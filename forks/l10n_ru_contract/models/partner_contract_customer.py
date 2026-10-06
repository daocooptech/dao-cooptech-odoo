from odoo import api, fields, models, tools, _

import logging
_logger = logging.getLogger(__name__)

class PartnerContractCustomer(models.Model):
    _name = 'partner.contract.customer'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'mail.render.mixin']

    name = fields.Char(string=_('Номер'))
    date_start = fields.Date(string=_('Дата договора'), required=True, default=fields.Datetime.now())
    date_end = fields.Date(string=_('Дата окончания'), required=True)
    type = fields.Selection(
        [('customer', 'С покупателем'),
         ('supplier', 'С поставщиком'),
         ('other', 'Прочие расчеты'),

         ],
        string=_('Тип договора'), default='customer', required=True)
    profile_id = fields.Many2one('contract.profile', string=_('Вид договора'), required=True)
    partner_id = fields.Many2one(
        'res.partner',
        string='Контрагент',
        required=True,
        domain="[('id', 'in', possible_partner_ids)]",
    )

    partner_type = fields.Selection(string=_('Тип контрагента'), selection=[
        ('person', 'Физ. лицо'),
        ('company_ip', 'ИП'),
        ('company', 'Юр. лицо')
    ], required=True)
    company_id = fields.Many2one('res.company', string=_('Компания'), required=True)
    state = fields.Selection(
        [
            ('draft', 'Черновик'),
            ('progress', 'На согласовании'),
            ('signed', 'Подписан, действует'),
            ('closed', 'Истёк'),
        ],
        string=_('Статус'),
        default='draft',
        group_expand=lambda self, states, domain: [
            key for key, _ in self._fields['state'].selection
        ],
    )
    stamp = fields.Boolean(string=_('Печать и подпись'))
    signed = fields.Boolean(string=_('Договор подписан'))
    lines_ids = fields.One2many('contract.line', 'contract_id', string=_('Пункты договора'))

    is_template = fields.Boolean(_('Это шаблон'))
    copy_from = fields.Many2one('partner.contract.customer', string=_('Копировать из этого шаблона'))

    director_name_partner = fields.Char(
        string=_('ФИО директора (от партнёра)'),
        related='partner_id.parent_id.name',
        readonly=True,
    )

    director_name_company = fields.Char(
        string=_('ФИО руководителя (от компании)'),
        related='company_id.chief_id.partner_id.name',
        readonly=True,
    )

    contract_header = fields.Html(
        string=_("Шапка договора"),
        compute="_compute_contract_header",
    )

    contract_header_template_id = fields.Many2one(
        "ir.ui.view",
        string=_("Шаблон шапки договора"),
        domain='['
               '("type", "=", "qweb"), '
               '"|", '
               '"&", ("model", "!=", False), ("model", "=", "partner.contract.customer"), '
               '"&", ("model", "=", False), ("key", "ilike", "l10n_ru_contract.contract_header_")'
               ']',
        help=_("QWeb-шаблон, по которому генерируется поле «Шапка договора»."),
    )

    use_custom_contract_header = fields.Boolean(
        string=_("Использовать кастомный шаблон"),
        default=False,
        help=_(
            "Если включено, шапка договора редактируется вручную и "
            "не перегенерируется автоматически при изменении реквизитов."
        ),
    )

    possible_partner_ids = fields.Many2many(
        'res.partner',
        compute='_compute_possible_partners',
        compute_sudo=True,
    )

    @api.depends('partner_type')
    def _compute_possible_partners(self):
        company_ids = self.env.companies.ids
        internal_user_partners = self.env['res.users'].sudo().search([
            ('share', '=', False)
        ]).mapped('partner_id.id')

        for rec in self:
            if rec.partner_type in ('company', 'company_ip'):
                rec.possible_partner_ids = self.env['res.partner'].search([
                    ('is_company', '=', True),
                    ('id', 'not in', company_ids),
                ])
            elif rec.partner_type == 'person':
                rec.possible_partner_ids = self.env['res.partner'].search([
                    ('is_company', '=', False),
                    ('id', 'not in', internal_user_partners),
                ])
            else:
                rec.possible_partner_ids = self.env['res.partner'].search([])

    @api.onchange('partner_type')
    def _onchange_partner_type(self):
        if self.partner_id:
            if self.partner_type in ('company', 'company_ip'):
                if not self.partner_id.is_company or self.partner_id.id in self.env.companies.ids:
                    self.partner_id = False
            elif self.partner_type == 'person':
                if self.partner_id.is_company or self.partner_id.id in self.env['res.users'].sudo().search(
                        [('share', '=', False)]).mapped('partner_id.id'):
                    self.partner_id = False

    def _get_default_header_xmlid(self):
        self.ensure_one()
        if self.partner_type == "company_ip":
            xmlid = "l10n_ru_contract.contract_header_ip"
        elif self.partner_type == "person":
            xmlid = "l10n_ru_contract.contract_header_individual"
        else:
            xmlid = "l10n_ru_contract.contract_header_entity"

        return xmlid

    def _render_header_qweb(self):
        self.ensure_one()
        view = self.contract_header_template_id
        if not view:
            xmlid = self._get_default_header_xmlid()
            view = self.env.ref(xmlid, raise_if_not_found=False)
            self.contract_header_template_id = view
        try:
            html = self.env["ir.qweb"]._render(view.key, {"object": self})
        except Exception as e:
            return ""
        return tools.html_sanitize(html or "")

    @api.depends(
        "partner_type",
        "partner_id",
        "company_id",
        "contract_header_template_id",
        "use_custom_contract_header",
    )
    def _compute_contract_header(self):
        for rec in self:
            rec.contract_header = rec._render_header_qweb()

    @api.onchange("partner_type")
    def _onchange_partner_type_set_template(self):
        for rec in self:
            xmlid = rec._get_default_header_xmlid()
            view = rec.env.ref(xmlid, raise_if_not_found=False)
            rec.contract_header_template_id = view

    def generate_contract_header(self):
        for rec in self:
            rec.contract_header = rec._render_header_qweb()

    @api.onchange("use_custom_contract_header")
    def _onchange_use_custom_contract_header(self):
        for rec in self:
            if rec.use_custom_contract_header:
                if not rec.contract_header:
                    rec.contract_header = rec._render_header_qweb()
            else:
                rec.contract_header = rec._render_header_qweb()

    @api.onchange('sec_partner_id')
    def set_pid(self):
        for s in self:
            s.partner_id = s.sec_partner_id.parent_id if s.sec_partner_id.parent_id else s.sec_partner_id

    def copy_it(self):
        for s in self:
            if s.copy_from:
                for line in s.copy_from.lines_ids:
                    line.copy({'contract_id': s.id})

    @api.model
    def create(self, vals_list):
        if not isinstance(vals_list, list):
            vals_list = [vals_list]

        for vals in vals_list:
            if not vals.get('is_template'):
                if vals.get('type') == 'customer':
                    vals['name'] = self.env['ir.sequence'].next_by_code('partner.contract.customer.sequence')
                elif vals.get('type') == 'supplier':
                    vals['name'] = self.env['ir.sequence'].next_by_code('partner.contract.supplier.sequence')

        records = super().create(vals_list)
        return records

    def write(self, values):

        if 'state' in values:
            if self.state != values['state']:
                msg = 'Статус: ' + dict(self._fields['state'].selection).get(self.state) + ' -> ' + dict(
                    self._fields['state'].selection).get(values['state'])
                self.message_post(body=msg)
        return super().write(values)


    def action_set_on_approval(self):
        for rec in self:
            rec.state = 'progress'

    def action_confirm(self):
        for rec in self:
            rec.state = 'signed'

    def action_reset_to_draft(self):
        for rec in self:
            rec.state = 'draft'