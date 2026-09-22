# -*- coding: utf-8 -*-
"""Окно приобретения цифрового финансового актива.

В макете (`cfa-asset.html`) на карточке актива стоит «Приобрести».
Модель владения описана — количество, оценка, срок погашения, — а
приобрести актив участник не мог: все действия раздела были
эмитентскими и операторскими.

Окном, а не кнопкой сразу: сколько единиц берётся — не мелочь, от этого
зависит и сумма, и запись в реестре держателей.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopCfaBuy(models.TransientModel):
    _name = 'coop.cfa.buy'
    _description = 'Приобретение цифрового актива'

    issue_id = fields.Many2one(
        'coop.cfa.issue', string='Выпуск', required=True, readonly=True)
    currency_id = fields.Many2one(
        related='issue_id.currency_id', readonly=True)
    unit_price = fields.Monetary(
        related='issue_id.unit_price', string='Цена за единицу', readonly=True)
    quantity = fields.Float(
        string='Сколько единиц', required=True, default=1.0, digits=(16, 3))
    total = fields.Monetary(
        string='К оплате', compute='_compute_total',
        currency_field='currency_id')

    @api.depends('quantity', 'unit_price')
    def _compute_total(self):
        for wizard in self:
            wizard.total = (wizard.quantity or 0.0) * (wizard.unit_price or 0.0)

    def action_buy(self):
        self.ensure_one()
        issue = self.issue_id
        me = self.env.user._coop_acting_partner()

        if issue.state != 'issued':
            raise UserError(_(
                'Приобрести можно выпущенный актив. Сейчас он в состоянии '
                '«%s».') % dict(
                    issue._fields['state'].selection)[issue.state])
        if issue.issuer_id == me:
            raise UserError(_(
                'Это ваш выпуск. Эмитент не приобретает собственный актив: '
                'невыкупленное и так остаётся за ним.'))
        if self.quantity <= 0:
            raise UserError(_('Количество должно быть больше нуля.'))

        # Реестр держателей ведёт оператор — так устроен закон о ЦФА, — и
        # запись о владении заводится от его имени. Но начинается
        # приобретение здесь: иначе выпуск некому купить.
        Holding = self.env['coop.cfa.holding'].sudo()
        ownership = Holding.create({
            'partner_id': me.id,
            'issue_id': issue.id,
            'operator_id': issue.operator_id.id,
            'name': issue.display_name,
            'quantity': self.quantity,
            'value': self.total,
        })

        body = _('Приобретение «%(what)s»: %(how_many)s ед. на %(amount)s ₽ '
                 'от %(who)s.',
                 what=issue.display_name, how_many=self.quantity,
                 amount=self.total, who=me.display_name)
        self.env['coop.notification']._notify(
            issue.issuer_id, body, record=issue, kind='other')
        issue.sudo().message_post(body=body)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Моё владение'),
            'res_model': 'coop.cfa.holding',
            'res_id': ownership.id,
            'view_mode': 'form',
            'target': 'current',
        }
