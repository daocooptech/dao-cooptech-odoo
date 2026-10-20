from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero

# Соответствие измерений субконто полям строки.
SUBCONTO_FIELD = {
    'partner': 'partner_id',
    'product': 'product_id',
    'user': 'user_id',
    'employee': 'employee_id',
    'origin': 'origin_move_id',
    'contract': 'contract_id',
}


class RsbuMoveLine(models.Model):
    """Строка проводки РСБУ (двойная запись, субконто)."""
    _name = 'rsbu.move.line'
    _description = 'РСБУ — Строка проводки'
    _check_company_auto = True

    move_id = fields.Many2one(
        'rsbu.move', string='Операция', required=True,
        ondelete='cascade', index=True)
    account_id = fields.Many2one(
        'rsbu.account', string='Счёт', required=True,
        check_company=True, index=True)
    name = fields.Char(string='Описание')
    debit = fields.Monetary(string='Дебет', default=0.0,
                            currency_field='currency_id')
    credit = fields.Monetary(string='Кредит', default=0.0,
                             currency_field='currency_id')

    # Субконто.
    partner_id = fields.Many2one('res.partner', string='Контрагент',
                                 check_company=True)
    product_id = fields.Many2one('product.product', string='Номенклатура')
    user_id = fields.Many2one('res.users', string='Пользователь')
    employee_id = fields.Many2one('hr.employee', string='Сотрудник',
                                  check_company=True)
    # Субконто «Документ-основание»: проводка-основание расчёта (аванс),
    # аналог 3-го субконто 1С на 62.02/60.02/76.АВ («Документы расчётов»).
    # Позволяет вести остаток и зачёт по каждому авансу отдельно.
    origin_move_id = fields.Many2one(
        'rsbu.move', string='Документ-основание', index=True,
        ondelete='restrict')
    # Субконто «Договор» — аналог 2-го субконто 1С «Договоры» на 60/62/76.
    # Расчёты и зачёт авансов ведутся в разрезе (контрагент, договор).
    contract_id = fields.Many2one(
        'partner.contract.customer', string='Договор', index=True,
        ondelete='restrict')

    company_id = fields.Many2one(
        related='move_id.company_id', string='Компания',
        store=True, index=True)
    currency_id = fields.Many2one(
        related='move_id.currency_id', string='Валюта', store=True)
    date = fields.Date(related='move_id.date', store=True, index=True)
    state = fields.Selection(
        related='move_id.state', store=True, index=True)

    # ------------------------------------------------------------------
    # Ограничения
    # ------------------------------------------------------------------
    @api.constrains('debit', 'credit')
    def _check_debit_credit(self):
        for line in self:
            rounding = line.currency_id.rounding or 0.01
            debit_zero = float_is_zero(line.debit, precision_rounding=rounding)
            credit_zero = float_is_zero(line.credit, precision_rounding=rounding)
            if debit_zero and credit_zero:
                raise ValidationError(_(
                    'Строка проводки должна иметь ненулевую сумму '
                    'по дебету или кредиту.'))
            if not debit_zero and not credit_zero:
                raise ValidationError(_(
                    'Строка проводки не может иметь одновременно дебет '
                    'и кредит. Заполните только одну сторону.'))

    @api.constrains('account_id')
    def _check_account_not_group(self):
        for line in self:
            if line.account_id.is_group:
                raise ValidationError(_(
                    'Нельзя относить проводку на счёт-группу «%s».')
                    % line.account_id.display_name)

    def _has_subconto(self, dimension):
        """Заполнено ли измерение субконто в строке."""
        self.ensure_one()
        field_name = SUBCONTO_FIELD.get(dimension)
        return bool(field_name and self[field_name])
