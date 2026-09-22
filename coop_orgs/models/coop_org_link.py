# -*- coding: utf-8 -*-
"""Связь между организациями.

В макете на карточке каждой организации есть полка «Связанные
организации» — с кем она работает: союз, в который входит, учредитель,
дочернее хозяйство, постоянный поставщик. Владелец 15 сентября 2026
назвал её в числе того, что надо взять из макета.

Своей записью, а не полем-списком, потому что связь несёт смысл: «входит
в союз» и «поставщик» — разные отношения, и показывать их одной кучей
значит не сказать ничего. У связи есть вид, пояснение и подтверждение со
второй стороны.

Связь двусторонняя по природе: если «Заря» входит в «Союз кооперативов»,
то у союза «Заря» — член. Поэтому запись одна, а на карточках она видна с
обеих сторон, каждой своим словом.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Вид связи и как он читается с каждой стороны.
#
# Первое слово — от лица того, кто связь завёл (сторона «А»), второе —
# от лица второй. «Входит в союз» с одной стороны и «Член союза» с
# другой — это одна и та же запись, а не две.
KINDS = [
    ('union', 'Входит в союз'),
    ('member', 'Член объединения'),
    ('founder', 'Учредитель'),
    ('subsidiary', 'Дочерняя организация'),
    ('supplier', 'Поставщик'),
    ('customer', 'Покупатель'),
    ('partner', 'Партнёр'),
]

BACK = {
    'union': 'member',
    'member': 'union',
    'founder': 'subsidiary',
    'subsidiary': 'founder',
    'supplier': 'customer',
    'customer': 'supplier',
    'partner': 'partner',
}


class CoopOrgLink(models.Model):
    _name = 'coop.org.link'
    _description = 'Связь между организациями'
    _order = 'kind, id desc'

    org_id = fields.Many2one(
        'res.partner', string='Организация', required=True, index=True,
        ondelete='cascade', domain=[('is_company', '=', True)])
    other_id = fields.Many2one(
        'res.partner', string='Связанная организация', required=True,
        index=True, ondelete='cascade', domain=[('is_company', '=', True)])
    kind = fields.Selection(
        KINDS, string='Вид связи', required=True, default='partner',
        help='Как первая организация относится ко второй. Обратное '
             'отношение выводится само.')
    note = fields.Char(string='Пояснение')
    # Подтверждение второй стороной. Без него связь — заявление одной
    # стороны: любая организация могла бы объявить себя учредителем
    # чужого кооператива, и на его карточке это бы висело.
    confirmed = fields.Boolean(
        string='Подтверждена', default=False,
        help='Вторая сторона согласилась, что связь есть.')

    _sql_constraints = [
        ('coop_org_link_uniq', 'unique(org_id, other_id, kind)',
         'Такая связь между этими организациями уже заведена.'),
    ]

    @api.constrains('org_id', 'other_id')
    def _check_not_self(self):
        for record in self:
            if record.org_id == record.other_id:
                raise ValidationError(_(
                    'Организация не может быть связана сама с собой.'))

    def kind_from(self, partner):
        """Как эта связь читается со стороны данной организации."""
        self.ensure_one()
        captions = dict(KINDS)
        if partner == self.org_id:
            return captions.get(self.kind, '')
        return captions.get(BACK.get(self.kind, self.kind), '')

    def action_confirm(self):
        """Подтвердить связь со второй стороны."""
        for record in self:
            if not self.env.user.coop_has_power('represent', record.other_id):
                raise UserError(_(
                    'Подтвердить связь может тот, кому доверено '
                    'представлять «%s».') % record.other_id.display_name)
        self.sudo().write({'confirmed': True})
        return True
