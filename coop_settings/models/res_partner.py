# -*- coding: utf-8 -*-
import base64
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
            date_value = partner.coop_registered_on if 'coop_registered_on' in partner._fields else False
            if not date_value and partner.create_date:
                date_value = fields.Date.to_date(partner.create_date)
            partner.coop_member_since = date_value

    def action_coop_export_archive(self):
        """Выгрузка своих данных одним файлом.

        Собирается здесь, а не штатной выгрузкой Odoo: та отдаёт одну
        модель в таблицу, а человеку нужно всё своё разом и в виде,
        который можно прочитать без платформы.

        Сделки и извещения берутся через sudo: часть их видна правилами
        только сторонам, а в своей выгрузке человек вправе видеть своё.
        """
        self.ensure_one()
        if self != self.env.user._coop_acting_partner():
            raise UserError(_('Выгрузить можно только свои данные.'))

        # Ключи латиницей, значения по-русски. Файл читает и человек, и
        # программа — но ключ в нём остаётся машинным именем, а
        # содержательное там значение. Кириллица в именах запрещена
        # решением 368; кавычки вокруг имени не превращают его в текст.
        collected_value = {
            'card': self._coop_archive_card(),
            'memberships': self._coop_archive_memberships(),
            'notifications': self._coop_archive_notifications(),
        }
        content = json.dumps(collected_value, ensure_ascii=False, indent=2,
                                default=str)
        file = self.env['ir.attachment'].sudo().create({
            'name': 'cooptech-%s-%s.json' % (
                self.id, fields.Date.today().isoformat()),
            'type': 'binary',
            'datas': base64.b64encode(content.encode('utf-8')),
            'res_model': 'res.partner',
            'res_id': self.id,
            'public': False,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % file.id,
            'target': 'self',
        }

    def _coop_archive_card(self):
        """Карточка — то, что человек о себе написал."""
        self.ensure_one()
        field_names = ['name', 'email', 'phone', 'city', 'website', 'coop_about',
                'coop_languages', 'coop_birthdate', 'coop_trust',
                'coop_verification_level']
        card = {
            field: self[field] for field in field_names if field in self._fields
        }
        # Ключи латиницей: это выгрузка, её читает программа, а не
        # человек. Кириллица в машинных именах запрещена решением 368, и
        # ключ внутри кавычек остаётся именем — то, что он в кавычках, не
        # делает его текстом.
        card['contacts'] = [
            {'label': line.name, 'value': line.value}
            for line in self.coop_contact_line_ids
        ]
        return card

    def _coop_archive_memberships(self):
        self.ensure_one()
        Membership = self.env['coop.membership'].sudo()
        return [
            {
                'organization': record.organization_id.display_name,
                'role': record.role_id.name,
                'job_title': record.job_title,
                'joined_on': record.joined_on,
                'state': record.state,
            }
            for record in Membership.search([('partner_id', '=', self.id)])
        ]

    def _coop_archive_notifications(self):
        self.ensure_one()
        Notification = self.env['coop.notification'].sudo()
        return [
            {
                'when': record.create_date,
                'about': record.kind,
                'event': record.body,
            }
            for record in Notification.search(
                [('partner_id', '=', self.id)], limit=500)
        ]

    def action_coop_hide_profile(self):
        """Скрыть себя из каталога — но не стереть.

        Не `active`: снятая запись исчезает и из чужих сделок, и из
        состава организаций, и из переписки, а человек просил всего лишь
        не показывать себя в каталоге.
        """
        self.ensure_one()
        self._coop_check_own()
        self.sudo().coop_profile_hidden = True
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_coop_show_profile(self):
        self.ensure_one()
        self._coop_check_own()
        self.sudo().coop_profile_hidden = False
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_coop_request_deletion(self):
        """Заявление об удалении — правлению узла, а не кнопка стирания.

        У участника кооператива есть пай, обязательства и незакрытые
        сделки; стереть его запись, пока они живы, значит оборвать чужие
        расчёты. Поэтому профиль скрывается сразу, а само удаление
        проходит через правление — как выход из кооператива.
        """
        self.ensure_one()
        self._coop_check_own()
        self.sudo().coop_profile_hidden = True
        # Кому заявление: тем, кто ведёт узел. Не всем администраторам
        # Odoo, а держателям платформенных полномочий: решает
        # вопрос о выходе участника правление, а не техническая служба.
        group = self.env.ref('coop_base.group_coop_platform',
                                 raise_if_not_found=False)
        receivers = group.sudo().all_user_ids.partner_id if group else None
        if receivers:
            self.env['coop.notification'].sudo()._notify(
                receivers,
                _('Участник %s подал заявление об удалении аккаунта.')
                % self.display_name,
                record=self, kind='org')
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def _coop_check_own(self):
        if self != self.env.user._coop_acting_partner():
            raise UserError(_('Это можно сделать только со своим профилем.'))

    @api.model
    def action_coop_open_notifications(self):
        """Вкладка «Уведомления».

        Строки настроек заводятся здесь, при первом заходе: девять строк
        на каждого из трёх с половиной тысяч участников, большинство из
        которых сюда не зайдёт, — это три десятка тысяч записей ради
        умолчания, которое и так известно.
        """
        partner = self.env.user.partner_id
        self.env['coop.notification.pref']._ensure_rows(partner)
        return self.action_coop_open_settings(
            'coop_settings.view_coop_settings_notifications_form',
            'Уведомления')

    def action_coop_open_settings(self, view_xmlid='coop_settings.view_coop_settings_account_form',
                                  name=None):
        """Настройки — свои, и решается это при каждом открытии.

        Серверным действием, а не окном с доменом, по той же причине, что
        и «Моя страница»: от чьего имени человек действует, того и
        настройки. Переключил себя на организацию — открываются настройки
        организации.

        Вкладка передаётся внешним именем представления: вкладки раздела
        собираются из пунктов меню, у каждого своё действие, а код у них
        один.
        """
        partner = self.env.user._coop_acting_partner()
        view = self.env.ref(view_xmlid, raise_if_not_found=False)
        return {
            'type': 'ir.actions.act_window',
            'name': name or _('Настройки'),
            'res_model': 'res.partner',
            'res_id': partner.id,
            'view_mode': 'form',
            'views': [(view.id if view else False, 'form')],
            'target': 'current',
            'context': {'coop_settings': True},
        }
