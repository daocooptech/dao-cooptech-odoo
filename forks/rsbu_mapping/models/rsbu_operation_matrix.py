from odoo import fields, models


class RsbuOperationMatrix(models.Model):
    """Матрица связности: подбор шаблона по признакам документа."""
    _name = 'rsbu.operation.matrix'
    _description = 'РСБУ — Матрица связности операций'
    _order = 'priority, id'
    _check_company_auto = True

    name = fields.Char(string='Наименование правила', required=True)
    doc_kind = fields.Selection(
        selection=[
            # account.move
            ('out_invoice', 'Счёт покупателю (реализация)'),
            ('out_refund', 'Возврат покупателю (кредит-нота)'),
            ('in_invoice', 'Счёт поставщика'),
            ('in_refund', 'Возврат поставщику'),
            # account.payment
            ('payment_inbound', 'Входящий платёж'),
            ('payment_outbound', 'Исходящий платёж'),
        ],
        string='Тип документа', required=True)
    has_advance = fields.Selection(
        selection=[('any', 'Не важно'), ('yes', 'Есть аванс'),
                   ('no', 'Без аванса')],
        string='Признак аванса', default='any', required=True)
    partner_kind = fields.Selection(
        selection=[('any', 'Не важно'), ('customer', 'Клиент'),
                   ('supplier', 'Поставщик')],
        string='Тип контрагента', default='any', required=True,
        help='Для платежей: различает клиента и поставщика при '
             'одинаковом направлении платежа.')
    template_id = fields.Many2one(
        'rsbu.operation.template', string='Шаблон РСБУ', required=True,
        check_company=True)
    priority = fields.Integer(string='Приоритет', default=10)
    # Только с компанией: правило без компании действовало бы на весь пул.
    company_id = fields.Many2one(
        'res.company', string='Компания', required=True, index=True,
        default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    def _match(self, doc):
        """Подходит ли правило документу."""
        self.ensure_one()
        doc_kind = doc._rsbu_doc_kind()
        if self.doc_kind != doc_kind:
            return False
        if self.has_advance != 'any':
            has_adv = doc._rsbu_has_advance()
            if self.has_advance == 'yes' and not has_adv:
                return False
            if self.has_advance == 'no' and has_adv:
                return False
        if self.partner_kind != 'any':
            if self.partner_kind != doc._rsbu_partner_kind():
                return False
        return True
