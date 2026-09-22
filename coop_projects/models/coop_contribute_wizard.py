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
    # Вид проекта решает, чем считается принятый вклад: паем, долей или
    # ничем. Обещать долю в некоммерческом проекте нельзя даже вскользь.
    project_kind = fields.Selection(
        related='project_id.kind', readonly=True)
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
    # Заполнено, когда пришли из строки потребности. Тогда
    # предложение видно ответственному за неё, а не только
    # инициатору проекта, и утверждение одного закрывает строку.
    need_id = fields.Many2one(
        'coop.resource', string='Потребность', readonly=True)

    @api.onchange('kind')
    def _onchange_kind(self):
        """Деньгам название не нужно — оно и есть сумма."""
        for wizard in self:
            if wizard.kind == 'money' and not wizard.name:
                wizard.name = _('Денежный вклад')

    def action_offer(self):
        self.ensure_one()
        project = self.project_id
        if project.state != 'gathering':
            raise UserError(_(
                'Вложиться можно в проект, который собирает. Сейчас он в '
                'состоянии «%s».') % dict(
                    project._fields['state'].selection).get(project.state))
        me = self.env.user._coop_acting_partner()
        if project.partner_id == me:
            raise UserError(_(
                'Это ваш проект. Вклад инициатора учитывается сметой, а не '
                'предложением самому себе.'))

        contribution = self.env['coop.project.contribution'].sudo().create({
            'project_id': project.id,
            'need_id': self.need_id.id,
            'partner_id': me.id,
            'kind': self.kind,
            'name': self.name,
            'value': self.value,
            'state': 'offered',
        })

        # Инициатору — иначе предложение лежит в проекте, и о нём никто
        # не знает: вкладчик ждёт ответа, проект стоит недособранным.
        body = _('Вклад в проект «%(project)s»: %(what)s на %(how_many)s ₽ '
                 'от %(who)s.',
                 project=project.name, what=self.name, how_many=self.value,
                 who=me.display_name)
        if self.note:
            body = '%s %s' % (body, self.note)
        # Ответственному за потребность — если участие пришло на
        # строку. Инициатор проекта с тремя десятками потребностей
        # иначе остаётся единственным, кто вообще об этом узнает.
        to_whom = project.partner_id
        if self.need_id:
            to_whom |= self.need_id._need_deciders()
        self.env['coop.notification']._notify(
            to_whom, body, record=project, kind='project')
        # След в ленте проекта — через sudo: проект чужой, и права писать
        # в него у вкладчика нет.
        project.sudo().message_post(body=body)
        return {'type': 'ir.actions.act_window_close'}
