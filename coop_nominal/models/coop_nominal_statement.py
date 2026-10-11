# -*- coding: utf-8 -*-
import codecs
import hashlib
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .coop_nominal_payout import LIVE

# Код удержания в назначении платежа. Люди набирают его как придётся:
# «CT-15», «ct 15», «СТ-15» русскими буквами, с длинным тире.
HOLD_CODE = re.compile(r'(?<!\w)[CС][TТ]\s*[-‐–—]?\s*(\d+)(?!\d)', re.IGNORECASE)


def _decode(data):
    """Текст файла обмена. Кодировку называет сам файл, но строкой в
    этой же кодировке, поэтому сперва смотрим на байты."""
    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8):].decode('utf-8')
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        pass
    if 'Кодировка=DOS'.encode('cp866') in data[:1000]:
        return data.decode('cp866')
    return data.decode('cp1251')


def _date(value):
    try:
        return datetime.strptime(value.strip(), '%d.%m.%Y').date()
    except (AttributeError, ValueError):
        return None


def _amount(value):
    try:
        return float(Decimal((value or '').replace(' ', '').replace(',', '.')))
    except InvalidOperation:
        return None


def parse_1c(data):
    """Разобрать файл 1CClientBankExchange.

    Возвращает шапку, секции счетов и документы — словари «ключ: значение».
    Оборванный файл (нет «КонецФайла») не принимаем: половина выписки
    дала бы верный остаток при пропавших строках.
    """
    lines = [line.strip() for line in _decode(data).splitlines()]
    if not lines or lines[0] != '1CClientBankExchange':
        raise UserError(_(
            'Это не выписка в формате 1С: файл должен начинаться строкой '
            '«1CClientBankExchange».'))
    header, accounts, documents = {}, [], []
    current = None
    for line in lines[1:]:
        if line == 'КонецФайла':
            break
        if line == 'СекцияРасчСчет':
            current = {}
            accounts.append(current)
        elif line.startswith('СекцияДокумент'):
            current = {'СекцияДокумент': line.partition('=')[2].strip()}
            documents.append(current)
        elif line in ('КонецРасчСчет', 'КонецДокумента'):
            current = None
        elif '=' in line:
            key, _sep, value = line.partition('=')
            (header if current is None else current)[key.strip()] = value.strip()
    else:
        raise UserError(_('Файл выписки оборван: нет строки «КонецФайла».'))
    return header, accounts, documents


class CoopNominalStatement(models.Model):
    """Выписка банка по номинальному счёту.

    Выписка — источник истины о деньгах: по ней удержание считается
    оплаченным, выплата исполненной, а остаток сверяется с книгой.
    Поэтому загруженную выписку не правят и не удаляют, а один и тот же
    файл дважды не принимают.
    """
    _name = 'coop.nominal.statement'
    _description = 'Выписка по номинальному счёту'
    _order = 'date_to desc, id desc'

    name = fields.Char(string='Выписка', readonly=True)
    account_id = fields.Many2one(
        'coop.nominal.account', string='Счёт', required=True,
        ondelete='restrict', index=True, readonly=True)
    currency_id = fields.Many2one(related='account_id.currency_id')
    file_name = fields.Char(string='Файл', readonly=True)
    file_hash = fields.Char(string='Хэш файла', required=True, readonly=True)
    date_from = fields.Date(string='С', readonly=True)
    date_to = fields.Date(string='По', readonly=True)
    balance_start = fields.Monetary(
        string='Начальный остаток', currency_field='currency_id', readonly=True)
    balance_end = fields.Monetary(
        string='Конечный остаток', currency_field='currency_id', readonly=True)
    total_in = fields.Monetary(
        string='Поступило', currency_field='currency_id', readonly=True)
    total_out = fields.Monetary(
        string='Списано', currency_field='currency_id', readonly=True)
    uploaded_by_id = fields.Many2one('res.users', string='Загрузил', readonly=True)
    skipped_count = fields.Integer(
        string='Уже были в прошлых выписках', readonly=True,
        help='Строки, которые пришли и в более ранней выписке: второй раз '
             'их не проводим.')
    line_ids = fields.One2many(
        'coop.nominal.statement.line', 'statement_id', string='Строки')
    unrecognized_count = fields.Integer(
        string='Нераспознано', compute='_compute_counts')
    opening_discrepancy = fields.Monetary(
        string='Расхождение на начало', currency_field='currency_id',
        compute='_compute_opening_discrepancy',
        help='Начальный остаток по выписке минус остаток книги накануне. '
             'Не ноль — между выписками пропущен день или строка.')

    _hash_unique = models.Constraint(
        'unique(account_id, file_hash)',
        'Эта выписка уже загружена.',
    )

    @api.depends('line_ids.state')
    def _compute_counts(self):
        for record in self:
            record.unrecognized_count = len(
                record.line_ids.filtered(lambda line: line.state == 'unrecognized'))

    def _compute_opening_discrepancy(self):
        Entry = self.env['coop.nominal.entry'].sudo()
        for record in self:
            if not record.date_from:
                record.opening_discrepancy = 0.0
                continue
            before = Entry._leg_sum(
                record.account_id, 'bank', until=record.date_from - timedelta(days=1))
            record.opening_discrepancy = record.balance_start - before

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('coop_nominal_import'):
            raise UserError(_('Выписка появляется только загрузкой файла банка.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('coop_nominal_import'):
            raise UserError(_('Загруженная выписка не правится.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_('Загруженная выписка не удаляется.'))


class CoopNominalStatementLine(models.Model):
    """Строка выписки: одно поступление или одно списание по счёту.

    Каждая строка проводится в книгу ровно один раз: либо как оплата
    удержания, выплата или комиссия, либо как нераспознанное. Поэтому
    книга по построению сходится с выпиской, а «нераспознанное» показывает,
    сколько денег ещё ждёт разбора.
    """
    _name = 'coop.nominal.statement.line'
    _description = 'Строка выписки по номинальному счёту'
    _order = 'date, id'

    statement_id = fields.Many2one(
        'coop.nominal.statement', string='Выписка', required=True,
        ondelete='restrict', index=True, readonly=True)
    account_id = fields.Many2one(
        related='statement_id.account_id', store=True, index=True, string='Счёт')
    currency_id = fields.Many2one(related='statement_id.currency_id')
    line_key = fields.Char(
        string='Ключ строки', required=True, readonly=True,
        help='Дата, номер, сумма, ИНН и счёт контрагента: по нему одна и та '
             'же строка из двух выписок проводится один раз.')
    direction = fields.Selection([
        ('in', 'Поступление'),
        ('out', 'Списание'),
    ], string='Движение', required=True, readonly=True)
    date = fields.Date(string='Дата', required=True, readonly=True)
    number = fields.Char(string='Номер документа', readonly=True)
    amount = fields.Monetary(
        string='Сумма', currency_field='currency_id', required=True, readonly=True)
    partner_name = fields.Char(string='Контрагент', readonly=True)
    partner_inn = fields.Char(string='ИНН', readonly=True)
    partner_kpp = fields.Char(string='КПП', readonly=True)
    partner_account = fields.Char(string='Счёт контрагента', readonly=True)
    partner_bic = fields.Char(string='БИК', readonly=True)
    purpose = fields.Char(string='Назначение платежа', readonly=True)

    state = fields.Selection([
        ('matched', 'Сопоставлено'),
        ('unrecognized', 'Нераспознано'),
        ('resolved', 'Разобрано вручную'),
    ], string='Разбор', readonly=True, index=True)
    resolution = fields.Selection([
        ('holds', 'Зачтено платежам на удержании'),
        ('refund', 'Возвращено отправителю'),
        ('payout', 'Признано выплатой'),
        ('offset', 'Зачтено встречной строкой'),
    ], string='Как разобрано', readonly=True)
    resolved_by_id = fields.Many2one('res.users', string='Разобрал', readonly=True)
    resolved_on = fields.Date(string='Разобрано', readonly=True)
    counterpart_line_id = fields.Many2one(
        'coop.nominal.statement.line', string='Встречная строка', readonly=True,
        ondelete='restrict')
    refund_payout_ids = fields.One2many(
        'coop.nominal.payout', 'source_line_id', string='Возврат')
    match_rule = fields.Selection([
        ('code', 'По коду удержания'),
        ('inn_amount', 'По ИНН и сумме'),
        ('payout', 'Выплата из реестра'),
        ('fee', 'Комиссия оператору'),
    ], string='Как сопоставлено', readonly=True)
    hold_ids = fields.Many2many(
        'coop.nominal.hold', string='Удержания', readonly=True)
    payout_id = fields.Many2one(
        'coop.nominal.payout', string='Выплата', readonly=True, ondelete='restrict')
    note = fields.Char(string='Почему не распознано', readonly=True)
    entry_ids = fields.One2many(
        'coop.nominal.entry', 'statement_line_id', string='Книга')

    _key_unique = models.Constraint(
        'unique(account_id, line_key)',
        'Эта строка выписки уже проведена.',
    )
    _amount_positive = models.Constraint(
        'CHECK(amount > 0)',
        'Сумма строки выписки — больше нуля.',
    )

    # Что пришло из банка, не меняется; меняется только разбор.
    _BANK_FIELDS = {'statement_id', 'line_key', 'direction', 'date', 'number',
                    'amount', 'partner_name', 'partner_inn', 'partner_kpp',
                    'partner_account', 'partner_bic', 'purpose'}

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('coop_nominal_import'):
            raise UserError(_('Строка выписки появляется только загрузкой файла банка.'))
        return super().create(vals_list)

    def write(self, vals):
        if self._BANK_FIELDS & set(vals):
            raise UserError(_('Строка выписки — слова банка: её не правят.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_('Строки выписки не удаляются.'))

    @api.depends('number', 'date', 'amount', 'direction')
    def _compute_display_name(self):
        for line in self:
            line.display_name = _('№%(number)s от %(date)s, %(sign)s%(amount)s') % {
                'number': line.number or '?',
                'date': line.date and line.date.strftime('%d.%m.%Y'),
                'sign': '−' if line.direction == 'out' else '',
                'amount': '%.2f' % line.amount,
            }

    def _codes(self):
        return {int(code) for code in HOLD_CODE.findall(self.purpose or '')}

    def _process(self):
        """Провести строки в книгу: сопоставить или отложить в нераспознанное."""
        for line in self.sorted(lambda l: (l.date, l.id)):
            if line.direction == 'in':
                line._process_incoming()
            else:
                line._process_outgoing()
        return True

    def _process_incoming(self):
        self.ensure_one()
        Hold = self.env['coop.nominal.hold'].sudo()
        currency = self.currency_id
        codes = self._codes()
        holds, rule, note = Hold, False, False
        if codes:
            found = Hold.browse(sorted(codes)).exists().filtered(
                lambda h: h.account_id == self.account_id)
            waiting = found.filtered(lambda h: h.state == 'awaiting')
            if not found:
                note = _('В назначении код, которого нет на этом счёте.')
            elif waiting != found:
                note = _('Удержание по коду уже оплачено или закрыто.')
            elif currency.compare_amounts(sum(waiting.mapped('amount')), self.amount):
                note = _('Сумма не совпала: ждали %s.') % sum(waiting.mapped('amount'))
            else:
                holds, rule = waiting, 'code'
        elif self.partner_inn:
            found = Hold.search([
                ('account_id', '=', self.account_id.id),
                ('state', '=', 'awaiting'),
                ('payer_id.vat', '=', self.partner_inn),
                ('amount', '=', self.amount),
            ])
            if len(found) == 1:
                holds, rule = found, 'inn_amount'
            elif found:
                note = _('Без кода, а удержаний с этим ИНН и суммой несколько.')
            else:
                note = _('Без кода, и по ИНН и сумме ничего не ждёт оплаты.')
        else:
            note = _('Без кода и без ИНН плательщика.')
        if holds:
            holds._credit(self.date, statement_line=self)
            self.write({'state': 'matched', 'match_rule': rule,
                        'hold_ids': [(6, 0, holds.ids)]})
        else:
            self._post_unrecognized(note)

    def _process_outgoing(self):
        self.ensure_one()
        Payout = self.env['coop.nominal.payout'].sudo()
        account = self.account_id
        currency = self.currency_id
        live = Payout.search([
            ('account_id', '=', account.id),
            ('state', 'in', LIVE),
        ]).filtered(lambda p: not currency.compare_amounts(p.amount, self.amount))
        codes = self._codes()
        payout = live.filtered(lambda p: p.hold_id.id in codes) if codes else Payout
        if not payout and self.partner_inn:
            payout = live.filtered(
                lambda p: (p.recipient_inn or p.partner_id.vat) == self.partner_inn)
        if len(payout) == 1:
            payout._mark_executed(self.date, statement_line=self)
            self.write({'state': 'matched', 'match_rule': 'payout',
                        'payout_id': payout.id, 'hold_ids': [(6, 0, payout.hold_id.ids)]})
            return
        # Оператор забирает свою комиссию на свой счёт — не больше, чем
        # набралось.
        Entry = self.env['coop.nominal.entry']
        fee_due = -Entry._leg_sum(account, 'fee')
        owner_inn = account.owner_id.vat
        if (not payout and owner_inn and self.partner_inn == owner_inn
                and currency.compare_amounts(self.amount, fee_due) <= 0):
            Entry._post(account, 'fee', self.date, [
                {'leg': 'fee', 'amount': self.amount},
                {'leg': 'bank', 'amount': -self.amount},
            ], statement_line=self)
            self.write({'state': 'matched', 'match_rule': 'fee'})
            return
        self._post_unrecognized(
            _('Несколько выплат подходят под списание.') if payout
            else _('Списание, которого нет в реестре выплат.'))

    def _post_unrecognized(self, note):
        """Деньги на счёте есть (или ушли), а чьи — неизвестно.

        Проводим их на заглушку «нераспознанное»: книга сходится с банком,
        а остаток заглушки показывает, что ждёт разбора.
        """
        self.ensure_one()
        sign = 1 if self.direction == 'in' else -1
        self.env['coop.nominal.entry']._post(self.account_id, 'unrecognized', self.date, [
            {'leg': 'bank', 'amount': sign * self.amount},
            {'leg': 'unrecognized', 'amount': -sign * self.amount},
        ], statement_line=self)
        self.write({'state': 'unrecognized', 'note': note})

    # Ручной разбор нераспознанного. Каждое действие закрывает строку
    # целиком: поделить одно поступление между разными исходами нельзя,
    # иначе остаток нераспознанного потом не сведёшь со строками.

    def _expect_unrecognized(self, direction=None):
        for line in self:
            if line.state != 'unrecognized':
                raise UserError(_('Строка №%s уже разобрана.') % line.number)
            if direction and line.direction != direction:
                raise UserError(_(
                    'Строка №%s — не то движение для этого разбора.') % line.number)
            if line.refund_payout_ids.filtered(lambda p: p.state in LIVE):
                raise UserError(_(
                    'По строке №%s уже поставлен возврат: дождитесь его в выписке '
                    'или снимите.') % line.number)

    def _mark_resolved(self, resolution, **vals):
        vals.update({
            'state': 'resolved',
            'resolution': resolution,
            'resolved_by_id': self.env.user.id,
            'resolved_on': fields.Date.context_today(self),
        })
        return self.sudo().write(vals)

    def _resolve_holds(self, holds):
        """Нераспознанное поступление — это оплата этих удержаний."""
        self.ensure_one()
        self._expect_unrecognized('in')
        holds = holds.sudo()
        if not holds or holds.account_id != self.account_id:
            raise UserError(_('Выберите удержания этого же счёта.'))
        if self.currency_id.compare_amounts(sum(holds.mapped('amount')), self.amount):
            raise UserError(_(
                'Сумма удержаний %(holds)s не равна поступлению %(amount)s.',
                holds=sum(holds.mapped('amount')), amount=self.amount))
        holds._credit(self.date, statement_line=self, from_unrecognized=True)
        return self._mark_resolved('holds', hold_ids=[(6, 0, holds.ids)])

    def _resolve_refund(self):
        """Чужие или ошибочные деньги — вернуть тому, кто прислал.

        Строка остаётся нераспознанной, пока возврат не увидим в выписке.
        """
        self.ensure_one()
        self._expect_unrecognized('in')
        if not (self.partner_account and self.partner_bic):
            raise UserError(_(
                'В строке №%s нет счёта или БИК отправителя: вернуть некуда.')
                % self.number)
        self.account_id._check_payouts_allowed()
        return self.env['coop.nominal.payout'].sudo().create({
            'source_line_id': self.id,
            'kind': 'refund',
            'amount': self.amount,
        })

    def _resolve_payout(self, payout):
        """Нераспознанное списание — это исполненная выплата из реестра."""
        self.ensure_one()
        self._expect_unrecognized('out')
        payout = payout.sudo()
        if payout.account_id != self.account_id or payout.state not in LIVE:
            raise UserError(_('Выберите выплату этого счёта, которая ещё в работе.'))
        if self.currency_id.compare_amounts(payout.amount, self.amount):
            raise UserError(_(
                'Сумма выплаты %(payout)s не равна списанию %(amount)s.',
                payout=payout.amount, amount=self.amount))
        payout._mark_executed(self.date, statement_line=self, from_unrecognized=True)
        return self._mark_resolved(
            'payout', payout_id=payout.id, hold_ids=[(6, 0, payout.hold_id.ids)])

    def _resolve_offset(self, other):
        """Встречные строки гасят друг друга: ошибочное списание и его
        возврат, деньги, ушедшие и вернувшиеся. В книге проводить нечего —
        в нераспознанном они уже дают ноль."""
        self.ensure_one()
        other = other.sudo()
        (self | other)._expect_unrecognized()
        if (len(other) != 1 or other == self or other.account_id != self.account_id
                or other.direction == self.direction
                or self.currency_id.compare_amounts(other.amount, self.amount)):
            raise UserError(_(
                'Встречная строка — того же счёта, обратного движения и на ту же сумму.'))
        self._mark_resolved('offset', counterpart_line_id=other.id)
        other._mark_resolved('offset', counterpart_line_id=self.id)
        return True

    def action_resolve(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Разобрать строку выписки'),
            'res_model': 'coop.nominal.statement.resolve',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_line_id': self.id},
        }


class CoopNominalAccountStatement(models.Model):
    _inherit = 'coop.nominal.account'

    statement_ids = fields.One2many(
        'coop.nominal.statement', 'account_id', string='Выписки')

    def _import_statement(self, data, file_name=False):
        """Загрузить выписку 1С: строки — в книгу, конечный остаток — в сверку."""
        self.ensure_one()
        account = self.sudo()
        if not account.account_number:
            raise UserError(_(
                'У счёта %s не указан расчётный счёт: не с чем сверить выписку.')
                % account.display_name)
        file_hash = hashlib.sha256(data).hexdigest()
        Statement = self.env['coop.nominal.statement'].sudo().with_context(
            coop_nominal_import=True)
        if Statement.search_count([('account_id', '=', account.id),
                                   ('file_hash', '=', file_hash)]):
            raise UserError(_('Эта выписка уже загружена.'))

        _header, sections, documents = parse_1c(data)
        number = account.account_number
        sections = sorted(
            (s for s in sections if s.get('РасчСчет') == number),
            key=lambda s: _date(s.get('ДатаНачала')) or datetime.min.date())
        if not sections:
            raise UserError(_('В файле нет выписки по счёту %s.') % number)
        date_from = _date(sections[0].get('ДатаНачала'))
        date_to = _date(sections[-1].get('ДатаКонца'))
        balance_start = _amount(sections[0].get('НачальныйОстаток'))
        balance_end = _amount(sections[-1].get('КонечныйОстаток'))
        if not date_to or balance_end is None:
            raise UserError(_('В выписке нет даты конца или конечного остатка.'))

        Line = self.env['coop.nominal.statement.line'].sudo()
        known = set(Line.search([('account_id', '=', account.id)]).mapped('line_key'))
        line_vals, skipped = [], 0
        for doc in documents:
            payer = doc.get('ПлательщикСчет') or doc.get('ПлательщикРасчСчет')
            payee = doc.get('ПолучательСчет') or doc.get('ПолучательРасчСчет')
            if (payer == number) == (payee == number):
                continue  # чужой счёт в общем файле или перевод самому себе
            side, direction = ('Получатель', 'out') if payer == number else ('Плательщик', 'in')
            date = _date(doc.get('ДатаСписано' if direction == 'out' else 'ДатаПоступило')) \
                or _date(doc.get('Дата'))
            amount = _amount(doc.get('Сумма'))
            if not date or not amount or amount <= 0:
                raise UserError(_(
                    'Документ №%s в выписке без даты или суммы.') % doc.get('Номер', '?'))
            inn = doc.get(side + 'ИНН', '')
            partner_account = doc.get(side + 'Счет') or doc.get(side + 'РасчСчет', '')
            key = hashlib.sha256('|'.join([
                direction, date.isoformat(), doc.get('Номер', ''), '%.2f' % amount,
                inn, partner_account,
            ]).encode()).hexdigest()
            if key in known:
                skipped += 1
                continue
            known.add(key)
            line_vals.append({
                'line_key': key,
                'direction': direction,
                'date': date,
                'number': doc.get('Номер'),
                'amount': amount,
                'partner_name': doc.get(side + '1') or doc.get(side),
                'partner_inn': inn,
                'partner_kpp': doc.get(side + 'КПП'),
                'partner_account': partner_account,
                'partner_bic': doc.get(side + 'БИК'),
                'purpose': doc.get('НазначениеПлатежа'),
            })

        statement = Statement.create({
            'name': _('Выписка %(start)s — %(end)s') % {
                'start': date_from and date_from.strftime('%d.%m.%Y'),
                'end': date_to.strftime('%d.%m.%Y')},
            'account_id': account.id,
            'file_name': file_name,
            'file_hash': file_hash,
            'date_from': date_from,
            'date_to': date_to,
            'balance_start': balance_start or 0.0,
            'balance_end': balance_end,
            'total_in': sum(_amount(s.get('ВсегоПоступило')) or 0.0 for s in sections),
            'total_out': sum(_amount(s.get('ВсегоСписано')) or 0.0 for s in sections),
            'uploaded_by_id': self.env.user.id,
            'skipped_count': skipped,
            'line_ids': [(0, 0, vals) for vals in line_vals],
        })
        statement.line_ids._process()
        # Сверяем по самой свежей выписке: старая, загруженная задним
        # числом, не должна откатить остаток.
        if not account.statement_date or date_to >= account.statement_date:
            account.write({'statement_balance': balance_end, 'statement_date': date_to})
        return statement.with_env(self.env)

    def action_import_statement(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Загрузить выписку'),
            'res_model': 'coop.nominal.statement.import',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_account_id': self.id},
        }

