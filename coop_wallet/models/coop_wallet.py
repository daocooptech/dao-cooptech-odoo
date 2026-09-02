# -*- coding: utf-8 -*-
from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError


class CoopWallet(models.Model):
    """Кошелёк участника — один на каждый вид средств.

    Вкладок в кошельке не фиксированное число: состав зависит от того,
    кем участник является и что у него подключено. Фиатный и
    крипто-кошелёк есть у всех, паевой счёт появляется только у
    участника кооператива — и отдельным на каждый кооператив, потому что
    пай в каждом свой и выходят из них порознь.

    Разница между видами не косметическая, и её стоит держать в голове:

    - **фиатный** — учёт рублёвых обязательств. Денег платформа не
      держит: принимать чужие средства и переводить их по команде —
      банковская операция, на неё нужна лицензия. Здесь записано, кто
      кому сколько должен и что подтверждено полученным;
    - **крипто** — адреса и активы участника во внешних сетях. Платформа
      их не хранит и ключами не распоряжается, она показывает остаток и
      служит местом, откуда транзакция уходит в выбранную сеть;
    - **взаимный кредит** — сальдо участника в кругу взаимозачёта. Не
      деньги и не суррогат: обязательства гасятся встречными, а не
      передачей средства платежа;
    - **паевой счёт** — состояние пая в конкретном кооперативе. Это
      учётный регистр членских отношений, а не банковский счёт;
    - **токены платформы** — предоплаченная единица её услуг. Движения
      живут отдельной моделью, потому что их нельзя ни править, ни
      удалять, и это правило старше кошелька.
    """
    _name = 'coop.wallet'
    _description = 'Кошелёк участника'
    _order = 'sequence, id'
    _rec_name = 'display_name'

    KINDS = [
        ('fiat', 'Фиатный кошелёк'),
        ('crypto', 'Крипто кошелёк'),
        ('lets', 'Взаимный кредит'),
        ('share', 'Паевой счёт'),
        ('token', 'Токены платформы'),
    ]

    partner_id = fields.Many2one(
        'res.partner', string='Участник', required=True, index=True,
        ondelete='cascade')
    kind = fields.Selection(KINDS, string='Вид', required=True, index=True)
    sequence = fields.Integer(string='Порядок', default=10)
    display_name = fields.Char(compute='_compute_display_name', store=True)

    # Паевой счёт — свой в каждом кооперативе: пай в каждом отдельный, и
    # выходят из них порознь.
    cooperative_id = fields.Many2one(
        'res.partner', string='Кооператив', index=True,
        domain=[('is_company', '=', True)])

    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        default=lambda self: self.env.company.currency_id)
    asset_code = fields.Char(
        string='Актив',
        help='Для крипто-кошелька: обозначение актива в сети.')
    address = fields.Char(
        string='Адрес в сети',
        help='Публичный адрес. Ключи платформа не хранит и не запрашивает.')

    movement_ids = fields.One2many(
        'coop.wallet.movement', 'wallet_id', string='Движения')
    token_ids = fields.One2many(
        related='partner_id.coop_token_ids', string='Движения токенов')

    balance = fields.Monetary(
        string='Остаток', currency_field='currency_id',
        compute='_compute_balance', store=True)
    movement_count = fields.Integer(
        string='Операций', compute='_compute_balance', store=True)

    active = fields.Boolean(string='Подключён', default=True)

    _sql_constraints = [
        ('one_per_kind', 'unique(partner_id, kind, cooperative_id)',
         'Такой кошелёк у участника уже есть.'),
    ]

    @api.depends('kind', 'cooperative_id', 'partner_id')
    def _compute_display_name(self):
        labels = dict(self.KINDS)
        for record in self:
            name = labels.get(record.kind, '')
            if record.kind == 'share' and record.cooperative_id:
                name = '%s — %s' % (name, record.cooperative_id.name)
            record.display_name = name

    @api.depends('movement_ids.amount', 'movement_ids.state',
                 'partner_id.coop_token_balance', 'kind')
    def _compute_balance(self):
        for record in self:
            if record.kind == 'token':
                # Остаток по токенам считается их собственной моделью:
                # движения там неизменяемы, и второй счётчик рано или
                # поздно разошёлся бы с первым.
                record.balance = record.partner_id.coop_token_balance
                record.movement_count = len(record.partner_id.coop_token_ids)
            else:
                confirmed = record.movement_ids.filtered(
                    lambda m: m.state == 'confirmed')
                record.balance = sum(confirmed.mapped('amount'))
                record.movement_count = len(record.movement_ids)

    # ── Состав кошельков ─────────────────────────────────────────────────

    @api.model
    def sync_for_partner(self, partner):
        """Собрать участнику те кошельки, которые ему положены.

        Фиатный, крипто и токены — всем. Взаимный кредит — тоже всем:
        круг взаимозачёта открыт любому участнику. Паевой счёт — только
        членам кооперативов, и отдельный на каждый.

        Кошелёк, переставший быть положенным (человек вышел из
        кооператива), не удаляется, а отключается: движения по паю —
        история расчётов, и стирать её при выходе нельзя.
        """
        partner.ensure_one()
        Wallet = self.sudo()
        wanted = [('fiat', False), ('crypto', False), ('lets', False), ('token', False)]

        memberships = self.env['coop.membership'].sudo().search([
            ('partner_id', '=', partner.id),
            ('state', 'in', ('active', 'leaving')),
            ('org_is_cooperative', '=', True),
        ])
        wanted += [('share', m.organization_id.id) for m in memberships]

        existing = Wallet.with_context(active_test=False).search(
            [('partner_id', '=', partner.id)])
        by_key = {(w.kind, w.cooperative_id.id or False): w for w in existing}

        order = {code: index for index, (code, _label) in enumerate(self.KINDS)}
        for kind, cooperative in wanted:
            wallet = by_key.get((kind, cooperative))
            if wallet:
                if not wallet.active:
                    wallet.active = True
                continue
            Wallet.create({
                'partner_id': partner.id,
                'kind': kind,
                'cooperative_id': cooperative or False,
                'sequence': (order.get(kind, 9) + 1) * 10,
            })

        stale = [w for key, w in by_key.items() if key not in wanted and w.active]
        for wallet in stale:
            wallet.active = False
        return True

    @api.model
    def action_open_my_wallet(self):
        """Открыть свой кошелёк, собрав недостающие вкладки.

        Собирается при открытии, а не заранее: состав зависит от членства,
        а членство меняется, и держать его в согласии постоянным
        регламентом дороже, чем пересобрать за один запрос.
        """
        partner = self.env.user._coop_acting_partner()
        self.sync_for_partner(partner)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Кошелёк'),
            'res_model': 'coop.wallet',
            'view_mode': 'kanban,list,form',
            'domain': [('partner_id', '=', partner.id)],
            'context': {'default_partner_id': partner.id},
        }


class CoopWalletMovement(models.Model):
    """Движение по кошельку.

    Знак суммы и есть направление: плюс — пришло, минус — ушло. Хранить
    направление отдельным полем значит завести вторую истину, которая
    рано или поздно разойдётся с первой.

    Подтверждает движение получатель. «Я отправил» — утверждение одной
    стороны, «я получил» — подтверждение другой, и доказательная сила у
    них разная.
    """
    _name = 'coop.wallet.movement'
    _description = 'Движение по кошельку'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    wallet_id = fields.Many2one(
        'coop.wallet', string='Кошелёк', required=True, index=True,
        ondelete='cascade')
    partner_id = fields.Many2one(
        related='wallet_id.partner_id', store=True, index=True, string='Участник')
    date = fields.Date(
        string='Дата', required=True, default=fields.Date.context_today, index=True)
    name = fields.Char(string='Назначение', required=True)
    amount = fields.Monetary(
        string='Сумма', currency_field='currency_id', required=True,
        help='Плюс — пришло, минус — ушло.')
    currency_id = fields.Many2one(related='wallet_id.currency_id', store=True)

    kind = fields.Selection([
        ('deal', 'По сделке'),
        ('contribution', 'Взнос'),
        ('payout', 'Выплата'),
        ('offset', 'Взаимозачёт'),
        ('correction', 'Корректировка'),
    ], string='Основание', required=True, default='deal', index=True)

    counterparty_id = fields.Many2one(
        'res.partner', string='Контрагент', index=True)
    deal_id = fields.Many2one('coop.deal', string='Сделка', index=True)

    state = fields.Selection([
        ('draft', 'Заявлено'),
        ('confirmed', 'Подтверждено'),
        ('cancelled', 'Отменено'),
    ], string='Состояние', default='confirmed', required=True, index=True,
        tracking=True)

    _sql_constraints = [
        ('amount_not_zero', 'check(amount != 0)',
         'Движение на ноль не имеет смысла.'),
    ]

    def action_confirm(self):
        self.write({'state': 'confirmed'})
        return True

    def unlink(self):
        confirmed = self.filtered(lambda m: m.state == 'confirmed')
        if confirmed:
            raise UserError(_(
                'Подтверждённое движение не удаляется: по остатку без истории '
                'нельзя объяснить, откуда он взялся. Ошибку исправляют '
                'встречным движением с пояснением.'))
        return super().unlink()


class CoopSettlement(models.Model):
    """Сальдо по контрагентам — кто кому остался должен.

    Не таблица, а взгляд на платежи по сделкам: считается на лету и
    хранить его негде. Вторая копия неизбежно разойдётся с графиками
    платежей, и тогда непонятно, какой из двух цифр верить.

    Отсюда же берётся круг взаимных долгов: когда долги идут по кругу,
    их гасят взаимозачётом, ничего не передавая.
    """
    _name = 'coop.settlement'
    _description = 'Сальдо по контрагентам'
    _auto = False
    _order = 'amount desc'

    partner_id = fields.Many2one('res.partner', string='Участник', readonly=True)
    counterparty_id = fields.Many2one('res.partner', string='Контрагент', readonly=True)
    amount = fields.Monetary(
        string='Осталось', currency_field='currency_id', readonly=True,
        help='Плюс — должны вам, минус — должны вы.')
    currency_id = fields.Many2one('res.currency', string='Валюта', readonly=True)
    deal_count = fields.Integer(string='Сделок', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Две половины: то, что должны нам, и то, что должны мы. Одна и та
        # же неоплаченная строка графика смотрит в разные стороны в
        # зависимости от того, с чьей стороны сделки на неё смотреть.
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    t.partner_id,
                    t.counterparty_id,
                    SUM(t.amount) AS amount,
                    MAX(t.currency_id) AS currency_id,
                    COUNT(DISTINCT t.deal_id) AS deal_count
                FROM (
                    SELECT d.party_a_id AS partner_id,
                           d.party_b_id AS counterparty_id,
                           p.amount AS amount,
                           d.currency_id AS currency_id,
                           d.id AS deal_id
                      FROM coop_deal_payment p
                      JOIN coop_deal d ON d.id = p.deal_id
                     WHERE p.state IN ('planned', 'overdue')
                       AND d.state NOT IN ('cancelled', 'draft')
                    UNION ALL
                    SELECT d.party_b_id AS partner_id,
                           d.party_a_id AS counterparty_id,
                           -p.amount AS amount,
                           d.currency_id AS currency_id,
                           d.id AS deal_id
                      FROM coop_deal_payment p
                      JOIN coop_deal d ON d.id = p.deal_id
                     WHERE p.state IN ('planned', 'overdue')
                       AND d.state NOT IN ('cancelled', 'draft')
                ) t
                GROUP BY t.partner_id, t.counterparty_id
                HAVING SUM(t.amount) <> 0
            )
        """ % self._table)
