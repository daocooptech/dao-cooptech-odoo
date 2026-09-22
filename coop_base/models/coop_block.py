# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopBlock(models.Model):
    """Чёрный список: кого человек не хочет слышать.

    Заблокированный не пишет и не откликается. При этом он не исчезает
    с платформы и не узнаёт о блокировке отдельным извещением: сообщать
    об этом — значит превращать личное решение в повод для разбирательства.
    Отказ он увидит только в тот момент, когда попробует написать.

    Запись односторонняя: «я не хочу слышать его». Обратная блокировка —
    его собственное решение и своя запись.
    """

    _name = 'coop.block'
    _description = 'Заблокированный участник'
    _order = 'create_date desc'

    partner_id = fields.Many2one(
        'res.partner', string='Кто заблокировал', required=True, index=True,
        ondelete='cascade')
    blocked_id = fields.Many2one(
        'res.partner', string='Кого заблокировали', required=True, index=True,
        ondelete='cascade')
    blocked_on = fields.Datetime(
        string='Когда', default=fields.Datetime.now, readonly=True)

    _pair_uniq = models.Constraint(
        'unique (partner_id, blocked_id)',
        'Этот участник уже в вашем чёрном списке.')

    @api.constrains('partner_id', 'blocked_id')
    def _check_not_self(self):
        for record in self:
            if record.partner_id == record.blocked_id:
                raise UserError(_('Себя заблокировать нельзя.'))

    def _compute_display_name(self):
        for record in self:
            record.display_name = record.blocked_id.display_name or ''

    @api.model
    def _blocks(self, partner, other):
        """Закрыл ли `партнёр` дорогу `другому`.

        Спрашивается на каждое сообщение, поэтому запрос один и по двум
        номерам, а не выборка всего списка.
        """
        if not partner or not other or partner == other:
            return False
        return bool(self.sudo().search_count([
            ('partner_id', '=', partner.id),
            ('blocked_id', '=', other.id),
        ]))
