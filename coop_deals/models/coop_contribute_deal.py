# -*- coding: utf-8 -*-
"""«Без вступления» в окне «Участвовать» (решение 676, задача 445).

Нечлену вклад в кооперативный проект закрыт, но отдать проекту вещь,
технику, помещение, труд или знания он может — сделкой с инициатором.
Порядок как в проекте окна ux-ui-designer 14.11: что передаёте → как
(договор) → что именно → сумма → чем вам платят. Итог — обращение в
«Сделках».

Виды, договоры и способы оплаты — маленькие справочники, а не списки
выбора: радио движка фильтрует их доменом, и окно показывает только то,
что подходит виду вклада и форме кооператива (решение 679 п. 2).
Займа нет (679 п. 1: участие в проекте — не заём). Деньги нечлену в
кредитном кооперативе, ЖСК и ГСК не предлагаем: там их принимают только
от членов (190-ФЗ ст. 6, 193-ФЗ ст. 40.1). Токенами не платим: вместо
зарплаты нельзя (ТК 131), по гражданскому договору — открыто у юриста.
"""
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopContributeKind(models.Model):
    _name = 'coop.contribute.kind'
    _description = 'Что передаёт нечлен проекту'
    _order = 'sequence, id'

    name = fields.Char(string='Вид', required=True, translate=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    # Коды форм через пробел, где вид нечлену закрыт.
    hide_forms = fields.Char(string='Скрыт у форм')
    warning = fields.Text(string='Предупреждение', translate=True)


class CoopContributePay(models.Model):
    _name = 'coop.contribute.pay'
    _description = 'Чем платят нечлену'
    _order = 'sequence, id'

    name = fields.Char(string='Чем платят', required=True, translate=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)


class CoopContributeWay(models.Model):
    _name = 'coop.contribute.way'
    _description = 'Договор, которым нечлен передаёт проекту'
    _order = 'sequence, id'

    name = fields.Char(string='Договор', required=True, translate=True)
    sequence = fields.Integer(default=10)
    kind_id = fields.Many2one(
        'coop.contribute.kind', string='Вид', required=True,
        ondelete='cascade')
    deal_way = fields.Char(
        string='Способ сделки', required=True,
        help='Код способа в coop.deal.way.')
    deal_subject = fields.Char(string='Предмет сделки', default='resource')
    pay_ids = fields.Many2many(
        'coop.contribute.pay', string='Чем платят')
    note = fields.Char(string='Пояснение', translate=True)


class CoopContributeDeal(models.TransientModel):
    _inherit = 'coop.project.contribute'

    org_form_code = fields.Char(compute='_compute_deal_kinds')
    deal_kind_ids = fields.Many2many(
        'coop.contribute.kind', compute='_compute_deal_kinds')
    # Деньги закрыты формой — показываем почему (проект окна, п. 3).
    deal_money_closed = fields.Boolean(compute='_compute_deal_kinds')
    deal_kind_id = fields.Many2one(
        'coop.contribute.kind', string='Что передаёте',
        compute='_compute_deal_kind_id', store=True, readonly=False)
    deal_kind_warning = fields.Text(related='deal_kind_id.warning')
    deal_way_id = fields.Many2one(
        'coop.contribute.way', string='Как',
        compute='_compute_deal_way_id', store=True, readonly=False)
    deal_way_note = fields.Char(related='deal_way_id.note')
    deal_pay_ids = fields.Many2many(
        related='deal_way_id.pay_ids', string='Способы оплаты')
    deal_pay_id = fields.Many2one(
        'coop.contribute.pay', string='Чем вам платят',
        compute='_compute_deal_pay_id', store=True, readonly=False)
    deal_name = fields.Char(string='Что именно')
    deal_amount = fields.Monetary(
        string='Сумма', currency_field='currency_id')

    @api.depends('project_id')
    def _compute_deal_kinds(self):
        kinds = self.env['coop.contribute.kind'].search([])
        for wizard in self:
            form = wizard.project_id.partner_id.coop_legal_form_id.code or ''
            wizard.org_form_code = form
            allowed = kinds.filtered(
                lambda k: form not in (k.hide_forms or '').split())
            wizard.deal_kind_ids = allowed
            wizard.deal_money_closed = bool(
                (kinds - allowed).filtered(lambda k: k.code == 'money'))

    # Цепочка вид → договор → оплата — вычисляемыми редактируемыми полями:
    # движок пересчитывает их сам и на новой записи, где обработчики
    # onchange друг друга не вызывают.
    @api.depends('project_id')
    def _compute_deal_kind_id(self):
        for wizard in self:
            if wizard.deal_kind_id not in wizard.deal_kind_ids:
                wizard.deal_kind_id = wizard.deal_kind_ids[:1]

    @api.depends('deal_kind_id')
    def _compute_deal_way_id(self):
        Way = self.env['coop.contribute.way']
        for wizard in self:
            if wizard.deal_way_id.kind_id != wizard.deal_kind_id:
                wizard.deal_way_id = Way.search(
                    # В окне до сохранения id — временный, ищем по исходному.
                    [('kind_id', '=', wizard.deal_kind_id._origin.id)], limit=1)

    @api.depends('deal_way_id')
    def _compute_deal_pay_id(self):
        for wizard in self:
            if wizard.deal_pay_id not in wizard.deal_way_id.pay_ids:
                wizard.deal_pay_id = wizard.deal_way_id.pay_ids[:1]

    def action_coop_propose_deal(self):
        self.ensure_one()
        project = self.project_id
        me = self.env.user._coop_acting_partner()
        if project.partner_id == me:
            raise UserError(_('Это ваш проект.'))
        kind, way = self.deal_kind_id, self.deal_way_id
        if not kind or kind not in self.deal_kind_ids:
            raise UserError(_('Выберите, что передаёте проекту.'))
        if not way or way.kind_id != kind:
            raise UserError(_('Выберите, каким договором передаёте.'))
        if self.deal_pay_id and self.deal_pay_id not in way.pay_ids:
            raise UserError(_('Такой оплаты у этого договора нет.'))
        what = self.deal_name or self.name
        if not what:
            raise UserError(_('Напишите, что именно предлагаете проекту.'))
        deal = self.env['coop.deal'].sudo().create({
            'name': what,
            'subject': way.deal_subject or 'resource',
            'way': way.deal_way,
            'party_a_id': me.id,
            'party_b_id': project.partner_id.id,
            'role_a': _('Передаёт'),
            'role_b': _('Принимает'),
            'author_id': self.env.user.partner_id.id,
            'project_id': project.id,
            'amount': self.deal_amount or 0.0,
            'state': 'lead',
        })
        terms = Markup('%s: %s<br/>%s: %s<br/>%s: %s') % (
            _('Что передаёт'), kind.name, _('Договор'), way.name,
            _('Чем платят'), self.deal_pay_id.name or _('без оплаты'))
        deal.message_post(body=terms)
        body = _('Предложение сделки по проекту «%(project)s»: %(what)s '
                 '(%(way)s) от %(who)s. Обращение %(number)s.',
                 project=project.name, what=what, way=way.name,
                 who=me.display_name, number=deal.number or '')
        self.env['coop.notification']._notify(
            project.partner_id, body, record=project, kind='project')
        project.sudo().message_post(body=body)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'coop.deal',
            'res_id': deal.id,
            'view_mode': 'form',
            'target': 'current',
        }
