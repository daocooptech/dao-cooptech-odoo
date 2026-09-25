# -*- coding: utf-8 -*-
"""Условия объявления по способу передачи.

Решение 412 (Н5), владелец 25 сентября 2026: «надо добавить условия для
продажи, для аренды, для бартера и т. п.». У продажи и аренды одной вещи
разная цена, у аренды — залог и срок, у обмена — что возьмёшь взамен;
одна цена на всё объявление этого не выражает.

Строка условий — на каждый отмеченный способ; заводится и снимается сама,
вслед за «Способами передачи».
"""
from markupsafe import Markup

from odoo import api, fields, models


class CoopResourceTerm(models.Model):
    _name = 'coop.resource.term'
    _description = 'Условия объявления по способу передачи'
    _order = 'sequence, id'

    resource_id = fields.Many2one('coop.resource', string='Объявление', required=True,
                                  ondelete='cascade', index=True)
    method_id = fields.Many2one('coop.resource.method', string='Способ', required=True,
                                ondelete='cascade')
    code = fields.Char(related='method_id.code', store=True)
    sequence = fields.Integer(related='method_id.sequence', store=True)
    is_monetary = fields.Boolean(related='method_id.is_monetary')
    currency_id = fields.Many2one(related='resource_id.currency_id')
    price = fields.Monetary(string='Цена')
    price_unit_label = fields.Char(string='За что', help='шт., кг, сутки, месяц')
    deposit = fields.Monetary(string='Залог')
    min_term = fields.Char(string='Срок', help='Минимальный срок аренды, рассрочки, лизинга.')
    note = fields.Char(string='Условия')
    summary = fields.Char(string='Кратко', compute='_compute_summary')

    _one_per_method = models.Constraint('unique(resource_id, method_id)',
                                        'Условия этого способа уже есть.')

    @api.depends('price', 'price_unit_label', 'deposit', 'min_term', 'note', 'method_id')
    def _compute_summary(self):
        for term in self:
            parts = []
            if term.price:
                amount = '{:,.0f} ₽'.format(term.price).replace(',', ' ')
                parts.append('%s за %s' % (amount, term.price_unit_label)
                             if term.price_unit_label else amount)
            if term.deposit:
                parts.append('залог {:,.0f} ₽'.format(term.deposit).replace(',', ' '))
            if term.min_term:
                parts.append('срок %s' % term.min_term)
            if term.note:
                parts.append(term.note)
            term.summary = '; '.join(parts)


class CoopResource(models.Model):
    _inherit = 'coop.resource'

    term_ids = fields.One2many('coop.resource.term', 'resource_id', string='Условия по способам')
    terms_html = fields.Html(string='Условия', compute='_compute_terms_html', sanitize=False)

    @api.depends('term_ids.summary', 'method_ids')
    def _compute_terms_html(self):
        """Опубликованное показывает только выбранное (Н6): способы, которые
        владелец отметил, и только заполненные условия — без пустых строк
        и без вариантов, которых он не выбирал."""
        for resource in self:
            rows = []
            for term in resource.term_ids.sorted('sequence'):
                rows.append(Markup('<li><b>%s</b>%s</li>') % (
                    term.method_id.name,
                    Markup(' — %s') % term.summary if term.summary else ''))
            resource.terms_html = Markup('<ul class="o_coop_res_terms">%s</ul>') % \
                Markup('').join(rows) if rows else False

    def _coop_sync_terms(self):
        """Строка условий на каждый отмеченный способ — не больше и не меньше."""
        Term = self.env['coop.resource.term'].sudo()
        for resource in self:
            have = resource.term_ids
            wanted = resource.method_ids
            have.filtered(lambda t: t.method_id not in wanted).sudo().unlink()
            missing = wanted - have.method_id
            if missing:
                Term.create([{'resource_id': resource.id, 'method_id': method.id}
                             for method in missing])

    @api.model_create_multi
    def create(self, vals_list):
        resources = super().create(vals_list)
        resources.filtered('method_ids')._coop_sync_terms()
        return resources

    def write(self, vals):
        result = super().write(vals)
        if 'method_ids' in vals:
            self._coop_sync_terms()
        return result
