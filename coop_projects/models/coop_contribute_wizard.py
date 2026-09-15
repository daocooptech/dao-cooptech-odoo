# -*- coding: utf-8 -*-
"""Окно вклада в проект.

Вклад был описан моделью до последней мелочи — вид, оценка, возврат,
окно отзыва, — но внести его участник не мог: на странице проекта есть
только действия инициатора, а «Предложения на потребность» открывает тот
же инициатор, чтобы утвердить одно из них. Сам проект при этом собирает
деньги и вещи — и собирать их было неоткуда.

Проверено 15 сентября 2026: на карточке проекта и в его форме нет ни
одной кнопки участника.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopContributeWizard(models.TransientModel):
    _name = 'coop.project.contribute'
    _description = 'Вклад в проект'

    project_id = fields.Many2one(
        'coop.project', string='Проект', required=True, readonly=True)
    currency_id = fields.Many2one(
        related='project_id.currency_id', readonly=True)
    kind = fields.Selection([
        ('money', 'Деньги'),
        ('labour', 'Труд'),
        ('resource', 'Ресурс или техника'),
        ('material', 'Материалы'),
        ('space', 'Помещение'),
        ('knowledge', 'Знания и документация'),
    ], string='Чем', required=True, default='money')
    name = fields.Char(
        string='Что именно', required=True,
        help='Смена экскаваторщика, месяц аренды склада, комплект досок.')
    value = fields.Monetary(
        string='Оценка, ₽', currency_field='currency_id', required=True,
        help='Денежная оценка вклада. Только через неё труд и деньги '
             'сводятся в одну величину, из которой считается доля.')
    note = fields.Text(string='Пара слов инициатору')

    @api.onchange('kind')
    def _onchange_kind(self):
        """Деньгам название не нужно — оно и есть сумма."""
        for wizard in self:
            if wizard.kind == 'money' and not wizard.name:
                wizard.name = _('Денежный вклад')

    def action_offer(self):
        self.ensure_one()
        проект = self.project_id
        if проект.state != 'gathering':
            raise UserError(_(
                'Вложиться можно в проект, который собирает. Сейчас он в '
                'состоянии «%s».') % dict(
                    проект._fields['state'].selection).get(проект.state))
        я = self.env.user._coop_acting_partner()
        if проект.partner_id == я:
            raise UserError(_(
                'Это ваш проект. Вклад инициатора учитывается сметой, а не '
                'предложением самому себе.'))

        вклад = self.env['coop.project.contribution'].sudo().create({
            'project_id': проект.id,
            'partner_id': я.id,
            'kind': self.kind,
            'name': self.name,
            'value': self.value,
            'state': 'offered',
        })

        # Инициатору — иначе предложение лежит в проекте, и о нём никто
        # не знает: вкладчик ждёт ответа, проект стоит недособранным.
        тело = _('Вклад в проект «%(проект)s»: %(что)s на %(сколько)s ₽ '
                 'от %(кто)s.',
                 проект=проект.name, что=self.name, сколько=self.value,
                 кто=я.display_name)
        if self.note:
            тело = '%s %s' % (тело, self.note)
        self.env['coop.notification']._notify(
            проект.partner_id, тело, record=проект, kind='project')
        # След в ленте проекта — через sudo: проект чужой, и права писать
        # в него у вкладчика нет.
        проект.sudo().message_post(body=тело)
        return {'type': 'ir.actions.act_window_close'}
