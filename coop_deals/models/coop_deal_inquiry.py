# -*- coding: utf-8 -*-
"""Обращения — упрощённая воронка у людей (задача 412).

Владелец 10.11.2026: «добавить вкладку Обращения, надо как-то у людей
сделать аналог CRM, но попроще», «переписки и звонки создают обращения,
они двигаются по воронке к сделке», место — «отдельным пунктом под моими
ресурсами».

Обращение — та же сделка на первых стадиях, а не отдельная сущность
(решение 451: лид человека — стадия «Обращение» в сделке). Новое здесь
только то, что заводит его сам разговор: «Написать владельцу» и
«Показать номер» на объявлении. Повторный разговор с тем же человеком о
том же объявлении попадает в то же обращение, пока оно не закрыто.
Воронка — «Обращение → Переговоры → Согласована», отказ — отменённая до
заключения; дальше сделка живёт в «Сделках».
"""

from odoo import _, api, fields, models

from odoo.addons.coop_resources.models.coop_respond_wizard import WAY

# Стадии, на которых обращение ещё открыто: новый разговор о том же
# объявлении с тем же человеком приходит сюда, а не заводит второе.
OPEN_STATES = ('lead', 'draft', 'agreed')


class CoopDeal(models.Model):
    _inherit = 'coop.deal'

    inquiry_source = fields.Selection([
        ('respond', 'Отклик на объявление'),
        ('message', 'Переписка'),
        ('call', 'Звонок'),
    ], string='Откуда обращение', index=True, readonly=True,
        help='Чем началось обращение. Пусто — сделку завели сразу, без '
             'обращения.')
    coop_mine = fields.Boolean(
        string='Моя сторона', compute='_compute_coop_mine',
        search='_search_coop_mine',
        help='Я — одна из сторон (сам или от имени организации, за которую '
             'сейчас действую).')

    def _compute_coop_mine(self):
        me = self.env.user._coop_acting_partner()
        for deal in self:
            deal.coop_mine = me in (deal.party_a_id | deal.party_b_id)

    def _search_coop_mine(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            return NotImplemented
        me = self.env.user._coop_acting_partner().id
        domain = ['|', ('party_a_id', '=', me), ('party_b_id', '=', me)]
        return domain if (operator == '=') == value else ['!'] + domain

    @api.model
    def _coop_inquiry_for(self, listing, source):
        """Обращение по объявлению от того, кто сейчас действует: найти
        открытое или завести новое. Своё объявление обращения не даёт."""
        me = self.env.user._coop_acting_partner()
        owner = listing.owner_id
        if not owner or owner == me:
            return self.browse()
        Deal = self.sudo()
        deal = Deal.search([
            ('resource_id', '=', listing.id),
            ('state', 'in', OPEN_STATES),
            '|', '&', ('party_a_id', '=', me.id), ('party_b_id', '=', owner.id),
            '&', ('party_a_id', '=', owner.id), ('party_b_id', '=', me.id),
        ], order='id desc', limit=1)
        if deal:
            return deal
        # Стороны — как у отклика (coop_respond_wizard): у предложения
        # передаёт владелец объявления, у спроса — обратившийся.
        if listing.listing_type == 'offer':
            side_a, side_b = owner, me
        else:
            side_a, side_b = me, owner
        method = listing.method_ids[:1]
        # Через sudo по той же причине, что и отклик: вторая сторона
        # чужая, права заводить запись с ней стороной у обратившегося нет.
        deal = Deal.create({
            'name': listing.name,
            'subject': 'resource',
            'way': WAY.get(method.code or '', 'sale'),
            'party_a_id': side_a.id,
            'party_b_id': side_b.id,
            'role_a': _('Передаёт'),
            'role_b': _('Принимает'),
            'author_id': self.env.user.partner_id.id,
            'resource_id': listing.id,
            'city': listing.city or '',
            'amount': listing.price or 0.0,
            'state': 'lead',
            'inquiry_source': source,
        })
        body = (_('%(who)s написал(а) по объявлению «%(what)s».')
                if source == 'message' else
                _('%(who)s запросил(а) номер по объявлению «%(what)s».')) % {
            'who': me.display_name, 'what': listing.name}
        deal.message_post(body=body)
        return deal


class CoopResource(models.Model):
    _inherit = 'coop.resource'

    def coop_owner_phone(self):
        """«Показать номер» — значит, будет звонок: заводим обращение."""
        phone = super().coop_owner_phone()
        if phone:
            self.env['coop.deal']._coop_inquiry_for(self, 'call')
        return phone


class CoopResourceRespond(models.TransientModel):
    _inherit = 'coop.resource.respond'

    def action_respond(self):
        action = super().action_respond()
        deal = self.env['coop.deal'].sudo().browse(action.get('res_id'))
        if deal.exists() and not deal.inquiry_source:
            deal.inquiry_source = 'respond'
        return action
