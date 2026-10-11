# -*- coding: utf-8 -*-
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Знак записи. Нога «на счёте» с плюсом — деньги пришли на счёт, с
# минусом — ушли. Остальные ноги — обязательства счёта перед кем-то: с
# минусом счёт стал должен, с плюсом долг погашен. Поэтому внутри события
# сумма всегда ноль, а остаток бенефициара — минус сумма его записей.
LEGS = [
    ('bank', 'Остаток на счёте'),
    ('holder', 'Бенефициар'),
    ('unrecognized', 'Нераспознанное'),
    ('fee', 'Комиссия оператора'),
]

KINDS = [
    ('credit', 'Зачисление'),
    ('unrecognized', 'Нераспознанное поступление'),
    ('recognize', 'Распознано'),
    ('beneficiary', 'Смена бенефициара'),
    ('fee', 'Комиссия'),
    ('payout', 'Выплата'),
    ('refund', 'Возврат'),
]


class CoopNominalEntry(models.Model):
    """Запись книги номинального счёта.

    Книга неизменяема: записи создаются только проводкой события
    (`_post`), не правятся и не удаляются. Ошибку исправляют новой
    проводкой — иначе остаток за прошлый месяц сегодня оказался бы
    другим, и сверка с выпиской потеряла бы смысл.
    """
    _name = 'coop.nominal.entry'
    _description = 'Запись книги номинального счёта'
    _order = 'date, id'

    account_id = fields.Many2one(
        'coop.nominal.account', string='Счёт', required=True,
        ondelete='restrict', index=True, readonly=True)
    event_key = fields.Char(
        string='Ключ события', required=True, index=True, readonly=True,
        help='Общий ключ записей одного события.')
    kind = fields.Selection(KINDS, string='Событие', required=True, readonly=True)
    leg = fields.Selection(LEGS, string='Нога', required=True, readonly=True)
    share_id = fields.Many2one(
        'coop.nominal.share', string='Доля', ondelete='restrict',
        index=True, readonly=True)
    partner_id = fields.Many2one(
        'res.partner', string='Бенефициар', index=True, readonly=True)
    amount = fields.Monetary(
        string='Сумма', currency_field='currency_id', required=True,
        readonly=True)
    currency_id = fields.Many2one(related='account_id.currency_id')
    date = fields.Date(string='Дата', required=True, index=True, readonly=True)
    posted_by_id = fields.Many2one('res.users', string='Провёл', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('coop_nominal_post'):
            raise UserError(_(
                'Запись книги создаётся только проводкой события.'))
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_(
            'Книга номинального счёта не правится: ошибку исправляют новой '
            'проводкой.'))

    def unlink(self):
        raise UserError(_(
            'Записи книги номинального счёта не удаляются.'))

    @api.model
    def _post(self, account, kind, date, lines):
        """Провести событие: набор записей с нулевой суммой.

        `lines` — словари с ключами `leg`, `amount` и, где нужно,
        `share` и `partner`. Нога бенефициара без бенефициара и любая
        запись с нулевой суммой — ошибка вызывающего кода.
        """
        account.ensure_one()
        currency = account.currency_id
        if not lines:
            raise UserError(_('Событие без записей не проводится.'))
        if not currency.is_zero(sum(line['amount'] for line in lines)):
            raise UserError(_(
                'Записи события должны давать в сумме ноль.'))
        key = uuid.uuid4().hex
        vals_list = []
        for line in lines:
            if currency.is_zero(line['amount']):
                raise UserError(_('Запись с нулевой суммой не проводится.'))
            partner = line.get('partner')
            if line['leg'] == 'holder' and not partner:
                raise UserError(_('У записи бенефициара нет бенефициара.'))
            share = line.get('share')
            vals_list.append({
                'account_id': account.id,
                'event_key': key,
                'kind': kind,
                'leg': line['leg'],
                'share_id': share.id if share else False,
                'partner_id': partner.id if partner else False,
                'amount': currency.round(line['amount']),
                'date': date,
                'posted_by_id': self.env.user.id,
            })
        return self.sudo().with_context(coop_nominal_post=True).create(vals_list)

    @api.model
    def _leg_sum(self, account, leg, share=None, partner=None, until=None):
        domain = [('account_id', '=', account.id), ('leg', '=', leg)]
        if share is not None:
            domain.append(('share_id', '=', share.id))
        if partner is not None:
            domain.append(('partner_id', '=', partner.id))
        if until:
            domain.append(('date', '<=', until))
        groups = self.sudo()._read_group(domain, aggregates=['amount:sum'])
        return (groups[0][0] or 0.0) if groups else 0.0
