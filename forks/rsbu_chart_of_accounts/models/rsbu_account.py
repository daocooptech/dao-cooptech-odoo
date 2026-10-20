from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# Соответствие измерений субконто моделям Odoo.
SUBCONTO_MODELS = {
    'partner': 'res.partner',
    'product': 'product.product',
    'user': 'res.users',
    'employee': 'hr.employee',
}


class RsbuAccount(models.Model):
    """План счетов РСБУ (Приказ Минфина № 94н).

    Независимая от account.account сущность. Иерархия произвольной глубины,
    признак счёта, флаги обязательных субконто и методы агрегации по дереву.
    Источник проводок для агрегации подключается на Этапе 2 через хук
    ``_read_postings`` (здесь возвращает пустой набор).
    """
    _name = 'rsbu.account'
    _description = 'РСБУ — Счёт плана счетов'
    _parent_store = True
    _parent_name = 'parent_id'
    _order = 'complete_code, code'
    _check_company_auto = True

    name = fields.Char(string='Наименование', required=True, translate=True)
    code = fields.Char(string='Код счёта', required=True, index=True)
    company_id = fields.Many2one(
        'res.company', string='Компания', required=True, index=True,
        default=lambda self: self.env.company,
    )
    parent_id = fields.Many2one(
        'rsbu.account', string='Родительский счёт',
        ondelete='restrict', index=True, check_company=True,
    )
    child_ids = fields.One2many('rsbu.account', 'parent_id', string='Субсчета')
    parent_path = fields.Char(index=True)

    is_group = fields.Boolean(
        string='Группа (счёт-агрегатор)',
        help='Счёт-группа служит только для агрегации; относить на него '
             'проводки запрещено (проверяется на Этапе 2).',
    )
    account_kind = fields.Selection(
        selection=[
            ('active', 'Активный'),
            ('passive', 'Пассивный'),
            ('active_passive', 'Активно-пассивный'),
            ('off_balance', 'Забалансовый'),
        ],
        string='Признак счёта', required=True, default='active',
    )

    subconto_partner = fields.Boolean(string='Субконто: Контрагент')
    subconto_product = fields.Boolean(string='Субконто: Номенклатура')
    subconto_user = fields.Boolean(string='Субконто: Пользователь')
    subconto_employee = fields.Boolean(string='Субконто: Сотрудник')
    subconto_origin = fields.Boolean(string='Субконто: Документ-основание')
    subconto_contract = fields.Boolean(string='Субконто: Договор')

    active = fields.Boolean(default=True)
    note = fields.Text(string='Примечание')

    complete_code = fields.Char(
        string='Полный код', compute='_compute_complete_code',
        store=True, recursive=True,
    )
    level = fields.Integer(string='Уровень', compute='_compute_level')

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)',
        'Код счёта должен быть уникальным в пределах компании.',
    )

    # ------------------------------------------------------------------
    # Вычисляемые поля
    # ------------------------------------------------------------------
    @api.depends('code', 'parent_id.complete_code')
    def _compute_complete_code(self):
        for account in self:
            if account.parent_id:
                account.complete_code = '%s / %s' % (
                    account.parent_id.complete_code or account.parent_id.code,
                    account.code,
                )
            else:
                account.complete_code = account.code

    @api.depends('parent_path')
    def _compute_level(self):
        for account in self:
            account.level = (account.parent_path or '').count('/') - 1 \
                if account.parent_path else 0

    # ------------------------------------------------------------------
    # Ограничения
    # ------------------------------------------------------------------
    @api.constrains('parent_id')
    def _check_parent_recursion(self):
        if self._has_cycle():
            raise ValidationError(
                _('Нельзя создать циклическую иерархию счетов.'))

    @api.constrains('parent_id', 'company_id')
    def _check_parent_company(self):
        for account in self:
            if account.parent_id and \
                    account.parent_id.company_id != account.company_id:
                raise ValidationError(_(
                    'Родительский счёт должен принадлежать той же компании.'))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_has_children(self):
        for account in self:
            if account.child_ids:
                raise ValidationError(_(
                    'Нельзя удалить счёт «%s»: у него есть субсчета. '
                    'Сначала удалите или перенесите субсчета, либо '
                    'заархивируйте счёт.') % account.display_name)

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for account in self:
            account.display_name = '%s %s' % (account.code, account.name)

    # ------------------------------------------------------------------
    # Субконто
    # ------------------------------------------------------------------
    def get_required_subconto(self):
        """Список обязательных измерений субконто для счёта.

        :return: list[str] из ('partner', 'product', 'user', 'employee')
        """
        self.ensure_one()
        required = []
        if self.subconto_partner:
            required.append('partner')
        if self.subconto_product:
            required.append('product')
        if self.subconto_user:
            required.append('user')
        if self.subconto_employee:
            required.append('employee')
        return required

    # ------------------------------------------------------------------
    # Иерархия и агрегация
    # ------------------------------------------------------------------
    def _get_subtree_account_ids(self):
        """ID счёта(ов) и всех их потомков."""
        return self.search([('id', 'child_of', self.ids)]).ids

    def _read_postings(self, domain=None):
        """Хук чтения проводок для агрегации.

        На Этапе 1 источника проводок нет — возвращается пустой recordset.
        На Этапе 2 (модуль rsbu_journal) метод переопределяется и читает
        проведённые строки rsbu.move.line.
        """
        return self.env['rsbu.account'].browse()  # пустой набор-заглушка

    def get_turnover(self, date_from=None, date_to=None, company_id=None,
                     include_children=True, subconto=None):
        """Обороты Дт/Кт за период по счёту (с учётом потомков).

        :param subconto: dict фильтров по измерениям, напр.
            {'partner': partner_id} — ограничить обороты этим субконто.
        """
        self.ensure_one()
        lines = self._collect_posting_lines(
            date_from, date_to, company_id, include_children, subconto)
        debit = sum(getattr(l, 'debit', 0.0) for l in lines)
        credit = sum(getattr(l, 'credit', 0.0) for l in lines)
        return {'debit': debit, 'credit': credit}

    def get_balance(self, date_from=None, date_to=None, company_id=None,
                    include_children=True, subconto=None):
        """Сальдо по счёту (с учётом потомков и признака счёта).

        :return: dict с ключами debit, credit, balance, side.
        """
        self.ensure_one()
        turnover = self.get_turnover(
            date_from, date_to, company_id, include_children, subconto)
        debit = turnover['debit']
        credit = turnover['credit']
        raw = debit - credit  # дебетовое сальдо положительно
        if self.account_kind == 'passive':
            balance = credit - debit
            side = 'credit' if balance >= 0 else 'debit'
        elif self.account_kind == 'active':
            balance = raw
            side = 'debit' if balance >= 0 else 'credit'
        else:  # active_passive / off_balance
            balance = abs(raw)
            side = 'debit' if raw >= 0 else 'credit'
        return {
            'debit': debit,
            'credit': credit,
            'balance': balance,
            'side': side,
        }

    def get_origin_balances(self, date_to=None, company_id=None,
                            subconto=None):
        """Сальдо счёта в разрезе субконто «Документ-основание» (origin).

        Возвращает список dict {'origin': rsbu.move, 'debit', 'credit',
        'balance', 'side'} по каждому origin_move_id с ненулевым остатком,
        упорядоченный по дате/номеру основания (FIFO). Служит для зачёта
        авансов по каждому основанию отдельно (аналог 3-го субконто 1С).
        """
        self.ensure_one()
        lines = self._collect_posting_lines(
            None, date_to, company_id, True, subconto)
        by_origin = {}
        for ln in lines:
            origin = ln.origin_move_id
            if not origin:
                continue
            acc = by_origin.setdefault(
                origin.id, {'origin': origin, 'debit': 0.0, 'credit': 0.0})
            acc['debit'] += ln.debit
            acc['credit'] += ln.credit
        result = []
        for data in by_origin.values():
            raw = data['debit'] - data['credit']
            if self.account_kind == 'passive':
                balance = data['credit'] - data['debit']
                side = 'credit' if balance >= 0 else 'debit'
            elif self.account_kind == 'active':
                balance = raw
                side = 'debit' if balance >= 0 else 'credit'
            else:
                balance = abs(raw)
                side = 'debit' if raw >= 0 else 'credit'
            data['balance'] = balance
            data['side'] = side
            result.append(data)
        # FIFO: по дате и номеру проводки-основания.
        result.sort(key=lambda d: (d['origin'].date, d['origin'].name or '',
                                   d['origin'].id))
        return result

    def get_expanded_balance(self, date_to=None, date_from=None,
                             company_id=None):
        """Развёрнутое сальдо счёта (Дт и Кт одновременно), как в 1С.

        Для активно-пассивных счетов (60/62/76) простое сальдо сворачивает
        дебиторку и кредиторку в нетто, что искажает ОСВ. Здесь остаток
        считается в разрезе субконто (счёт-лист × контрагент × договор ×
        документ-основание): по каждой аналитике вычисляется её сальдо со
        знаком по признаку счёта, затем дебетовые остатки суммируются в
        `debit`, кредитовые — в `credit`.

        :return: dict {'debit': <сумма дебетовых остатков>,
                       'credit': <сумма кредитовых остатков>}.
        """
        self.ensure_one()
        lines = self._collect_posting_lines(
            date_from, date_to, company_id, True, None)
        # Группировка по аналитике листа: (счёт, партнёр, договор, основание).
        groups = {}
        for ln in lines:
            key = (ln.account_id.id,
                   ln.partner_id.id or 0,
                   ln.contract_id.id or 0,
                   ln.origin_move_id.id or 0)
            g = groups.setdefault(
                key, {'account': ln.account_id, 'debit': 0.0, 'credit': 0.0})
            g['debit'] += ln.debit
            g['credit'] += ln.credit
        debit_total = 0.0
        credit_total = 0.0
        for g in groups.values():
            raw = round(g['debit'] - g['credit'], 2)
            kind = g['account'].account_kind
            if kind == 'active':
                side = 'debit' if raw >= 0 else 'credit'
            elif kind == 'passive':
                side = 'credit' if raw <= 0 else 'debit'
            else:  # active_passive / off_balance — по знаку остатка
                side = 'debit' if raw >= 0 else 'credit'
            if side == 'debit':
                debit_total += abs(raw)
            else:
                credit_total += abs(raw)
        return {'debit': round(debit_total, 2),
                'credit': round(credit_total, 2)}

    def _collect_posting_lines(self, date_from, date_to, company_id,
                               include_children, subconto=None):
        """Собрать строки проводок для агрегации через хук _read_postings."""
        self.ensure_one()
        domain = []
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))
        if company_id:
            domain.append(('company_id', '=', company_id))
        # Фильтр по субконто (напр. остаток по партнёру).
        if subconto:
            for dim, value in subconto.items():
                field_name = {
                    'partner': 'partner_id', 'product': 'product_id',
                    'user': 'user_id', 'employee': 'employee_id',
                    'origin': 'origin_move_id', 'contract': 'contract_id',
                }.get(dim)
                if field_name and value:
                    domain.append((field_name, '=', value))
        return self._read_postings(domain)
