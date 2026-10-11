# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CoopNominalAccount(models.Model):
    """Номинальный счёт оператора платформы.

    Владелец счёта — ООО-оператор, бенефициары — стороны сделок. Реестр
    здесь — зеркало счёта в банке: истина об остатке в выписке, и
    расхождение с ней останавливает выплаты, пока его не разберут.
    """
    _name = 'coop.nominal.account'
    _description = 'Номинальный счёт'
    _inherit = ['mail.thread']
    _order = 'name, id'

    name = fields.Char(string='Название', required=True)
    owner_id = fields.Many2one(
        'res.partner', string='Владелец счёта', required=True,
        help='Оператор платформы: он открывает счёт и подписывает '
             'распоряжения банку.')
    bank_name = fields.Char(string='Банк')
    bank_bic = fields.Char(string='БИК')
    account_number = fields.Char(string='Расчётный счёт')
    adapter = fields.Selection([
        ('manual', 'Вручную: выписка и реестр платёжек'),
        ('demo', 'Демо'),
    ], string='Подключение банка', default='manual', required=True)
    currency_id = fields.Many2one(
        'res.currency', string='Валюта', required=True,
        default=lambda self: self.env.ref('base.RUB'))
    auto_payout_limit = fields.Monetary(
        string='Порог автовыплаты', currency_field='currency_id',
        help='Выплаты до этой суммы уходят без подписи уполномоченного; '
             'ноль — подписывают все.')
    active = fields.Boolean(default=True)

    setting_ids = fields.One2many(
        'coop.nominal.setting', 'account_id', string='Настройки')
    share_ids = fields.One2many(
        'coop.nominal.share', 'account_id', string='Доли')
    entry_ids = fields.One2many(
        'coop.nominal.entry', 'account_id', string='Книга')

    # Последний конечный остаток по выписке. Пишет его загрузка выписки,
    # а не человек: цифра «со слов» сверку бы обесценила.
    statement_balance = fields.Monetary(
        string='Остаток по выписке', currency_field='currency_id',
        readonly=True, tracking=True)
    statement_date = fields.Date(
        string='Выписка на дату', readonly=True, tracking=True)

    ledger_balance = fields.Monetary(
        string='Остаток по реестру', currency_field='currency_id',
        compute='_compute_balances')
    unrecognized_balance = fields.Monetary(
        string='Нераспознанное', currency_field='currency_id',
        compute='_compute_balances',
        help='Поступления, которые не сопоставились с долей. Должно '
             'уходить в ноль.')
    discrepancy = fields.Monetary(
        string='Расхождение с выпиской', currency_field='currency_id',
        compute='_compute_balances')
    payouts_blocked = fields.Boolean(
        string='Выплаты остановлены', compute='_compute_balances')

    @api.depends('entry_ids.amount', 'statement_balance', 'statement_date')
    def _compute_balances(self):
        Entry = self.env['coop.nominal.entry'].sudo()
        for record in self:
            record.ledger_balance = Entry._leg_sum(record, 'bank')
            record.unrecognized_balance = -Entry._leg_sum(record, 'unrecognized')
            on_statement = Entry._leg_sum(
                record, 'bank', until=record.statement_date) \
                if record.statement_date else 0.0
            record.discrepancy = record.statement_balance - on_statement
            # Без выписки сверять не с чем — значит, и платить рано.
            record.payouts_blocked = (
                not record.statement_date
                or not record.currency_id.is_zero(record.discrepancy))

    def _setting_on(self, date):
        """Версия настроек, действующая на дату."""
        self.ensure_one()
        setting = self.env['coop.nominal.setting'].sudo().search([
            ('account_id', '=', self.id),
            ('date_from', '<=', date),
        ], order='date_from desc, id desc', limit=1)
        if not setting:
            raise UserError(_(
                'У счёта %(account)s нет настроек, действующих на %(date)s.',
                account=self.display_name, date=date))
        return setting

    def _check_payouts_allowed(self):
        """Инвариант 2: расхождение с выпиской останавливает выплаты."""
        for record in self:
            if not record.statement_date:
                raise UserError(_(
                    'По счёту %s ещё не загружена выписка: остаток не с чем '
                    'сверить, выплаты остановлены.') % record.display_name)
            if not record.currency_id.is_zero(record.discrepancy):
                raise UserError(_(
                    'Реестр счёта %(account)s расходится с выпиской на '
                    '%(diff)s: выплаты остановлены до разбора.',
                    account=record.display_name, diff=record.discrepancy))


class CoopNominalSetting(models.Model):
    """Версия настроек номинального счёта с датой действия.

    Развилки владельца меняются не задним числом: доля, созданная при
    одной версии, живёт по ней до конца. Поэтому вступившую в силу версию
    нельзя ни править, ни удалять — только добавить следующую.
    """
    _name = 'coop.nominal.setting'
    _description = 'Настройки номинального счёта'
    _order = 'date_from desc, id desc'

    account_id = fields.Many2one(
        'coop.nominal.account', string='Счёт', required=True,
        ondelete='cascade', index=True)
    date_from = fields.Date(string='Действует с', required=True)
    beneficiary_mode = fields.Selection([
        ('both', 'Обе стороны: до акта — покупатель'),
        ('seller', 'Только продавец'),
    ], string='Бенефициары', default='both', required=True)
    fee_mode = fields.Selection([
        ('withhold', 'Удержать из доли'),
        ('invoice', 'Выставить счёт'),
    ], string='Комиссия', default='withhold', required=True)
    books_mode = fields.Selection([
        ('off_balance', 'За балансом'),
        ('on_balance', 'На балансе'),
    ], string='Учёт у оператора', default='off_balance', required=True)
    bank_control = fields.Boolean(
        string='Контроль банка',
        help='Банк проверяет основание каждой выплаты до списания.')
    fee_percent = fields.Float(
        string='Комиссия, %', digits=(5, 2),
        help='Доля от суммы платежа, которую берёт оператор.')
    fee_vat_percent = fields.Float(
        string='НДС в комиссии, %', digits=(5, 2),
        help='Ставка НДС, входящего в сумму комиссии. Ноль — без НДС.')
    note = fields.Char(string='Основание')

    _date_unique = models.Constraint(
        'unique(account_id, date_from)',
        'У счёта на одну дату — одна версия настроек.',
    )

    @api.constrains('fee_percent', 'fee_vat_percent')
    def _check_percents(self):
        for record in self:
            if not 0 <= record.fee_percent < 100 or not 0 <= record.fee_vat_percent < 100:
                raise ValidationError(_('Проценты — от нуля до ста.'))

    @api.model_create_multi
    def create(self, vals_list):
        today = fields.Date.context_today(self)
        for vals in vals_list:
            account = self.env['coop.nominal.account'].browse(vals.get('account_id'))
            date_from = fields.Date.to_date(vals.get('date_from'))
            # Задним числом — только пока по счёту нет ни одной доли:
            # иначе прошлые доли разошлись бы с тем, что «действовало».
            if date_from and date_from < today and account.sudo().share_ids:
                raise UserError(_(
                    'По счёту уже есть доли: новая версия настроек действует '
                    'не раньше сегодняшнего дня.'))
        return super().create(vals_list)

    def _check_not_started(self):
        today = fields.Date.context_today(self)
        if any(record.date_from <= today for record in self):
            raise UserError(_(
                'Версия настроек уже действует: её не правят, а заменяют '
                'следующей.'))

    def write(self, vals):
        self._check_not_started()
        result = super().write(vals)
        if 'date_from' in vals:
            self._check_not_started()
        return result

    def unlink(self):
        self._check_not_started()
        return super().unlink()
