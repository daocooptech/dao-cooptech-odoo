# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopFriendship(models.Model):
    """Связь между двумя участниками.

    В макете у человека две разные кнопки, и разница между ними
    существенная. «Подписаться» — односторонне: я слежу за человеком, его
    согласия не требуется, он об этом может и не знать. «Добавить в
    друзья» — двусторонне: связь появляется только когда вторая сторона
    согласилась. Подписка реализована штатными подписчиками Odoo, а для
    дружбы нужна собственная запись: у неё есть состояние ожидания, а у
    подписки его нет.

    Пара хранится один раз, в направлении «кто предложил → кому». Хранить
    обе стороны значит немедленно получить их расхождение.
    """
    _name = 'coop.friendship'
    _description = 'Дружба участников'
    _order = 'create_date desc'

    requester_id = fields.Many2one(
        'res.partner', string='Предложил', required=True,
        ondelete='cascade', index=True)
    addressee_id = fields.Many2one(
        'res.partner', string='Кому', required=True,
        ondelete='cascade', index=True)
    state = fields.Selection(
        [('pending', 'Ожидает ответа'),
         ('accepted', 'В друзьях'),
         ('declined', 'Отклонено')],
        string='Состояние', default='pending', required=True, index=True)

    _pair_uniq = models.Constraint(
        'unique(requester_id, addressee_id)',
        'Такое предложение дружбы уже отправлено.',
    )
    _not_self = models.Constraint(
        'check(requester_id != addressee_id)',
        'Нельзя добавить в друзья самого себя.',
    )

    @api.constrains('requester_id', 'addressee_id')
    def _check_reverse(self):
        """Запретить встречную запись по той же паре.

        Иначе двое, добавившие друг друга одновременно, окажутся в двух
        состояниях сразу: у одного «ожидает», у другого «в друзьях».
        """
        for record in self:
            reverse = self.search_count([
                ('requester_id', '=', record.addressee_id.id),
                ('addressee_id', '=', record.requester_id.id),
            ])
            if reverse:
                raise UserError(_(
                    'Эти двое уже связаны предложением дружбы — '
                    'встречное создавать не нужно.'))
