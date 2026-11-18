# -*- coding: utf-8 -*-
"""Задачи за токены и налоги (решения 414, 515, 668; № 465 п. 20).

- До утверждения автор видит статус заявителя — самозанятый, ИП,
  физлицо по договору ГПХ или организация — и резидентство из профиля,
  с предупреждением, где оплата токенами упирается в закон: в России
  токенами платят только по ГПХ и самозанятым, за работу по трудовому
  договору и трудовое участие члена кооператива — только деньгами
  (ч. 3 ст. 131 ТК, решение 668).
- При каждой выплате — акт приёмки с номером: статус исполнителя
  записывается в выплату на день приёмки, потому что потом профиль может
  поменяться, а акт — нет.
"""
from odoo import _, api, fields, models

# Статус — одним-двумя словами, как бейдж (дизайн-система, `Badge`);
# полная формулировка — в подсказке столбца и в акте.
EXECUTOR_STATUS = [
    ('org', 'Организация'),
    ('ip', 'ИП'),
    ('npd', 'Самозанятый'),
    ('gph', 'Физлицо, ГПХ'),
]
EXECUTOR_STATUS_HELP = (
    'Из профиля исполнителя. Самозанятый — акт приёмки и чек НПД; ИП — акт, налог платит '
    'сам; физлицо — договор ГПХ, НДФЛ не удерживается, агент сообщает о нём в налоговую; '
    'организация — акт, НДФЛ нет.')
TAX_FLAGS = [
    ('nonresident', 'Нерезидент РФ'),
    ('member', 'Член организации'),
    ('both', 'Нерезидент, член организации'),
]
TAX_FLAG_HELP = (
    'Нерезидент РФ — НДФЛ 30 % или по соглашению об избежании двойного налогообложения. '
    'Член организации-автора — за работу по трудовому договору и трудовое участие токенами '
    'платить нельзя (ч. 3 ст. 131 ТК, решение 668), только по договору ГПХ.')
IP_REGIMES = ('usn_income', 'usn_profit', 'patent')


def executor_status(partner):
    """Статус исполнителя по профилю. Общая система у человека — то же,
    что физлицо: налог за него удерживает или о нём сообщает агент."""
    if partner.is_company:
        return 'org'
    if partner.coop_tax_regime == 'npd':
        return 'npd'
    if partner.coop_tax_regime in IP_REGIMES:
        return 'ip'
    return 'gph'


class CoopBountyTask(models.Model):
    _inherit = 'coop.bounty.task'

    natural_income_ids = fields.One2many(
        'coop.tax.natural.income', 'task_id', string='НДФЛ с вознаграждения')
    natural_ndfl = fields.Monetary(
        string='НДФЛ с вознаграждения', currency_field='natural_currency_id',
        compute='_compute_natural_ndfl')
    natural_ndfl_state = fields.Selection(
        related='natural_income_ids.state', string='Состояние НДФЛ')
    natural_currency_id = fields.Many2one(
        'res.currency', compute='_compute_natural_ndfl')
    coop_executor_status = fields.Selection(
        EXECUTOR_STATUS, string='Статус исполнителя', compute='_compute_coop_executor_status',
        help=EXECUTOR_STATUS_HELP)
    coop_executor_flag = fields.Selection(
        TAX_FLAGS, string='Внимание', compute='_compute_coop_executor_status', help=TAX_FLAG_HELP)

    def _compute_natural_ndfl(self):
        rub = self.env.ref('base.RUB')
        for record in self:
            record.natural_ndfl = sum(record.natural_income_ids.mapped('ndfl_amount'))
            record.natural_currency_id = rub

    @api.depends('assignee_id', 'payer_id')
    def _compute_coop_executor_status(self):
        Application = self.env['coop.bounty.application']
        for task in self:
            status, flag = Application._coop_tax_check(task.assignee_id, task.payer_id)
            task.coop_executor_status = status
            task.coop_executor_flag = flag

    def _coop_on_payout(self, payout):
        """Выплата — акт приёмки; токенами услуг платформы — ещё и строка
        реестра (решение 515).

        По выплате, а не по задаче (№ 465): у команды доход у каждого свой,
        частичная приёмка платит меньше суммы, постоянная задача — по
        каждому принятому результату, этапная — по каждому этапу.
        """
        result = super()._coop_on_payout(payout)
        payout._coop_fill_act()
        task = payout.task_id
        # Исполнитель-организация — не НДФЛ (решение 553): реестр только людей.
        if task.payment_mode == 'tokens' and task.payer_id and not payout.partner_id.is_company:
            self.env['coop.tax.natural.income'].sudo()._coop_register_payout(payout)
        return result


class CoopBountyApplication(models.Model):
    _inherit = 'coop.bounty.application'

    coop_executor_status = fields.Selection(
        EXECUTOR_STATUS, string='Статус', compute='_compute_coop_executor_status',
        help=EXECUTOR_STATUS_HELP)
    coop_tax_flag = fields.Selection(
        TAX_FLAGS, string='Внимание', compute='_compute_coop_executor_status', help=TAX_FLAG_HELP)
    # Одним бейджем: статус, а при отметке — и она, жёлтым. Отдельный столбец
    # «Внимание» стоял пустым почти у всех и отнимал место у сообщения.
    coop_executor_label = fields.Char(
        string='Статус', compute='_compute_coop_executor_status',
        help=EXECUTOR_STATUS_HELP + ' ' + TAX_FLAG_HELP)

    @api.depends('partner_id', 'task_id.payer_id')
    def _compute_coop_executor_status(self):
        statuses = dict(EXECUTOR_STATUS)
        flags = {'nonresident': _('нерезидент РФ'), 'member': _('член организации'),
                 'both': _('нерезидент, член организации')}
        for application in self:
            status, flag = self._coop_tax_check(application.partner_id, application.task_id.payer_id)
            application.coop_executor_status = status
            application.coop_tax_flag = flag
            label = statuses.get(status, '')
            application.coop_executor_label = (
                '%s · %s' % (label, flags[flag]) if flag else label) or False

    @api.model
    def _coop_tax_check(self, partner, payer):
        """Что автор должен знать об исполнителе до утверждения: статус —
        и отметка, если оплата токенами упирается в закон."""
        if not partner:
            return False, False
        person = partner.sudo()
        status = executor_status(person)
        if status == 'org':
            return status, False
        nonresident = not person.coop_tax_resident
        member = bool(payer) and bool(self.env['coop.membership'].sudo().search_count(
            [('partner_id', '=', person.id), ('organization_id', '=', payer.id)], limit=1))
        flag = 'both' if nonresident and member else 'nonresident' if nonresident else             'member' if member else False
        return status, flag


class CoopBountyPayout(models.Model):
    _inherit = 'coop.bounty.payout'

    act_number = fields.Char(string='Акт №', readonly=True, copy=False, index=True)
    executor_status = fields.Selection(EXECUTOR_STATUS, string='Статус исполнителя', readonly=True)
    executor_resident = fields.Boolean(string='Налоговый резидент РФ', readonly=True, default=True)
    payer_id = fields.Many2one(related='task_id.payer_id', string='Заказчик')

    def _coop_fill_act(self):
        """Номер акта и статус исполнителя на день выплаты."""
        Sequence = self.env['ir.sequence'].sudo()
        for payout in self.sudo().filtered(lambda p: not p.act_number):
            partner = payout.partner_id
            payout.write({
                'act_number': Sequence.next_by_code('coop.bounty.act'),
                'executor_status': executor_status(partner),
                'executor_resident': partner.is_company or partner.coop_tax_resident,
            })
        return True

    def action_print_act(self):
        self.ensure_one()
        return self.env.ref('coop_tax.action_report_bounty_act').report_action(self)
