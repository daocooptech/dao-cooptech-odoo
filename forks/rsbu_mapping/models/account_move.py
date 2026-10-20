from odoo import api, fields, models
from ..resolvers.registry import get_resolver


class AccountMove(models.Model):
    _inherit = 'account.move'

    rsbu_template_id = fields.Many2one(
        'rsbu.operation.template', string='Шаблон РСБУ',
        compute='_compute_rsbu_template_id', store=True, readonly=False,
        copy=False)

    @api.depends('move_type', 'state', 'line_ids')
    def _compute_rsbu_template_id(self):
        for move in self:
            if move.rsbu_template_id:
                # ручное переопределение сохраняем
                continue
            move.rsbu_template_id = move._rsbu_detect_template()

    # ------------------------------------------------------------------
    # Классификация
    # ------------------------------------------------------------------
    def _rsbu_doc_kind(self):
        self.ensure_one()
        return self.move_type

    def _rsbu_has_advance(self):
        self.ensure_one()
        return False

    def _rsbu_partner_kind(self):
        self.ensure_one()
        if self.move_type in ('out_invoice', 'out_refund'):
            return 'customer'
        if self.move_type in ('in_invoice', 'in_refund'):
            return 'supplier'
        return 'any'

    def _rsbu_detect_template(self):
        self.ensure_one()
        # sudo: детект — внутренняя механика; пользователь, проводящий
        # документ, может не иметь прав на РСБУ-модели.
        Matrix = self.env['rsbu.operation.matrix'].sudo()
        rules = Matrix.search([
            ('company_id', 'in', (False, self.company_id.id)),
        ], order='priority, id')
        for rule in rules:
            if rule._match(self):
                return rule.template_id
        return self.env['rsbu.operation.template'].sudo()

    # ------------------------------------------------------------------
    # Реализация точек миксина (Этап 3)
    # ------------------------------------------------------------------
    def _rsbu_is_applicable(self):
        self.ensure_one()
        return bool(self.rsbu_template_id or self._rsbu_detect_template())

    def _rsbu_build_lines(self):
        self.ensure_one()
        template = (self.rsbu_template_id or self._rsbu_detect_template()).sudo()
        if not template:
            return []
        fn = get_resolver(template.resolver_key)
        if not fn:
            return []
        return fn(self, template)
