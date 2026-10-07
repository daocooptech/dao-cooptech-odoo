from odoo import fields, models

class Company(models.Model):
    _inherit = 'res.company'

    inn = fields.Char(related='partner_id.inn', readonly=False)
    kpp = fields.Char(related='partner_id.kpp', readonly=False)
    okpo = fields.Char(related='partner_id.okpo', readonly=False)
    # В Odoo 20 company_registry удалено (есть additional_identifiers, но ключа ОГРН для RU
    # нет), поэтому поле заведено здесь: его читают печатные формы и шапки договоров.
    company_registry = fields.Char('ОГРН/ОГРНИП', related='partner_id.company_registry', readonly=False)
    chief_id = fields.Many2one('res.users', 'Chief')
    accountant_id = fields.Many2one('res.users', 'General Accountant')
    print_facsimile = fields.Boolean(string='Print Facsimile',
                    help="Check this for adding Facsimiles of responsible persons to documents.")
    print_stamp = fields.Boolean(string='Print Stamp',
                                 help="Check this for adding Stamp of company to documents.")
    stamp = fields.Binary("Stamp")
    print_anywhere = fields.Boolean(string='Print Anywhere',
                    help="Uncheck this, if you want add Facsimile and Stamp only in email.",
                    default=True)
