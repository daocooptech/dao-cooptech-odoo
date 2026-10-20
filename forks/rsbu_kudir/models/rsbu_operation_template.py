from odoo import fields, models


class RsbuOperationTemplate(models.Model):
    """Расширение шаблона: правило признания в УСН (для КУДиР)."""
    _inherit = 'rsbu.operation.template'

    usn_recognition = fields.Selection(
        selection=[
            ('income', 'Доход'),
            ('expense', 'Расход'),
            ('refund_customer', 'Возврат клиенту'),
            ('refund_supplier', 'Возврат поставщику'),
            ('none', 'Не участвует в УСН'),
        ],
        string='Признание в УСН', default='none', required=True)
    is_refund = fields.Boolean(string='Это возврат')
