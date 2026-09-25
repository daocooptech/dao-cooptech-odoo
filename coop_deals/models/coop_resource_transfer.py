# -*- coding: utf-8 -*-
import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Способы сделки, при которых меняется собственник. Аренда и услуга права
# не передают — в историю прав они не попадают.
TRANSFER_WAYS = ('sale', 'batch', 'gift', 'exchange')
# Что вообще может иметь историю прав: вещь, а не труд и не деньги.
OWNABLE_TYPES = ('material', 'equipment')


def canonical(obj):
    """Каноническая запись тела — как в протоколе обмена узлов
    (`federation/ref/canonical.py` дизайн-макета). Дробных чисел нет:
    количество — строкой."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


class CoopResourceTransfer(models.Model):
    """История передачи прав собственности на ресурс.

    Макет, вкладка «Трекинг» ресурса: «неизменяемая история передачи
    прав» — постановка на учёт первичным владельцем, передача партнёру,
    продажи конечным покупателям; у каждой записи — хэш. В ревизии
    макета и MVP это пункт 9: на движке не было ничего.

    Запись заводится сама: при постановке ресурса на учёт и при
    завершении сделки, которая передаёт собственность. Руками её не
    завести и не поправить — это журнал, а не справочник: номер в цепочке
    ресурса (`seq`), хэш предыдущего (`prev_hash`) и хэш канонического тела
    (`hash`), как у события журнала узла (навык `federation-protocol`).
    Стороны в теле пока номерами участников этого узла; `did` появится
    вместе с обменом между узлами.
    """
    _name = 'coop.resource.transfer'
    _description = 'Передача прав на ресурс'
    _order = 'resource_id, seq'

    resource_id = fields.Many2one(
        'coop.resource', string='Ресурс', required=True, index=True,
        ondelete='cascade')
    deal_id = fields.Many2one(
        'coop.deal', string='Сделка', index=True, ondelete='set null')
    date = fields.Datetime(string='Когда', required=True, readonly=True)
    kind = fields.Selection([
        ('registered', 'Поставлен на учёт'),
        ('sale', 'Продажа'),
        ('batch', 'Продажа партией'),
        ('gift', 'Дар'),
        ('exchange', 'Обмен'),
    ], string='Что произошло', required=True, readonly=True)
    from_partner_id = fields.Many2one(
        'res.partner', string='От кого', readonly=True, ondelete='restrict')
    to_partner_id = fields.Many2one(
        'res.partner', string='Кому', required=True, readonly=True,
        ondelete='restrict')
    quantity = fields.Char(string='Сколько', readonly=True)
    seq = fields.Integer(string='Номер', required=True, readonly=True)
    prev_hash = fields.Char(string='Хэш предыдущего', readonly=True)
    hash = fields.Char(string='Хэш', required=True, readonly=True, index=True)
    hash_short = fields.Char(string='Запись', compute='_compute_hash_short')

    _one_per_deal = models.Constraint(
        'unique(resource_id, deal_id)',
        'Сделка уже записана в историю прав.')

    def _compute_hash_short(self):
        for record in self:
            h = record.hash or ''
            record.hash_short = '0x%s…%s' % (h[:8], h[-4:]) if h else ''

    # ── Журнал ───────────────────────────────────────────────────────

    @api.model
    def _coop_append(self, resource, kind, to_partner, date,
                     from_partner=None, deal=None, quantity=''):
        """Дописать запись в конец цепочки ресурса."""
        self.env.cr.execute(
            'SELECT id FROM coop_resource WHERE id = %s FOR UPDATE', [resource.id])
        last = self.sudo().search([('resource_id', '=', resource.id)],
                                  order='seq desc', limit=1)
        seq = (last.seq or 0) + 1
        prev = last.hash or ''
        body = {
            'type': 'resource.rights.%s' % kind,
            'resource': resource.id,
            'deal': deal.id if deal else 0,
            'from': from_partner.id if from_partner else 0,
            'to': to_partner.id,
            'quantity': quantity or '',
            'at': fields.Datetime.to_string(date),
            'seq': seq,
            'prev': prev,
        }
        return self.sudo().with_context(coop_transfer_append=True).create({
            'resource_id': resource.id,
            'deal_id': deal.id if deal else False,
            'date': date,
            'kind': kind,
            'from_partner_id': from_partner.id if from_partner else False,
            'to_partner_id': to_partner.id,
            'quantity': quantity or False,
            'seq': seq,
            'prev_hash': prev,
            'hash': hashlib.sha256(canonical(body)).hexdigest(),
        })

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('coop_transfer_append'):
            raise UserError(_("История прав пишется сама — сделкой, а не вручную."))
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_("Запись истории прав не меняется."))

    def unlink(self):
        # Уходит только вместе с ресурсом (каскад базы, мимо этого метода).
        raise UserError(_("Запись истории прав не удаляется."))


def _deal_quantity(deal):
    """«2 кг» из спецификации сделки — строкой, без дробных хвостов."""
    line = deal.line_ids[:1]
    if not line or not line.quantity:
        return ''
    qty = line.quantity
    text = ('%d' % qty) if float(qty).is_integer() else ('%.3f' % qty).rstrip('0').rstrip('.')
    return '%s %s' % (text.replace('.', ','), line.uom_name or '')


class CoopResource(models.Model):
    _inherit = 'coop.resource'

    coop_transfer_ids = fields.One2many(
        'coop.resource.transfer', 'resource_id', string='История прав')
    coop_has_rights_history = fields.Boolean(
        compute='_compute_coop_has_rights_history')

    def _compute_coop_has_rights_history(self):
        for resource in self:
            resource.coop_has_rights_history = (
                resource.listing_type == 'offer'
                and resource.resource_type in OWNABLE_TYPES)

    def _coop_register_rights(self, date=None):
        """Первая запись цепочки — постановка на учёт владельцем."""
        Transfer = self.env['coop.resource.transfer']
        for resource in self.sudo():
            if not resource.coop_has_rights_history or not resource.owner_id:
                continue
            if Transfer.sudo().search_count([('resource_id', '=', resource.id)], limit=1):
                continue
            Transfer._coop_append(
                resource, 'registered', resource.owner_id,
                date or resource.create_date or fields.Datetime.now())

    @api.model_create_multi
    def create(self, vals_list):
        resources = super().create(vals_list)
        resources._coop_register_rights()
        return resources


class CoopDeal(models.Model):
    _inherit = 'coop.deal'

    def write(self, vals):
        done_before = {deal.id for deal in self if deal.state == 'done'}
        result = super().write(vals)
        if vals.get('state') == 'done':
            (self.filtered(lambda d: d.id not in done_before))._coop_record_rights()
        return result

    def _coop_record_rights(self, date=None):
        """Сделка завершена — права перешли: запись в историю ресурса."""
        Transfer = self.env['coop.resource.transfer'].sudo()
        for deal in self.sudo():
            resource = deal.resource_id
            if (not resource or deal.way not in TRANSFER_WAYS
                    or not resource.coop_has_rights_history
                    or not deal.party_b_id):
                continue
            if Transfer.search_count([('resource_id', '=', resource.id),
                                      ('deal_id', '=', deal.id)], limit=1):
                continue
            resource._coop_register_rights()
            Transfer._coop_append(
                resource, deal.way, deal.party_b_id,
                date or fields.Datetime.now(),
                from_partner=deal.party_a_id, deal=deal,
                quantity=_deal_quantity(deal))
