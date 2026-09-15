# -*- coding: utf-8 -*-
"""Извещения участника.

Платформа до этого не умела сообщать человеку ничего. Всё, что
происходило с его записями, писалось в ленту самой записи: откликнулись
на вакансию — наниматель узнавал об этом, только открыв вакансию;
пригласили — соискатель не узнавал вовсе; перебили ставку — участник
торга тоже. Взаимодействие двоих обрывалось ровно посередине: одна
сторона действовала, вторая об этом не знала.

Отдельная модель, а не чужая лента и не переписка. Решение владельца от
15 сентября 2026: у извещений свой раздел. Переписка — разговор, где
ждут ответа; извещение — след события, на который отвечать не надо, и
смешивать их значит хоронить одно в другом.

Своя модель, а не `mail.activity` и не `mail.message`: активность — это
задача с исполнителем и сроком, а сообщение адресовано подписчикам
записи, тогда как извещение адресовано человеку и живёт в его списке
независимо от того, подписан он на что-нибудь или нет.
"""

from odoo import _, api, fields, models


class CoopNotification(models.Model):
    _name = 'coop.notification'
    _description = 'Извещение участника'
    _order = 'create_date desc, id desc'

    partner_id = fields.Many2one(
        'res.partner', string='Кому', required=True, index=True,
        ondelete='cascade')
    body = fields.Html(
        string='Событие', required=True, sanitize=True,
        help='Текст со ссылками на записи, которых событие касается.')
    kind = fields.Selection([
        ('vacancy', 'Вакансии'),
        ('auction', 'Торги'),
        ('deal', 'Сделки'),
        ('project', 'Проекты'),
        ('community', 'Сообщества'),
        ('resource', 'Ресурсы'),
        ('org', 'Организации'),
        ('wallet', 'Кошелёк'),
        ('other', 'Прочее'),
    ], string='О чём', default='other', required=True, index=True)

    # На что ссылается. Пара «модель и номер», а не связь: извещения
    # приходят о записях из полутора десятков моделей, и заводить под
    # каждую своё поле значило бы переписывать модель при появлении
    # шестнадцатой.
    res_model = fields.Char(string='Модель записи')
    res_id = fields.Integer(string='Номер записи')

    is_read = fields.Boolean(string='Прочитано', default=False, index=True)
    read_on = fields.Datetime(string='Когда прочитано', readonly=True)

    @api.model
    def _notify(self, partners, body, record=None, kind='other'):
        """Известить участников.

        Через sudo: извещение пишется тому, кто в этот момент ничего не
        делает, — нанимателю о чужом отклике, прежнему лидеру о чужой
        ставке. Прав писать в его список у действующего нет и быть не
        должно, иначе любое действие упиралось бы в отказ доступа — так
        уже вышло с записью в чужую ленту у отклика и у ставки.

        Себе извещений не пишем: человек и так знает, что сделал.
        """
        partners = partners.exists() if partners else partners
        if not partners:
            return self.browse()
        я = self.env.user._coop_acting_partner() if hasattr(
            self.env.user, '_coop_acting_partner') else self.env.user.partner_id
        значения = []
        for partner in partners:
            if partner == я:
                continue
            строка = {
                'partner_id': partner.id,
                'body': body,
                'kind': kind,
            }
            if record is not None and record:
                строка['res_model'] = record._name
                строка['res_id'] = record.id
            значения.append(строка)
        if not значения:
            return self.browse()
        return self.sudo().create(значения)

    @api.model
    def unread_count(self):
        """Сколько непрочитанного у того, кто сейчас смотрит.

        Имя без подчёркивания намеренно: Odoo не отдаёт наружу методы,
        начинающиеся с него, — «Private methods cannot be called
        remotely», — а счётчик в шапке спрашивает именно снаружи.
        """
        partner = self.env.user._coop_acting_partner() if hasattr(
            self.env.user, '_coop_acting_partner') else self.env.user.partner_id
        return self.search_count([
            ('partner_id', '=', partner.id), ('is_read', '=', False)])

    def action_open(self):
        """Открыть запись, о которой извещение, и погасить точку."""
        self.ensure_one()
        self.mark_read()
        if not self.res_model or not self.res_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'views': [[False, 'form']],
        }

    def mark_read(self):
        непрочитанные = self.filtered(lambda n: not n.is_read)
        if непрочитанные:
            непрочитанные.write({
                'is_read': True,
                'read_on': fields.Datetime.now(),
            })
        return True

    @api.model
    def action_mark_all_read(self):
        """Погасить все точки разом.

        Список на сотню событий иначе не разобрать: гасить по одному —
        работа, которая не даёт человеку ничего.
        """
        partner = self.env.user._coop_acting_partner() if hasattr(
            self.env.user, '_coop_acting_partner') else self.env.user.partner_id
        self.search([
            ('partner_id', '=', partner.id), ('is_read', '=', False),
        ]).mark_read()
        return True
