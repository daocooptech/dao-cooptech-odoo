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

    # Подписи столбцов доски обращений: «обращение» — оно, значит
    # «Согласовано» и «Отменено» (владелец 11.11.2026). В «Сделках»
    # остаются «Согласована» / «Отменена» — там это сделка.
    INQUIRY_LABELS = {'agreed': 'Согласовано', 'cancelled': 'Отменено'}

    INQUIRY_ACTIONS = ('coop_deals.action_coop_deal_inquiries',)

    @api.model
    def get_views(self, views, options=None):
        # Контекст действия клиент при загрузке вида отбрасывает (оставляет
        # только язык), а номер действия передаёт — по нему и узнаём доску.
        res = super().get_views(views, options)
        action_id = (options or {}).get('action_id')
        if not action_id:
            return res
        ids = [self.env.ref(x, raise_if_not_found=False) for x in self.INQUIRY_ACTIONS]
        if action_id not in [a.id for a in ids if a]:
            return res
        fields_ = res.get('models', {}).get(self._name, {}).get('fields', {})
        if fields_.get('state', {}).get('selection'):
            state = dict(fields_['state'])
            state['selection'] = [
                [key, self.INQUIRY_LABELS.get(key, label)]
                for key, label in state['selection']]
            fields_['state'] = state
        return res

    @api.model
    def _coop_inquiry_for(self, listing, source):
        """Обращение по объявлению о ресурсе от того, кто сейчас действует."""
        # Стороны — как у отклика (coop_respond_wizard): у предложения
        # передаёт владелец объявления, у спроса — обратившийся.
        method = listing.method_ids[:1]
        return self._coop_inquiry(
            listing.owner_id, 'resource_id', listing, source,
            subject='resource', way=WAY.get(method.code or '', 'sale'),
            owner_gives=listing.listing_type == 'offer',
            amount=listing.price, city=listing.city)

    @api.model
    def _coop_skill_inquiry_for(self, offer, source):
        """Обращение по предложению навыка: заказчик — обратившийся,
        исполнитель — тот, кто предлагает навык."""
        return self._coop_inquiry(
            offer.partner_id, 'skill_offer_id', offer, source,
            subject='service', way='service', owner_gives=True,
            amount=offer.rate, city=offer.city)

    @api.model
    def _coop_inquiry(self, owner, link, record, source, subject, way,
                      owner_gives, amount=0.0, city=''):
        """Найти открытое обращение того, кто сейчас действует, с владельцем
        записи о ней же — или завести новое. Своя запись обращения не даёт."""
        me = self.env.user._coop_acting_partner()
        if not owner or owner == me:
            return self.browse()
        Deal = self.sudo()
        deal = Deal.search([
            (link, '=', record.id),
            ('state', 'in', OPEN_STATES),
            '|', '&', ('party_a_id', '=', me.id), ('party_b_id', '=', owner.id),
            '&', ('party_a_id', '=', owner.id), ('party_b_id', '=', me.id),
        ], order='id desc', limit=1)
        if deal:
            return deal
        side_a, side_b = (owner, me) if owner_gives else (me, owner)
        # Через sudo по той же причине, что и отклик: вторая сторона
        # чужая, права заводить запись с ней стороной у обратившегося нет.
        deal = Deal.create({
            'name': record.display_name,
            'subject': subject,
            'way': way,
            'party_a_id': side_a.id,
            'party_b_id': side_b.id,
            'role_a': _('Передаёт'),
            'role_b': _('Принимает'),
            'author_id': self.env.user.partner_id.id,
            link: record.id,
            'city': city or '',
            'amount': amount or 0.0,
            'state': 'lead',
            'inquiry_source': source,
        })
        body = (_('%(who)s написал(а) по «%(what)s».')
                if source == 'message' else
                _('%(who)s запросил(а) контакты по «%(what)s».')) % {
            'who': me.display_name, 'what': record.display_name}
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


class CoopSkillOffer(models.Model):
    _inherit = 'coop.skill.offer'

    def action_show_contacts(self):
        """«Показать контакты» — значит, будет звонок: заводим обращение."""
        self.env['coop.deal']._coop_skill_inquiry_for(self, 'call')
        return super().action_show_contacts()


class CoopResourceRespond(models.TransientModel):
    _inherit = 'coop.resource.respond'

    def action_respond(self):
        action = super().action_respond()
        deal = self.env['coop.deal'].sudo().browse(action.get('res_id'))
        if deal.exists() and not deal.inquiry_source:
            deal.inquiry_source = 'respond'
        return action


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def action_coop_my_trust(self):
        """«Сделки → Уровень доверия» (решение 89; предложение архитектора
        принято владельцем 11.11.2026): из чего сложился мой процент."""
        me = self.env.user._coop_acting_partner()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Уровень доверия'),
            'res_model': 'res.partner',
            'res_id': me.id,
            'view_mode': 'form',
            'views': [(self.env.ref('coop_deals.view_res_partner_coop_trust').id, 'form')],
            'target': 'current',
        }

    def action_coop_reviews_about(self):
        """Отзывы о человеке по завершённым сделкам."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'coop_deals.action_coop_deal_review')
        action['domain'] = [('target_id', '=', self.id)]
        action['name'] = _('Отзывы обо мне')
        return action
