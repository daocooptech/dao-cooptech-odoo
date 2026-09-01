# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ResPartner(models.Model):
    """Организация как участник платформы.

    Та же модель, что и человек, с признаком компании. Это не экономия на
    моделях: организация выступает стороной сделки наравне с человеком, и
    если развести их на две модели, каждую сделку придётся описывать
    дважды — отдельно для людей, отдельно для организаций.
    """
    _inherit = 'res.partner'

    # ── Реквизиты ────────────────────────────────────────────────────────
    #
    # ИНН и ОГРН хранятся отдельно от штатного vat. В vat Odoo кладёт
    # налоговый номер в международном формате («RU7707083893»), и он же
    # используется в проверках контрагентов. Российской организации в
    # каталоге нужен именно ИНН как он написан в выписке, без префикса.
    coop_inn = fields.Char(
        string='ИНН', size=12, index=True,
        help='10 цифр у организации, 12 у индивидуального предпринимателя.')
    coop_kpp = fields.Char(string='КПП', size=9)
    coop_ogrn = fields.Char(
        string='ОГРН', size=15,
        help='13 цифр у организации, 15 у индивидуального предпринимателя.')
    coop_registered_on = fields.Date(string='Дата регистрации')

    coop_charter_url = fields.Char(
        string='Устав',
        help='Ссылка на действующую редакцию устава. Для кооператива это '
             'не формальность: правила приёма, голосования и распределения '
             'записаны там, а не на платформе.')

    # Знак бывает двух видов: символ рода занятий во весь кадр или буква
    # названия с символом над ней. Оба заливают плитку целиком — поле
    # различает только рисунок, а не способ показа.
    coop_symbol_mark = fields.Boolean(
        string='Знак-символ', default=False,
        help='Установлено, если знак организации — символ рода занятий. '
             'Снято, если это буква названия.')

    # ── Состав ───────────────────────────────────────────────────────────
    coop_member_ids = fields.One2many(
        'coop.membership', 'organization_id', string='Состав')
    coop_member_count = fields.Integer(
        string='Участников', compute='_compute_coop_member_count', store=True)
    coop_has_members = fields.Boolean(
        string='Форма предполагает членство',
        related='coop_legal_form_id.has_members', store=True,
        help='У фонда и АНО членства нет вовсе, у кооператива и ТСЖ есть. '
             'От этого зависит, показывать ли раздел состава.')

    @api.depends('coop_member_ids.state')
    def _compute_coop_member_count(self):
        # Через sudo намеренно. Число участников — публичная величина, она
        # есть в уставе и в выписке; закрыт поимённый состав. Без sudo
        # пересчёт у пользователя без прав на членство ронял бы чтение
        # самой карточки организации, а не только состава.
        counts = {
            group['organization_id'][0]: group['__count']
            for group in self.env['coop.membership'].sudo()._read_group(
                [('organization_id', 'in', self.ids), ('state', '=', 'active')],
                groupby=['organization_id'], aggregates=['__count'])
        } if self.ids else {}
        for record in self:
            record.coop_member_count = counts.get(record.id, 0)

    def action_coop_members(self):
        """Открыть состав организации."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Состав: %s') % self.name,
            'res_model': 'coop.membership',
            'view_mode': 'list,form',
            'domain': [('organization_id', '=', self.id)],
            'context': {'default_organization_id': self.id},
        }

    def action_coop_org_message(self):
        """Написать организации."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Написать: %s') % self.name,
            'res_model': 'discuss.channel',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_channel_partner_ids': [(4, self.id)]},
        }

    def action_coop_org_follow(self):
        """Подписаться на организацию или отписаться.

        Дружбы у организаций нет — она бывает только между людьми. Здесь
        подписка означает «следить за лентой»: за новыми ресурсами,
        вакансиями и объявлениями.
        """
        self.ensure_one()
        me = self.env.user.partner_id
        if me in self.message_partner_ids:
            self.message_unsubscribe(partner_ids=me.ids)
        else:
            self.message_subscribe(partner_ids=me.ids)
        return True

    coop_org_is_following = fields.Boolean(
        string='Я подписан на организацию', compute='_compute_org_following')

    def _compute_org_following(self):
        me = self.env.user.partner_id
        for record in self:
            record.coop_org_is_following = me in record.message_partner_ids
