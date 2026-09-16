# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ResPartner(models.Model):
    """Настройки участника — то, что он решает про себя, а не показывает.

    Открываются всегда на себе, как и «Моя страница»: своей записи, своего
    состояния и своих подтверждений. Чужие настройки не открываются ни по
    ссылке, ни через список — их там попросту нет.
    """

    _inherit = 'res.partner'

    coop_member_since = fields.Date(
        string='Участник платформы с', compute='_compute_coop_member_since',
        help='День, когда запись участника появилась на узле. У организаций '
             'берётся дата регистрации, если она заполнена.')

    def _compute_coop_member_since(self):
        for partner in self:
            дата = partner.coop_registered_on if 'coop_registered_on' in partner._fields else False
            if not дата and partner.create_date:
                дата = fields.Date.to_date(partner.create_date)
            partner.coop_member_since = дата

    @api.model
    def action_coop_open_settings(self):
        """Настройки — свои, и решается это при каждом открытии.

        Серверным действием, а не окном с доменом, по той же причине, что
        и «Моя страница»: от чьего имени человек действует, того и
        настройки. Переключил себя на организацию — открываются настройки
        организации.
        """
        partner = self.env.user._coop_acting_partner()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Настройки'),
            'res_model': 'res.partner',
            'res_id': partner.id,
            'view_mode': 'form',
            'views': [(self.env.ref('coop_settings.view_coop_settings_account_form').id,
                       'form')],
            'target': 'current',
            'context': {'coop_settings': True},
        }
