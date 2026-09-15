# -*- coding: utf-8 -*-
"""Окно отклика на вакансию.

Отдельная временная модель, а не поле на самой вакансии: отклик пишет
не хозяин записи, и давать ему право писать в вакансию ради одного
текста нельзя. Окно живёт ровно столько, сколько открыто, и всё, что из
него выходит, — одна строка отклика.
"""

from odoo import _, fields, models


class CoopVacancyApply(models.TransientModel):
    _name = 'coop.vacancy.apply'
    _description = 'Отклик на вакансию'

    vacancy_id = fields.Many2one(
        'coop.vacancy', string='Вакансия', required=True, readonly=True)
    message = fields.Text(
        string='Пара слов о себе',
        help='Необязательно. Наниматель видит это рядом с вашим именем.')

    def action_send(self):
        self.ensure_one()
        self.vacancy_id._do_apply(self.message)
        # Закрытие окна перерисовывает экран под ним, и карточка вакансии
        # сразу показывает «Вы откликнулись» вместо кнопки.
        return {'type': 'ir.actions.act_window_close'}

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}
