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
    ПАЕВЫЕ_РОЛИ = ('founder', 'member', 'associate', 'board')

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
        Членство = self.env['coop.membership'].sudo()
        действующие = Членство.search([
            ('organization_id', '=', self.id), ('state', '=', 'active')])
        if not действующие:
            # Организация-визитка без единого человека: заводить ей
            # переписку не из кого. Появится состав — появится и чат.
            return []
        спецификации = [{
            'kind': 'org',
            'name': 'Рабочий чат — %s' % self.display_name,
            'subtitle': self.city or False,
            'partners': действующие.mapped('partner_id'),
        }]
        if self.coop_is_cooperative:
            пайщики = действующие.filtered(
                lambda m: m.role in self.ПАЕВЫЕ_РОЛИ).mapped('partner_id')
            if пайщики:
                спецификации.append({
                    'kind': 'shareholders',
                    'name': 'Пайщики — %s' % self.display_name,
                    'subtitle': self.city or False,
                    'partners': пайщики,
                })
        return спецификации


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
    def _coop_after_change(self, организации):
        организации._coop_ensure_channel()
        организации._coop_sync_channels()
        Сделка = self.env['coop.deal'].sudo()
        сделки = Сделка.search([
            '|', ('party_a_id', 'in', организации.ids),
            ('party_b_id', 'in', организации.ids)])
        сделки._coop_sync_channels()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        членства = super().create(vals_list)
        членства._coop_after_change(членства._coop_touched_partners())
        return членства

    def write(self, vals):
        было = self._coop_touched_partners()
        res = super().write(vals)
        if {'state', 'role', 'power_ids', 'organization_id', 'partner_id'} & set(vals):
            self._coop_after_change(было | self._coop_touched_partners())
        return res

    def unlink(self):
        # Организации запоминаем до удаления: после него спросить уже
        # не у кого.
        организации = self._coop_touched_partners()
        res = super().unlink()
        self.env['coop.membership']._coop_after_change(организации)
        return res
