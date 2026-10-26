# -*- coding: utf-8 -*-
import csv
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .ndfl import ndfl

# 1 токен = 1 ₽ (решение 249): по этой оценке токены за задачу — доход.
TOKEN_RUB = 1.0
# П. 4 ст. 226 НК: «Удерживаемая сумма налога не может превышать 50
# процентов суммы выплаты». Считаем от суммы на руки после НДФЛ самой
# выплаты — осторожное прочтение: человек не останется без половины денег.
WITHHOLD_SHARE = 0.5


class CoopTaxNaturalIncome(models.Model):
    """Реестр доходов в натуральной форме (решение 515).

    Задача, оплаченная сразу токенами, — доход в натуральной форме (пп. 2
    п. 1 ст. 223 НК). НДФЛ исчисляется в день приёмки, но денег, из
    которых его удержать, нет: агент удерживает его из ближайшей денежной
    выплаты тому же человеку, не больше половины выплаты (п. 4 ст. 226),
    а что не удержал до конца года — сообщает человеку и в налоговую до
    25 февраля следующего года (п. 5 ст. 226).

    Строка — одно вознаграждение. Состояние следует из сумм и года:
    удержано всё — «удержан»; год кончился или сообщение отправлено, а
    остаток есть — «не удержан»; иначе — «исчислен».
    """
    _name = 'coop.tax.natural.income'
    _description = 'Доход в натуральной форме'
    _order = 'date desc, id desc'

    name = fields.Char(string='Доход', required=True)
    partner_id = fields.Many2one(
        'res.partner', string='Получатель', required=True, index=True,
        ondelete='restrict')
    agent_id = fields.Many2one(
        'res.partner', string='Налоговый агент', required=True, index=True,
        ondelete='restrict', help='Кто выплатил вознаграждение.')
    task_id = fields.Many2one(
        'coop.bounty.task', string='Задача', index=True, ondelete='set null')
    date = fields.Date(string='Дата дохода', required=True, index=True)
    year = fields.Integer(string='Год', compute='_compute_year', store=True, index=True)
    tokens = fields.Integer(string='Токенов')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.ref('base.RUB'), required=True)
    amount = fields.Monetary(string='Доход, ₽', currency_field='currency_id', required=True)
    rate = fields.Char(string='Ставка')
    ndfl_amount = fields.Monetary(string='НДФЛ исчислен', currency_field='currency_id')
    withheld = fields.Monetary(string='Удержан', currency_field='currency_id')
    remaining = fields.Monetary(
        string='Не удержан', currency_field='currency_id',
        compute='_compute_state', store=True)
    withheld_note = fields.Char(string='Из какой выплаты удержан')
    reported_on = fields.Date(
        string='Сообщено в налоговую',
        help='Дата сообщения о невозможности удержать налог (п. 5 ст. 226 НК).')
    state = fields.Selection([
        ('calculated', 'Исчислен'),
        ('withheld', 'Удержан'),
        ('not_withheld', 'Не удержан'),
    ], string='Состояние', compute='_compute_state', store=True, index=True)

    @api.depends('date')
    def _compute_year(self):
        for record in self:
            record.year = record.date.year if record.date else 0

    @api.depends('ndfl_amount', 'withheld', 'reported_on', 'year')
    def _compute_state(self):
        this_year = fields.Date.context_today(self).year
        for record in self:
            record.remaining = max(0.0, record.ndfl_amount - record.withheld)
            if not record.remaining:
                record.state = 'withheld'
            elif record.reported_on or record.year < this_year:
                record.state = 'not_withheld'
            else:
                record.state = 'calculated'

    # ── Начисление ───────────────────────────────────────────────────────

    @api.model
    def _coop_register_task(self, task):
        """Строка реестра по принятой задаче, оплаченной токенами."""
        partner = task.assignee_id
        date = task.accepted_on or fields.Date.context_today(self)
        amount = task.reward_tokens * TOKEN_RUB
        tax, rate = self._coop_ndfl(partner, task.payer_id, amount, date)
        return self.create({
            'name': _('Вознаграждение за задачу «%s»') % task.name,
            'partner_id': partner.id,
            'agent_id': task.payer_id.id,
            'task_id': task.id,
            'date': date,
            'tokens': task.reward_tokens,
            'amount': amount,
            'rate': rate or False,
            'ndfl_amount': tax,
        })

    @api.model
    def _coop_ndfl(self, partner, agent, amount, date):
        """Шкала — по сумме доходов у этого агента за год (ст. 224)."""
        earlier = self.search([
            ('partner_id', '=', partner.id), ('agent_id', '=', agent.id),
            ('year', '=', date.year), ('date', '<=', date)])
        return ndfl(amount, sum(earlier.mapped('amount')),
                    resident=partner.coop_tax_resident,
                    treaty_rate=partner.coop_tax_treaty_rate)

    # ── Удержание из денежной выплаты ────────────────────────────────────

    @api.model
    def _coop_withhold(self, partner, agent, cash, date, note):
        """Удержать неудержанное из денежной выплаты; вернуть сумму.

        Только тем же агентом и в том же году: после 31 декабря удержание
        кончается, остаётся сообщение (п. 5 ст. 226). Старые строки — первыми.
        """
        limit = int(cash * WITHHOLD_SHARE)
        if limit <= 0:
            return 0.0
        lines = self.search([
            ('partner_id', '=', partner.id), ('agent_id', '=', agent.id),
            ('year', '=', date.year), ('state', '=', 'calculated'),
            ('date', '<=', date)], order='date, id')
        total = 0.0
        for line in lines:
            take = min(line.remaining, limit - total)
            if take <= 0:
                break
            line.write({'withheld': line.withheld + take, 'withheld_note': note})
            total += take
        return total

    # ── Сообщение в налоговую ────────────────────────────────────────────

    @api.model
    def _coop_close_years(self):
        """Пересчитать состояние: прошедший год делает «исчислен» «не удержан»."""
        self.search([('state', '=', 'calculated'),
                     ('year', '<', fields.Date.context_today(self).year)])._compute_state()

    def action_fns_message(self):
        """Сообщение о невозможности удержать налог — по выбранным строкам.

        Отмечает дату отправки и отдаёт файл: человек, ИНН, год, доход,
        исчисленный, удержанный и не удержанный налог, агент.
        """
        lines = self.filtered(lambda l: l.remaining > 0 and l.year < fields.Date.context_today(l).year)
        if not lines:
            raise UserError(_(
                'Сообщают только о налоге, не удержанном за прошедший год: '
                'среди выбранных строк таких нет.'))
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=';')
        writer.writerow(['Получатель', 'ИНН', 'Год', 'Доход, ₽', 'НДФЛ исчислен',
                         'Удержан', 'Не удержан', 'Налоговый агент', 'ИНН агента'])
        for line in lines.sorted(lambda l: (l.agent_id.id, l.partner_id.name or '', l.date)):
            writer.writerow([line.partner_id.name, line.partner_id.vat or '', line.year,
                             '%.2f' % line.amount, '%.0f' % line.ndfl_amount,
                             '%.0f' % line.withheld, '%.0f' % line.remaining,
                             line.agent_id.name, line.agent_id.vat or ''])
        lines.write({'reported_on': fields.Date.context_today(self)})
        attachment = self.env['ir.attachment'].create({
            'name': 'Сообщение о неудержанном НДФЛ, %s.csv' % ', '.join(
                str(y) for y in sorted(set(lines.mapped('year')))),
            'raw': buffer.getvalue().encode('utf-8-sig'),
            'mimetype': 'text/csv',
        })
        return {'type': 'ir.actions.act_url', 'target': 'download',
                'url': '/web/content/%d?download=true' % attachment.id}
