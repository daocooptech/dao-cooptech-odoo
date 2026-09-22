# -*- coding: utf-8 -*-
"""Окно отзыва по сделке.

Отзывы были заведены моделью, но оставить их было негде: на вкладке
сделки лежал редактируемый список, где человек должен был сам выбрать,
кто кого оценивает. Обе стороны сделки известны, оценивает всегда тот,
кто нажал, а оценивают вторую сторону — спрашивать тут нечего, кроме
самой оценки и пары слов.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopDealReviewWizard(models.TransientModel):
    _name = 'coop.deal.review.wizard'
    _description = 'Отзыв по сделке'

    deal_id = fields.Many2one(
        'coop.deal', string='Сделка', required=True, readonly=True)
    target_id = fields.Many2one(
        'res.partner', string='Кого оцениваете', readonly=True,
        compute='_compute_target', store=False)
    rating = fields.Selection([
        ('5', 'Отлично'),
        ('4', 'Хорошо'),
        ('3', 'Нормально'),
        ('2', 'Так себе'),
        ('1', 'Плохо'),
    ], string='Оценка', required=True, default='5')
    body = fields.Text(
        string='Пара слов',
        help='Что получилось и что стоило бы сделать иначе. Необязательно.')

    @api.depends('deal_id')
    def _compute_target(self):
        for wizard in self:
            wizard.target_id = wizard.deal_id._other_partner()

    def action_send(self):
        self.ensure_one()
        deal = self.deal_id
        target = deal._other_partner()
        if not target:
            raise UserError(_('Не видно второй стороны сделки.'))
        self.env['coop.deal.review'].create({
            'deal_id': deal.id,
            'author_id': self.env.user._coop_acting_partner().id,
            'target_id': target.id,
            'rating': self.rating,
            'body': self.body,
        })
        return {'type': 'ir.actions.act_window_close'}
