# -*- coding: utf-8 -*-
"""Роль в организации — запись справочника, а не строка в коде.

Решение 371 от 22 сентября 2026, исполняющее решение 180 от 2 сентября:
**роль ограничивается правовой формой организации**. До этого роль была
единым перечислением на все формы, и пайщик заводился в ООО
беспрепятственно — ровно то, что решение 180 называло проблемой.

Почему справочником, а не проверкой в коде. Проверка дешевле на день
работы, но замораживает право в питоне: появится новая правовая форма —
и роли для неё придётся дописывать в модуль. Правовые формы меняются
вместе с законом, а не вместе с нашими планами; справочник это
переживёт, `if` в модели — нет.

Код роли остался прежним (`member`, `board`, `audit`…): на него опираются
правила доступа в четырёх модулях, и менять их ради переименования
значило бы трогать права там, где к ним нет вопросов.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CoopMembershipRole(models.Model):
    _name = 'coop.membership.role'
    _description = 'Роль участия в организации'
    _order = 'sequence, name'

    name = fields.Char(string='Название', required=True, translate=True)
    code = fields.Char(
        string='Код', required=True, index=True,
        help='На код опираются правила доступа. Менять у заведённой роли '
             'нельзя — права перестанут находить её носителей.')
    sequence = fields.Integer(string='Порядок', default=10)
    active = fields.Boolean(default=True)

    group_ids = fields.Many2many(
        'coop.legal.form.group', 'coop_membership_role_group_rel',
        'role_id', 'group_id', string='В каких формах бывает',
        help='Пусто — роль годится в организации любой формы. Заполнено — '
             'только в перечисленных.')

    description = fields.Char(
        string='Пояснение',
        help='Чем эта роль отличается от соседних — человеку, который '
             'выбирает её впервые.')

    _code_unique = models.Constraint(
        'unique(code)',
        'Код роли занят: два разных основания участия под одним кодом '
        'сделают права неразрешимыми.',
    )

    @api.constrains('code')
    def _check_code_latin(self):
        """Код — латиницей и без пробелов.

        На код опираются домены правил доступа, а туда он попадает
        строкой. Кириллица в машинном имени однажды уронила платформу
        целиком (решение 352), и справочник, который её допускает, —
        приглашение повторить.
        """
        for record in self:
            code = (record.code or '').strip()
            if not code or not code.replace('_', '').isalnum() \
                    or not code.isascii():
                raise ValidationError(_(
                    'Код роли «%s» не годится: только латинские буквы, '
                    'цифры и подчёркивание.') % record.code)

    def fits_group(self, group):
        """Годится ли роль организации такой формы."""
        self.ensure_one()
        return not self.group_ids or group in self.group_ids
