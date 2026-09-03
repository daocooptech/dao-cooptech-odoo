# -*- coding: utf-8 -*-
from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError


class CoopWallet(models.Model):
    """Кошелёк участника — один на всех, вкладки внутри.

    Сначала я сделал по кошельку на каждый вид средств и сложил их
    остатки в одну колонку в рублях. Так нельзя, и вот почему: рубли,
    доли биткоина, кредиты-часы и пай — величины разной природы. В одной
    колонке получалось «−18,00 ₽» вместо «−18 кредитов» и «0,08 BTC»
    вместо «0,0842 BTC». Это не оформление, это неверные цифры на экране.

    Поэтому кошелёк один, а величины у каждой вкладки свои:

    - **фиатный** — рубли. Денег платформа не держит: принимать чужие
      средства и переводить их по команде — банковская операция, на неё
      нужна лицензия. Здесь учёт обязательств и подтверждённых
      поступлений;
    - **крипто** — активы во внешних сетях, у каждой сети свой адрес.
      Кошелёк некастодиальный: истина в сети, а не у нас, поэтому у
      остатка есть время получения и признак «сеть не отвечает»;
    - **взаимный кредит** — линии обязательств с названными
      контрагентами, в кредитах. Кредит — примерно час труда; курса у
      него нет и быть не может;
    - **взаиморасчёты** — кто кому должен по неоплаченным платежам
      сделок и к какому сроку;
    - **паевой счёт** — доля в кооперативе, отдельным счётом на каждый.

    Токенов среди вкладок нет: они живут в токеномике, и смешивать
    предоплаченную услугу платформы с деньгами участника незачем.
    """
    _name = 'coop.wallet'
    _description = 'Кошелёк участника'
    _order = 'id'
    _rec_name = 'display_name'

    TABS = [
        # Фиат первым: в рублях у участника проходит почти всё, а крипта
        # — у меньшинства. Первой должна стоять та вкладка, которую
        # открывают чаще, иначе каждый заход начинается с переключения.
        ('fiat', 'Фиатный кошелёк'),
        ('crypto', 'Крипто кошелёк'),
        ('lets', 'Взаимный кредит'),
        ('settle', 'Взаиморасчёты'),
        ('share', 'Паевой счёт'),
    ]

    partner_id = fields.Many2one(
        'res.partner', string='Владелец', required=True, index=True,
        ondelete='cascade')
    display_name = fields.Char(compute='_compute_display_name', store=True)

    # Вкладка — состояние экрана, а не свойство кошелька. Хранится, чтобы
    # кнопки в шапке менялись вместе с вкладкой: у каждой свой набор
    # действий, и показывать их все сразу значит предлагать «вывести
    # средства» на вкладке пая.
    tab = fields.Selection(TABS, string='Вкладка', default='fiat', required=True)

    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        default=lambda self: self.env.company.currency_id)

    # ── Крипто ───────────────────────────────────────────────────────────
    address_ids = fields.One2many(
        'coop.wallet.address', 'wallet_id', string='Адреса в сетях')
    asset_ids = fields.One2many(
        'coop.wallet.asset', 'wallet_id', string='Активы')
    crypto_valuation = fields.Monetary(
        string='Оценка активов', currency_field='currency_id',
        compute='_compute_crypto', store=True,
        help='Пересчёт в рубли справочно: курс определяет рынок, а не '
             'платформа.')
    asset_count = fields.Integer(
        string='Активов', compute='_compute_crypto', store=True)
    network_count = fields.Integer(
        string='Сетей', compute='_compute_crypto', store=True)
    tx_ids = fields.One2many(
        'coop.wallet.tx', 'wallet_id', string='Операции в сетях')
    crypto_synced_at = fields.Datetime(
        string='Остаток получен',
        help='Кошелёк некастодиальный: истина в сети. Если человек '
             'потратил монеты другим приложением тем же ключом, наша '
             'цифра устаревает — поэтому у неё есть время.')
    crypto_sync_failed = fields.Boolean(
        string='Сеть не отвечает',
        help='Показываем последний известный остаток и говорим об этом '
             'прямо, а не выдаём вчерашнее за сегодняшнее.')

    # ── Фиат ─────────────────────────────────────────────────────────────
    method_ids = fields.One2many(
        'coop.wallet.method', 'wallet_id', string='Способы оплаты')
    movement_ids = fields.One2many(
        'coop.wallet.movement', 'wallet_id', string='Движения')
    fiat_balance = fields.Monetary(
        string='Остаток', currency_field='currency_id',
        compute='_compute_fiat', store=True)
    fiat_available = fields.Monetary(
        string='Доступно к выводу', currency_field='currency_id',
        compute='_compute_fiat', store=True,
        help='Остаток за вычетом обещанного по графикам платежей: «есть на '
             'счету» и «можно вывести» — разные вещи.')
    movement_count = fields.Integer(
        string='Операций', compute='_compute_fiat', store=True)

    # ── Взаимный кредит ──────────────────────────────────────────────────
    credit_balance = fields.Float(
        string='Кредитов', compute='_compute_credit', store=True,
        help='Сумма линий с контрагентами. Плюс — вам должны, минус — '
             'должны вы. Кредит — примерно час труда, курса у него нет.')
    credit_line_count = fields.Integer(
        string='Линий', compute='_compute_credit', store=True)
    # Линия хранится один раз на пару, и участник бывает на любой её
    # стороне — обычной обратной связью такое не выражается, поэтому
    # список собирается вычислением.
    credit_line_ids = fields.Many2many(
        'coop.credit.line', string='Линии с контрагентами',
        compute='_compute_credit_line_ids')

    # ── Взаиморасчёты ────────────────────────────────────────────────────
    owed_to_me = fields.Monetary(
        string='Должны вам', currency_field='currency_id',
        compute='_compute_settlement', store=True)
    owed_by_me = fields.Monetary(
        string='Должны вы', currency_field='currency_id',
        compute='_compute_settlement', store=True)
    net_settlement = fields.Monetary(
        string='Чистое сальдо', currency_field='currency_id',
        compute='_compute_settlement', store=True)
    next_payment_on = fields.Date(
        string='Ближайший платёж', compute='_compute_settlement', store=True)
    settlement_ids = fields.Many2many(
        'coop.settlement', string='Сальдо по контрагентам',
        compute='_compute_settlement_ids')

    # ── Паевой счёт ──────────────────────────────────────────────────────
    share_account_ids = fields.One2many(
        'coop.share.account', 'wallet_id', string='Паевые счета')
    share_total = fields.Monetary(
        string='Пай во всех кооперативах', currency_field='currency_id',
        compute='_compute_share', store=True,
        help='Справочно. Вынуть эту сумму одним действием нельзя: каждый '
             'пай возвращается по правилам своего кооператива и решением '
             'его собрания.')
    share_account_count = fields.Integer(
        string='Кооперативов', compute='_compute_share', store=True)

    _sql_constraints = [
        ('one_per_partner', 'unique(partner_id)',
         'Кошелёк у участника уже есть — он один, вкладки внутри.'),
    ]

    @api.depends('partner_id')
    def _compute_display_name(self):
        for record in self:
            record.display_name = _('Кошелёк: %s') % (
                record.partner_id.display_name or '')

    @api.depends('asset_ids.valuation', 'asset_ids.network_id')
    def _compute_crypto(self):
        for record in self:
            record.crypto_valuation = sum(record.asset_ids.mapped('valuation'))
            record.asset_count = len(record.asset_ids)
            record.network_count = len(record.asset_ids.mapped('network_id'))

    @api.depends('movement_ids.amount', 'movement_ids.state')
    def _compute_fiat(self):
        Settlement = self.env['coop.settlement'].sudo()
        for record in self:
            confirmed = record.movement_ids.filtered(
                lambda m: m.state == 'confirmed')
            record.fiat_balance = sum(confirmed.mapped('amount'))
            record.movement_count = len(record.movement_ids)
            promised = sum(Settlement.search([
                ('partner_id', '=', record.partner_id.id),
            ]).mapped('owed_by_me'))
            record.fiat_available = max(0.0, record.fiat_balance - promised)

    @api.depends('partner_id')
    def _compute_credit(self):
        Line = self.env['coop.credit.line'].sudo()
        for record in self:
            lines = Line.search([
                '|', ('partner_id', '=', record.partner_id.id),
                ('counterparty_id', '=', record.partner_id.id)])
            total = 0.0
            for line in lines:
                own = line.partner_id == record.partner_id
                total += line.balance if own else -line.balance
            record.credit_balance = total
            record.credit_line_count = len(lines)

    @api.depends('partner_id')
    def _compute_settlement(self):
        Settlement = self.env['coop.settlement'].sudo()
        for record in self:
            rows = Settlement.search([('partner_id', '=', record.partner_id.id)])
            record.owed_to_me = sum(rows.mapped('owed_to_me'))
            record.owed_by_me = sum(rows.mapped('owed_by_me'))
            record.net_settlement = record.owed_to_me - record.owed_by_me
            dates = [row.next_due_on for row in rows if row.next_due_on]
            record.next_payment_on = min(dates) if dates else False

    def _compute_credit_line_ids(self):
        Line = self.env['coop.credit.line'].sudo()
        for record in self:
            record.credit_line_ids = Line.search([
                '|', ('partner_id', '=', record.partner_id.id),
                ('counterparty_id', '=', record.partner_id.id)])

    def _compute_settlement_ids(self):
        Settlement = self.env['coop.settlement'].sudo()
        for record in self:
            record.settlement_ids = Settlement.search(
                [('partner_id', '=', record.partner_id.id)])

    @api.depends('share_account_ids.balance', 'share_account_ids.state')
    def _compute_share(self):
        for record in self:
            live = record.share_account_ids.filtered(lambda a: a.state != 'closed')
            record.share_total = sum(live.mapped('balance'))
            record.share_account_count = len(live)

    # ── Сборка ───────────────────────────────────────────────────────────

    @api.model
    def wallet_for(self, partner):
        """Найти кошелёк участника или завести его.

        Паевые счета пересобираются здесь же: членство меняется, и держать
        их в согласии постоянным регламентом дороже, чем пересобрать за
        один запрос.
        """
        partner.ensure_one()
        wallet = self.sudo().search([('partner_id', '=', partner.id)], limit=1)
        if not wallet:
            wallet = self.sudo().create({'partner_id': partner.id})
        wallet._sync_share_accounts()
        return wallet

    def _sync_share_accounts(self):
        """Завести паевой счёт на каждый кооператив, где участник состоит.

        Счёт прекратившегося членства не прячется. По уставам пай
        возвращается в течение года после утверждения годового отчёта —
        то есть счёт нужен ровно тогда, когда членство уже закончилось.
        Спрятать его в этот момент значит убрать экран тогда, когда
        человек ждёт денег.
        """
        Account = self.env['coop.share.account'].sudo()
        Membership = self.env['coop.membership'].sudo()
        states = {
            'active': 'open', 'applied': 'open',
            'leaving': 'closing', 'ended': 'closed',
        }
        for wallet in self:
            memberships = Membership.search([
                ('partner_id', '=', wallet.partner_id.id),
                ('org_is_cooperative', '=', True),
            ])
            by_coop = {a.cooperative_id.id: a for a in wallet.share_account_ids}
            for membership in memberships:
                state = states.get(membership.state, 'open')
                account = by_coop.get(membership.organization_id.id)
                if account:
                    if account.state != state:
                        account.state = state
                    continue
                Account.create({
                    'wallet_id': wallet.id,
                    'cooperative_id': membership.organization_id.id,
                    'membership_id': membership.id,
                    'joined_on': membership.joined_on,
                    'state': state,
                })
        return True

    @api.model
    def action_open_my_wallet(self):
        """Открыть свой кошелёк, собрав паевые счета."""
        partner = self.env.user._coop_acting_partner()
        wallet = self.wallet_for(partner)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Кошелёк'),
            'res_model': 'coop.wallet',
            'res_id': wallet.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ── Действия вкладок ─────────────────────────────────────────────────
    #
    # Все требуют подтверждённой личности: это деньги и обязательства.
    # Проверка стоит и здесь, а не только в кнопке: кнопку можно обойти
    # вызовом, а правило от этого не перестаёт действовать.

    def _require_identity(self, action):
        self.ensure_one()
        self.partner_id.coop_require_level('identity', action)

    def action_crypto_send(self):
        self._require_identity(_('отправить перевод'))
        raise UserError(_(
            'Отправка в сеть пока не подключена: платформа не хранит ключей, '
            'и транзакцию подписывает сам участник. Сети подключаются в '
            'справочнике сетей.'))

    def action_fiat_topup(self):
        self._require_identity(_('пополнить кошелёк'))
        raise UserError(_(
            'Пополнение пойдёт через платёжного агрегатора — платформа денег '
            'не принимает. Агрегатор ещё не подключён.'))

    def action_fiat_withdraw(self):
        self._require_identity(_('вывести средства'))
        raise UserError(_(
            'Вывод пойдёт через платёжного агрегатора на привязанный способ '
            'оплаты. Агрегатор ещё не подключён.'))


class CoopWalletMovement(models.Model):
    """Движение по фиатному кошельку.

    Знак суммы и есть направление: плюс — пришло, минус — ушло. Хранить
    направление отдельным полем значит завести вторую истину, которая
    рано или поздно разойдётся с первой.
    """
    _name = 'coop.wallet.movement'
    _description = 'Движение по кошельку'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    wallet_id = fields.Many2one(
        'coop.wallet', string='Кошелёк', required=True, index=True,
        ondelete='cascade')
    partner_id = fields.Many2one(
        related='wallet_id.partner_id', store=True, index=True, string='Владелец')
    date = fields.Date(
        string='Дата', required=True, default=fields.Date.context_today, index=True)
    name = fields.Char(
        string='Операция', required=True,
        help='Так, как это прочтёт человек: «Пополнение с карты МИР •• 4412», '
             '«Оплата по вакансии „Кладовщик“ — ООО „Мириталь“». Человек '
             'ищет глазами знакомое имя, а не вид записи.')
    amount = fields.Monetary(
        string='Сумма', currency_field='currency_id', required=True,
        help='Плюс — пришло, минус — ушло.')
    currency_id = fields.Many2one(related='wallet_id.currency_id', store=True)

    kind = fields.Selection([
        ('topup', 'Пополнение'),
        ('withdraw', 'Вывод'),
        ('transfer', 'Перевод участнику'),
        ('deal', 'По сделке'),
        ('correction', 'Корректировка'),
    ], string='Вид', required=True, default='deal', index=True)

    method_id = fields.Many2one(
        'coop.wallet.method', string='Способ оплаты',
        help='Обязателен для пополнения и вывода: без него в истории не из '
             'чего собрать «Вывод на карту МИР •• 4412».')
    counterparty_id = fields.Many2one('res.partner', string='Контрагент', index=True)
    deal_id = fields.Many2one('coop.deal', string='Сделка', index=True)

    state = fields.Selection([
        ('pending', 'В работе'),
        ('confirmed', 'Проведено'),
        ('failed', 'Отклонено'),
        ('cancelled', 'Отменено'),
    ], string='Состояние', default='confirmed', required=True, index=True,
        tracking=True,
        help='Вывод на карту идёт минуты, а не мгновенно, и банк его может '
             'отклонить. Без промежуточных состояний экран показывал бы '
             'только свершившееся, а человек не понимал бы, где его деньги.')

    _sql_constraints = [
        ('amount_not_zero', 'check(amount != 0)',
         'Движение на ноль не имеет смысла.'),
    ]

    @api.constrains('kind', 'method_id')
    def _check_method(self):
        for record in self:
            if record.kind in ('topup', 'withdraw') and not record.method_id:
                raise ValidationError(_(
                    'У пополнения и вывода должен быть указан способ оплаты: '
                    'иначе в истории не из чего собрать, откуда пришло и куда '
                    'ушло.'))

    def action_confirm(self):
        self.write({'state': 'confirmed'})
        return True

    def unlink(self):
        confirmed = self.filtered(lambda m: m.state == 'confirmed')
        if confirmed:
            raise UserError(_(
                'Проведённое движение не удаляется: по остатку без истории '
                'нельзя объяснить, откуда он взялся. Ошибку исправляют '
                'встречным движением с пояснением.'))
        return super().unlink()


class CoopSettlement(models.Model):
    """Сальдо по контрагентам — кто кому должен и когда.

    Одно число «баланс» не отвечает на главный вопрос: кто кому должен и
    к какому сроку. Здесь тот же оборот разложен по контрагентам — по
    неоплаченным позициям графиков платежей в сделках.

    Не таблица, а взгляд: считается на лету и хранить его негде. Вторая
    копия неизбежно разойдётся с графиками платежей, и тогда непонятно,
    какой из двух цифр верить.

    Знак берётся из того, **кто платит**, а не из порядка сторон в
    сделке. Стороны равноправны, «первая» — это порядок полей, а не
    старшинство; считать её кредитором значило бы переворачивать знак на
    каждой покупке и уверенно показывать «должны вам» там, где должны вы.
    """
    _name = 'coop.settlement'
    _description = 'Сальдо по контрагентам'
    _auto = False
    _order = 'amount desc'

    partner_id = fields.Many2one('res.partner', string='Участник', readonly=True)
    counterparty_id = fields.Many2one('res.partner', string='Контрагент', readonly=True)
    amount = fields.Monetary(
        string='Сальдо', currency_field='currency_id', readonly=True,
        help='Плюс — должны вам, минус — должны вы.')
    owed_to_me = fields.Monetary(
        string='Должны вам', currency_field='currency_id', readonly=True)
    owed_by_me = fields.Monetary(
        string='Должны вы', currency_field='currency_id', readonly=True)
    next_due_on = fields.Date(string='Ближайший срок', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Валюта', readonly=True)
    deal_count = fields.Integer(string='Сделок', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    -- Идентификатор собирается из пары участников, а не
                    -- нумерацией строк. `row_number()` даёт разные номера
                    -- при каждом запросе: список, собранный по одному
                    -- запросу, при чтении по этим же номерам показывал
                    -- чужие строки — и человек видел долги, которых у него
                    -- нет.
                    (t.partner_id * 1000000 + t.counterparty_id) AS id,
                    t.partner_id,
                    t.counterparty_id,
                    SUM(t.amount) AS amount,
                    SUM(GREATEST(t.amount, 0)) AS owed_to_me,
                    SUM(GREATEST(-t.amount, 0)) AS owed_by_me,
                    MIN(t.due_on) AS next_due_on,
                    MAX(t.currency_id) AS currency_id,
                    COUNT(DISTINCT t.deal_id) AS deal_count
                FROM (
                    -- Получателю платежа должны: сумма в плюс.
                    SELECT p.payee_id AS partner_id,
                           p.payer_id AS counterparty_id,
                           p.amount AS amount,
                           p.due_on AS due_on,
                           d.currency_id AS currency_id,
                           d.id AS deal_id
                      FROM coop_deal_payment p
                      JOIN coop_deal d ON d.id = p.deal_id
                     WHERE p.state IN ('planned', 'overdue')
                       AND d.state NOT IN ('cancelled', 'draft')
                       AND p.payer_id IS NOT NULL AND p.payee_id IS NOT NULL
                    UNION ALL
                    -- Плательщик должен: та же сумма в минус.
                    SELECT p.payer_id AS partner_id,
                           p.payee_id AS counterparty_id,
                           -p.amount AS amount,
                           p.due_on AS due_on,
                           d.currency_id AS currency_id,
                           d.id AS deal_id
                      FROM coop_deal_payment p
                      JOIN coop_deal d ON d.id = p.deal_id
                     WHERE p.state IN ('planned', 'overdue')
                       AND d.state NOT IN ('cancelled', 'draft')
                       AND p.payer_id IS NOT NULL AND p.payee_id IS NOT NULL
                ) t
                GROUP BY t.partner_id, t.counterparty_id
                HAVING SUM(t.amount) <> 0
            )
        """ % self._table)
