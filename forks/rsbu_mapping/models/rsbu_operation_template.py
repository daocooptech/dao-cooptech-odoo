from odoo import fields, models, _
from odoo.exceptions import UserError
from ..resolvers.registry import resolver_selection

# Роли счетов, используемые резолверами.
ROLE_SELECTION = [
    ('bank', 'Денежный счёт (51/50)'),
    ('advance_received', 'Авансы полученные (62.АВ)'),
    ('receivable', 'Расчёты с покупателями (62.01)'),
    ('revenue', 'Выручка (90.01)'),
    ('revenue_vat', 'НДС в составе продаж (90.03)'),
    ('vat_output', 'НДС начисленный (68.НДС)'),
    ('vat_advance', 'НДС с авансов (76.АВ)'),
    ('payable', 'Расчёты с поставщиками (60.01)'),
    ('advance_paid', 'Авансы выданные (60.02)'),
    ('expense', 'Затраты / расходы (44/26/20)'),
    ('vat_input', 'Входящий НДС (19)'),
]


class RsbuOperationTemplate(models.Model):
    """Шаблон типовой операции РСБУ (декларативная часть маппинга)."""
    _name = 'rsbu.operation.template'
    _description = 'РСБУ — Шаблон типовой операции'
    _check_company_auto = True

    name = fields.Char(string='Наименование', required=True)
    code = fields.Char(string='Код', required=True)
    resolver_key = fields.Selection(
        selection=lambda self: resolver_selection(),
        string='Резолвер', required=True,
        help='Python-резолвер (в коде модуля), формирующий проводки.')
    company_id = fields.Many2one(
        'res.company', string='Компания',
        default=lambda self: self.env.company)
    role_ids = fields.One2many(
        'rsbu.operation.template.role', 'template_id', string='Роли счетов')
    active = fields.Boolean(default=True)
    note = fields.Text(string='Описание логики')

    _code_uniq = models.Constraint(
        'unique(code, company_id)',
        'Код шаблона должен быть уникальным в пределах компании.')

    def _account(self, role):
        """Счёт РСБУ по роли шаблона (обязательная роль)."""
        self.ensure_one()
        line = self.role_ids.filtered(lambda r: r.role == role)[:1]
        if not line:
            raise UserError(_(
                'В шаблоне «%(tmpl)s» не задана роль счёта «%(role)s».',
                tmpl=self.display_name, role=role))
        return line.account_id

    def _account_or_none(self, role):
        """Счёт РСБУ по роли шаблона или None, если роль не задана."""
        self.ensure_one()
        line = self.role_ids.filtered(lambda r: r.role == role)[:1]
        return line.account_id if line else None


class RsbuOperationTemplateRole(models.Model):
    """Роль счёта в шаблоне операции."""
    _name = 'rsbu.operation.template.role'
    _description = 'РСБУ — Роль счёта в шаблоне'
    _check_company_auto = True

    template_id = fields.Many2one(
        'rsbu.operation.template', string='Шаблон', required=True,
        ondelete='cascade')
    role = fields.Selection(
        selection=ROLE_SELECTION, string='Роль', required=True)
    account_id = fields.Many2one(
        'rsbu.account', string='Счёт РСБУ', required=True, check_company=True)
    company_id = fields.Many2one(
        related='template_id.company_id', store=True)
    subconto_source = fields.Selection(
        selection=[
            ('partner_from_doc', 'Контрагент из документа'),
            ('none', 'Без субконто по умолчанию'),
        ],
        string='Источник субконто', default='partner_from_doc')
