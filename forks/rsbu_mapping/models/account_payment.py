from odoo import api, fields, models
from ..resolvers.registry import get_resolver


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    rsbu_vat_amount = fields.Monetary(
        string='В том числе НДС', currency_field='currency_id',
        help='Сумма НДС в составе платежа (для авансового НДС). '
             'Заполняется вручную или при загрузке банковской выписки.')
    rsbu_template_id = fields.Many2one(
        'rsbu.operation.template', string='Шаблон РСБУ',
        compute='_compute_rsbu_template_id', store=True, readonly=False,
        copy=False)

    @api.depends('payment_type', 'state')
    def _compute_rsbu_template_id(self):
        for payment in self:
            if payment.rsbu_template_id:
                continue
            payment.rsbu_template_id = payment._rsbu_detect_template()

    # ------------------------------------------------------------------
    # Классификация
    # ------------------------------------------------------------------
    def _rsbu_doc_kind(self):
        self.ensure_one()
        return 'payment_inbound' if self.payment_type == 'inbound' \
            else 'payment_outbound'

    def _rsbu_has_advance(self):
        self.ensure_one()
        # Признак используется матрицей лишь при has_advance != 'any'.
        # Для клиентских платежей тип (аванс/постоплата/переплата) определяет
        # резолвер customer_payment по сальдо дебиторки на дату платежа, а
        # матрица ведёт на один шаблон (has_advance='any'), поэтому этот
        # признак на выбор шаблона клиентского платежа не влияет.
        return self.payment_type == 'inbound' \
            and self.partner_type == 'customer'

    def _rsbu_partner_kind(self):
        self.ensure_one()
        return self.partner_type or 'any'

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
