# -*- coding: utf-8 -*-
"""Переписки организации: рабочая и пайщиков.

Решение владельца 328 от 16 сентября 2026: «в чатах организации только
сотрудники организации, в чатах пк только пайщики конкретного пк». Это
две разные переписки с разными составами, а не одна: у кооператива
рабочая жизнь и паевая — разные, и пайщик, не работающий в кооперативе,
не должен читать рабочую.

Сверх этих двух организация заводит свои чаты сама, сколько нужно, — в
них платформа не вмешивается.
"""

from odoo import api, models


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner', 'coop.channel.sync']

    # Роли, дающие место в паевом чате: пайщик, учредитель,
    # ассоциированный член и правление. Наёмный сотрудник паем не
    # владеет, и в паевом разговоре ему нечего делать.
    SHARE_ROLES = ('founder', 'member', 'associate', 'board')

    def _coop_channel_owners(self, kind=None):
        """Кто ведёт состав или подписывает от имени организации.

        Решение владельца 16 сентября 2026. Это те же люди, что решают,
        кто в организации состоит, — переименование её чата того же
        порядка. Полномочие «Переписка и заявки» сюда не годится: его
        поручают многим, и тогда рабочий чат переименовывал бы любой из
        семи.
        """
        self.ensure_one()
        if not self.is_company:
            return self.env['res.partner']
        return (self.coop_power_holders('roster')
                | self.coop_power_holders('sign'))

    def _coop_channel_specs(self):
        self.ensure_one()
        if not self.is_company:
            return []
        Membership = self.env['coop.membership'].sudo()
        active_ones = Membership.search([
            ('organization_id', '=', self.id), ('state', '=', 'active')])
        if not active_ones:
            # Организация-визитка без единого человека: заводить ей
            # переписку не из кого. Появится состав — появится и чат.
            return []
        specs = [{
            'kind': 'org',
            'name': 'Рабочий чат — %s' % self.display_name,
            'subtitle': self.city or False,
            'partners': active_ones.mapped('partner_id'),
        }]
        if self.coop_is_cooperative:
            shareholders = active_ones.filtered(
                lambda m: m.role in self.SHARE_ROLES).mapped('partner_id')
            if shareholders:
                specs.append({
                    'kind': 'shareholders',
                    'name': 'Пайщики — %s' % self.display_name,
                    'subtitle': self.city or False,
                    'partners': shareholders,
                })
        return specs


class CoopMembership(models.Model):
    """Сменился состав организации — сменился и состав её переписок.

    Хук на членстве, а не на организации: состав меняется именно здесь,
    и отсюда же видно, что изменилось — приём, выход, смена роли или
    полномочий.

    Пересчитываются заодно переписки сделок этой организации: в них
    сидят подписант и ведущий, а это полномочия, которые тут и выдают.
    """

    _inherit = 'coop.membership'

    def _coop_touched_partners(self):
        return self.mapped('organization_id')

    @api.model
    def _coop_after_change(self, organizations):
        organizations._coop_ensure_channel()
        organizations._coop_sync_channels()
        Deal = self.env['coop.deal'].sudo()
        deals = Deal.search([
            '|', ('party_a_id', 'in', organizations.ids),
            ('party_b_id', 'in', organizations.ids)])
        deals._coop_sync_channels()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        memberships = super().create(vals_list)
        memberships._coop_after_change(memberships._coop_touched_partners())
        return memberships

    def write(self, vals):
        was = self._coop_touched_partners()
        res = super().write(vals)
        if {'state', 'role', 'power_ids', 'organization_id', 'partner_id'} & set(vals):
            self._coop_after_change(was | self._coop_touched_partners())
        return res

    def unlink(self):
        # Организации запоминаем до удаления: после него спросить уже
        # не у кого.
        organizations = self._coop_touched_partners()
        res = super().unlink()
        self.env['coop.membership']._coop_after_change(organizations)
        return res
