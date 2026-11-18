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

EXECUTOR_STATUS = [
    ('org', 'организация'),
    ('ip', 'индивидуальный предприниматель'),
    ('npd', 'самозанятый (НПД)'),
    ('gph', 'физическое лицо, договор ГПХ'),
]
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
    coop_executor_tax_note = fields.Char(
        string='Статус исполнителя', compute='_compute_coop_executor_tax_note')

    def _compute_natural_ndfl(self):
        rub = self.env.ref('base.RUB')
        for record in self:
            record.natural_ndfl = sum(record.natural_income_ids.mapped('ndfl_amount'))
            record.natural_currency_id = rub

    @api.depends('assignee_id', 'payer_id')
    def _compute_coop_executor_tax_note(self):
        Application = self.env['coop.bounty.application']
        for task in self:
            task.coop_executor_tax_note = Application._coop_tax_texts(
                task.assignee_id, task.payer_id)[0] if task.assignee_id else False

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

    # Текстом, а не строкой: в списке заявок строка обрезается, текст переносится.
    coop_tax_note = fields.Text(string='Статус и налог', compute='_compute_coop_tax_note')
    coop_tax_warning = fields.Text(string='Внимание', compute='_compute_coop_tax_note')

    @api.depends('partner_id', 'task_id.payer_id')
    def _compute_coop_tax_note(self):
        for application in self:
            note, warning = self._coop_tax_texts(application.partner_id, application.task_id.payer_id)
            application.coop_tax_note = note
            application.coop_tax_warning = warning

    @api.model
    def _coop_tax_texts(self, partner, payer):
        """Что автор должен знать об исполнителе до утверждения: статус —
        и предупреждение, если оплата токенами упирается в закон."""
        if not partner:
            return False, False
        person = partner.sudo()
        status = executor_status(person)
        if status == 'org':
            note = _('Организация — акт приёмки, НДФЛ нет')
        elif status == 'ip':
            note = _('ИП, %s — акт приёмки, налог платит сам') % dict(
                person._fields['coop_tax_regime'].selection)[person.coop_tax_regime]
        elif status == 'npd':
            note = _('Самозанятый — акт приёмки и чек НПД')
        else:
            note = _('Физлицо, договор ГПХ — акт приёмки; НДФЛ не удерживается, '
                     'агент сообщает о нём в налоговую')
        warnings = []
        if status != 'org' and not person.coop_tax_resident:
            warnings.append(_('не налоговый резидент РФ: НДФЛ 30 % или по соглашению '
                              'об избежании двойного налогообложения'))
        if status != 'org' and payer and self.env['coop.membership'].sudo().search_count(
                [('partner_id', '=', person.id), ('organization_id', '=', payer.id)], limit=1):
            warnings.append(_('состоит в организации-авторе: за работу по трудовому договору и '
                              'трудовое участие токенами платить нельзя (ч. 3 ст. 131 ТК) — только '
                              'по договору ГПХ, отдельно от трудовых обязанностей'))
        warning = '; '.join(warnings)
        return note, (warning[:1].upper() + warning[1:]) if warning else False


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
