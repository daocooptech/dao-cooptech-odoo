# -*- coding: utf-8 -*-
"""Кабинет организации (решение 450): воронка сделок и сотрудники.

Блок на странице организации — только её людям с полномочиями. Чужим
он не виден: это не витрина, а рабочее место.

Воронка — как в Битрикс24: открытые лиды CRM, затем сделки площадки по
стадиям. Канбан — вид в кабинете, общий раздел «Сделки» остаётся
списком (владелец 07.10.2026: «Вернуть в кабинете организации»).
"""
from odoo import _, api, fields, models

FUNNEL = ('lead', 'draft', 'agreed', 'active', 'acceptance', 'disputed', 'done')
OPEN = ('lead', 'draft', 'agreed', 'active', 'acceptance', 'disputed')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_is_org_staff = fields.Boolean(compute='_compute_coop_cabinet')
    # Воронку видят держатели «Сделок» — те же, кто ведёт лиды CRM
    # (решение 450): сделки организации открыты им, а не всему составу.
    coop_can_see_funnel = fields.Boolean(compute='_compute_coop_cabinet')
    coop_funnel_crm = fields.Integer(compute='_compute_coop_cabinet')
    coop_funnel_lead = fields.Integer(compute='_compute_coop_cabinet')
    coop_funnel_draft = fields.Integer(compute='_compute_coop_cabinet')
    coop_funnel_agreed = fields.Integer(compute='_compute_coop_cabinet')
    coop_funnel_active = fields.Integer(compute='_compute_coop_cabinet')
    coop_funnel_acceptance = fields.Integer(compute='_compute_coop_cabinet')
    coop_funnel_disputed = fields.Integer(compute='_compute_coop_cabinet')
    coop_funnel_done = fields.Integer(compute='_compute_coop_cabinet')
    coop_funnel_unassigned = fields.Integer(compute='_compute_coop_cabinet')
    coop_staff_ids = fields.Many2many(
        'coop.membership', string='Сотрудники и ответственные',
        compute='_compute_coop_cabinet')

    def _coop_org_deal_domain(self):
        return ['|', ('party_a_id', '=', self.id), ('party_b_id', '=', self.id)]

    @api.depends_context('uid')
    def _compute_coop_cabinet(self):
        Membership = self.env['coop.membership'].sudo()
        me = self.env.user.partner_id
        for org in self:
            staff = Membership
            if org.is_company and org.id:
                staff = Membership.search([
                    ('organization_id', '=', org.id), ('state', '=', 'active'),
                    ('power_ids', '!=', False)])
            mine = staff.filtered(lambda m: m.partner_id == me)
            is_staff = bool(mine)
            can_funnel = 'deal' in mine.power_ids.mapped('code')
            org.coop_is_org_staff = is_staff
            org.coop_can_see_funnel = can_funnel
            org.coop_staff_ids = staff if is_staff else Membership
            counts = dict.fromkeys(FUNNEL, 0)
            crm = unassigned = 0
            if can_funnel:
                Deal = self.env['coop.deal'].sudo()
                for state, count in Deal._read_group(
                        org._coop_org_deal_domain() + [('state', 'in', FUNNEL)],
                        ['state'], ['__count']):
                    counts[state] = count
                unassigned = Deal.search_count(org._coop_org_deal_domain() + [
                    ('state', 'in', OPEN), '|',
                    '&', ('party_a_id', '=', org.id), ('responsible_a_id', '=', False),
                    '&', ('party_b_id', '=', org.id), ('responsible_b_id', '=', False)])
                if org.coop_company_id:
                    crm = self.env['crm.lead'].sudo().search_count([
                        ('company_id', '=', org.coop_company_id.id),
                        ('type', '=', 'opportunity'), ('won_status', '=', 'pending')])
            for state in FUNNEL:
                org['coop_funnel_%s' % state] = counts[state]
            org.coop_funnel_crm = crm
            org.coop_funnel_unassigned = unassigned

    def action_coop_org_funnel(self):
        """Воронка сделок организации — канбан по стадиям."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Воронка сделок — %s') % self.name,
            'res_model': 'coop.deal',
            'view_mode': 'kanban,list,form',
            'views': [(self.env.ref('coop_crm.view_coop_deal_funnel_kanban').id, 'kanban'),
                      (False, 'list'), (False, 'form')],
            'search_view_id': self.env.ref('coop_deals.view_coop_deal_search').id,
            'domain': self._coop_org_deal_domain(),
            # Признаки каталога организаций сбрасываются явно: форма, из
            # которой нажата кнопка, отдаёт свой контекст вниз, и над
            # воронкой вставали вкладки каталога и «Добавить организацию».
            'context': {
                'coop_org_id': self.id, 'group_by': 'state',
                'coop_catalog': False, 'coop_section': False,
                'coop_create_label': _('Новая сделка'),
                'default_party_a_id': self.id,
            },
            'target': 'current',
        }

    def action_coop_org_leads(self):
        """Лиды CRM организации — первый этап её воронки."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'crm.crm_lead_action_pipeline')
        action['domain'] = [('company_id', '=', self.coop_company_id.id)]
        action['context'] = {'default_company_id': self.coop_company_id.id}
        return action


class CoopMembership(models.Model):
    _inherit = 'coop.membership'

    coop_open_deal_count = fields.Integer(
        string='Ведёт сделок', compute='_compute_coop_workload')
    coop_overdue_count = fields.Integer(
        string='Просрочено дел', compute='_compute_coop_workload')

    def _compute_coop_workload(self):
        Deal = self.env['coop.deal'].sudo()
        Activity = self.env['mail.activity'].sudo()
        today = fields.Date.context_today(self)
        for membership in self:
            users = membership.partner_id.user_ids
            org = membership.organization_id
            if not users or not org:
                membership.coop_open_deal_count = 0
                membership.coop_overdue_count = 0
                continue
            deals = Deal.search([
                ('state', 'in', OPEN), '|',
                '&', ('party_a_id', '=', org.id), ('responsible_a_id', 'in', users.ids),
                '&', ('party_b_id', '=', org.id), ('responsible_b_id', 'in', users.ids)])
            membership.coop_open_deal_count = len(deals)
            membership.coop_overdue_count = Activity.search_count([
                ('res_model', '=', 'coop.deal'), ('res_id', 'in', deals.ids),
                ('user_id', 'in', users.ids), ('date_deadline', '<', today)])


class CoopDeal(models.Model):
    _inherit = 'coop.deal'

    # Пустые стадии воронки тоже видны: пустая колонка — тоже сведения.
    state = fields.Selection(group_expand=True)

    coop_org_counterparty_id = fields.Many2one(
        'res.partner', string='С кем', compute='_compute_coop_org_view')
    coop_org_responsible_id = fields.Many2one(
        'res.users', string='Ответственный', compute='_compute_coop_org_view')

    @api.depends_context('coop_org_id')
    @api.depends('party_a_id', 'party_b_id', 'responsible_a_id', 'responsible_b_id')
    def _compute_coop_org_view(self):
        """Карточка воронки — глазами организации, чей это кабинет."""
        org_id = self.env.context.get('coop_org_id')
        for deal in self:
            ours_b = deal.party_b_id.id == org_id
            deal.coop_org_counterparty_id = deal.party_a_id if ours_b else deal.party_b_id
            deal.coop_org_responsible_id = deal.responsible_b_id if ours_b else deal.responsible_a_id
