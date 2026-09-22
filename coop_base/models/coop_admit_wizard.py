# -*- coding: utf-8 -*-
"""Окно приёма в организацию.

Приём в члены — решение органа управления, и без ссылки на это решение
запись о членстве не имеет силы: так говорит `_check_admission_basis` на
самой модели. Кнопка «Принять» без окна упиралась в эту проверку —
человек нажимал и получал ошибку вместо приёма.

Здесь же решается второе: организация принимает не обязательно тем, кем
человек попросился. Пайщик вносит пай и получает голос, наёмный
сотрудник — ни того ни другого; правление вправе предложить другое
основание, и заявление этому не указ.
"""

from odoo import _, fields, models


class CoopAdmitWizard(models.TransientModel):
    _name = 'coop.membership.admit'
    _description = 'Приём в организацию'

    membership_id = fields.Many2one(
        'coop.membership', string='Заявление', required=True, readonly=True)
    partner_id = fields.Many2one(
        related='membership_id.partner_id', string='Кого принимаем',
        readonly=True)
    organization_id = fields.Many2one(
        related='membership_id.organization_id', string='В организацию',
        readonly=True)
    # Показываем запись справочника, а не код: роль стала
    # `coop.membership.role` (решение 371), и связанное поле
    # обязано иметь тот же тип, что источник.
    role_id = fields.Many2one(
        related='membership_id.role_id', string='Основание участия',
        readonly=False)
    # Чем ограничен выбор — берём у самого членства, чтобы правило
    # «пайщик бывает в кооперативе» было одно на всю платформу, а не
    # переписывалось в каждом мастере заново.
    allowed_role_ids = fields.Many2many(
        related='membership_id.allowed_role_ids',
        string='Подходящие роли', readonly=True)
    job_title = fields.Char(
        related='membership_id.job_title', string='Должность', readonly=False)
    admission_basis = fields.Char(
        string='Основание приёма', required=True,
        help='Решение общего собрания или правления: номер и дата протокола.')
    has_vote = fields.Boolean(
        related='membership_id.has_vote', string='Право голоса',
        readonly=False)

    def action_confirm(self):
        self.ensure_one()
        membership = self.membership_id
        # Полномочие проверяет сама модель — одной проверкой и для кнопки,
        # и для вызова со стороны.
        membership._check_can_decide()
        membership.sudo().write({'admission_basis': self.admission_basis})
        membership.action_admit()
        return {'type': 'ir.actions.act_window_close'}
