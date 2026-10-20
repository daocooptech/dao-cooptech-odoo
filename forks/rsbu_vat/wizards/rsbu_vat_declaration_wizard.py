from odoo import fields, models


class RsbuVatDeclarationWizard(models.TransientModel):
    """Визард быстрого просмотра итогов НДС на экране.

    Полноценная декларация НДС с выгрузкой XML (комплект из 3 файлов по
    формату ФНС 5.12) — постоянная модель rsbu.nds.declaration в модуле
    rsbu_fns_reporting (меню «Отчётность ФНС → Декларация НДС»). Этот
    визард оставлен для быстрой прикидки сумм за произвольный период.
    """
    _name = 'rsbu.vat.declaration.wizard'
    _description = 'РСБУ — Расчёт декларации НДС'

    date_from = fields.Date(string='Дата с', required=True)
    date_to = fields.Date(string='Дата по', required=True)
    company_id = fields.Many2one(
        'res.company', string='Компания', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        related='company_id.currency_id')

    tax_base = fields.Monetary(string='Налоговая база', readonly=True,
                               currency_field='currency_id')
    vat_charged = fields.Monetary(string='НДС начислен', readonly=True,
                                  currency_field='currency_id')
    vat_deducted = fields.Monetary(string='Вычеты', readonly=True,
                                   currency_field='currency_id')
    vat_payable = fields.Monetary(string='НДС к уплате', readonly=True,
                                  currency_field='currency_id')
    computed = fields.Boolean(default=False)

    def action_compute(self):
        self.ensure_one()
        # Гарантируем актуальность книг/итогов.
        self.env['rsbu.vat.book.line'].recompute_period(
            self.date_from, self.date_to, self.company_id)
        self.env['rsbu.vat.summary'].recompute_period(
            self.date_from, self.date_to, self.company_id)
        books = self.env['rsbu.vat.book.line'].search([
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ])
        charged = sum(books.filtered(lambda b: b.book == 'sales')
                      .mapped('vat_amount'))
        deducted = sum(books.filtered(lambda b: b.book == 'purchases')
                       .mapped('vat_amount'))
        self.write({
            'vat_charged': charged,
            'vat_deducted': deducted,
            'vat_payable': charged - deducted,
            'computed': True,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'rsbu.vat.declaration.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
