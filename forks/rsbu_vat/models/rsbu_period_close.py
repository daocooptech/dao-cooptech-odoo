"""Регламентные операции закрытия периода (РСБУ, УСН+НДС).

Документ конца квартала, порождающий регламентные РСБУ-проводки, которых
нет среди первичных документов:

* вычет авансового НДС по зачтённым облагаемым авансам
  (Дт vat_output(68.02) — Кт vat_advance(76.АВ)) — «формирование записей
  книги покупок»;
* перенос налогов на единый налоговый счёт (ЕНС):
  Дт 68.02 — Кт 68.90 (НДС), Дт 68.12 — Кт 68.90 (УСН);
* начисление налога УСН: Дт 99.01.1 — Кт 68.12.

Каждая операция создаёт отдельную rsbu.move (сводную регламентную) и
хранит ссылку для отмены/переигрывания. Суммы берутся из сальдо/оборотов
счётов РСБУ-журнала (get_balance / get_origin_balances), без внешних данных.
"""
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class RsbuPeriodClose(models.Model):
    _name = 'rsbu.period.close'
    _description = 'РСБУ — Закрытие периода (регламент)'
    _order = 'date_to desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Наименование', compute='_compute_name',
                       store=True)
    # Закрытие помесячное (как в 1С). Период задаётся месяцем; границы
    # date_from/date_to вычисляются как первый/последний день месяца.
    period_month = fields.Date(
        string='Месяц закрытия', required=True,
        default=lambda self: fields.Date.today().replace(day=1),
        help='Любая дата месяца; закрытие выполняется за календарный месяц.')
    date_from = fields.Date(string='Период с', compute='_compute_period',
                            store=True)
    date_to = fields.Date(string='Период по', compute='_compute_period',
                          store=True)
    company_id = fields.Many2one(
        'res.company', string='Компания', required=True, index=True,
        default=lambda self: self.env.company)
    move_ids = fields.Many2many(
        'rsbu.move', string='Регламентные проводки', copy=False)
    move_count = fields.Integer(compute='_compute_move_count')
    state = fields.Selection(
        selection=[('draft', 'Черновик'), ('done', 'Проведён')],
        default='draft', string='Состояние', copy=False)

    @api.constrains('period_month', 'company_id')
    def _check_unique_month(self):
        for rec in self:
            if not rec.period_month:
                continue
            dup = self.search([
                ('id', '!=', rec.id),
                ('company_id', '=', rec.company_id.id),
                ('period_month', '>=', rec.date_from),
                ('period_month', '<=', rec.date_to),
            ], limit=1)
            if dup:
                raise ValidationError(_(
                    'Закрытие за этот месяц уже существует: %s.') % dup.name)

    _MONTH_NAMES = [
        '', 'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
        'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']

    @api.depends('period_month', 'company_id')
    def _compute_period(self):
        """Границы календарного месяца по period_month."""
        import calendar
        for rec in self:
            if not rec.period_month:
                rec.date_from = rec.date_to = False
                continue
            first = rec.period_month.replace(day=1)
            last_day = calendar.monthrange(first.year, first.month)[1]
            rec.date_from = first
            rec.date_to = first.replace(day=last_day)

    @api.depends('period_month')
    def _compute_name(self):
        for rec in self:
            if rec.period_month:
                rec.name = _('Закрытие: %(m)s %(y)s',
                             m=self._MONTH_NAMES[rec.period_month.month],
                             y=rec.period_month.year)
            else:
                rec.name = _('Закрытие периода')

    def _is_quarter_end(self):
        """Месяц — последний в квартале (март/июнь/сентябрь/декабрь)."""
        self.ensure_one()
        return bool(self.period_month) and self.period_month.month in (3, 6, 9, 12)

    def _is_year_end(self):
        """Месяц — декабрь (для реформации баланса)."""
        self.ensure_one()
        return bool(self.period_month) and self.period_month.month == 12

    @api.depends('move_ids')
    def _compute_move_count(self):
        for rec in self:
            rec.move_count = len(rec.move_ids)

    # ------------------------------------------------------------------
    def _acc(self, code):
        return self.env['rsbu.account'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('code', '=', code)], limit=1)

    def _role_account(self, role):
        rec = self.env['rsbu.operation.template.role'].sudo().search([
            ('role', '=', role),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        return rec.account_id

    def _new_move(self, ref, lines):
        """Создать и провести регламентную rsbu.move; вернуть её."""
        self.ensure_one()
        move = self.env['rsbu.move'].sudo().create({
            'date': self.date_to,
            'company_id': self.company_id.id,
            'ref': ref,
            'line_ids': [(0, 0, ln) for ln in lines],
        })
        move.action_post()
        self.move_ids = [(4, move.id)]
        return move

    def _has_move_by_ref(self, ref):
        """Идемпотентность: уже есть регламентная проводка с таким ref."""
        self.ensure_one()
        return any(m.ref == ref for m in self.move_ids)

    def _month_turnover(self, account):
        """Обороты Дт/Кт счёта (без потомков) за месяц закрытия."""
        self.ensure_one()
        return account.get_turnover(
            date_from=self.date_from, date_to=self.date_to,
            company_id=self.company_id.id, include_children=False)

    # ------------------------------------------------------------------
    # Регламент: закрытие затрат 26 → 90.08 (директ-костинг)
    # ------------------------------------------------------------------
    def action_close_expenses(self):
        """Списать общехозяйственные расходы (26) на 90.08 (директ-костинг).

        Дебетовый оборот 26 за месяц переносится проводкой
        Дт 90.08 — Кт 26; счёт 26 на конец месяца обнуляется.
        """
        for rec in self:
            ref = _('Закрытие счёта 26 (директ-костинг)')
            if rec._has_move_by_ref(ref):
                continue
            acc26 = rec._acc('26')
            acc9008 = rec._acc('90.08.1') or rec._acc('90.08')
            if not acc26 or not acc9008:
                continue
            turnover = rec._month_turnover(acc26)
            amount = round(turnover['debit'] - turnover['credit'], 2)
            if amount <= 0:
                continue
            rec._new_move(ref, [
                {'account_id': acc9008.id, 'debit': amount,
                 'name': _('Управленческие расходы')},
                {'account_id': acc26.id, 'credit': amount,
                 'name': _('Списаны общехозяйственные расходы')},
            ])
        return True

    # ------------------------------------------------------------------
    # Регламент: закрытие 90 → 99 и 91 → 99 через 90.09 / 91.09
    # ------------------------------------------------------------------
    def _close_result_group(self, group_code, result_sub_code, ref):
        """Закрыть результатный счёт (90/91) на 99 через итоговый субсчёт.

        1. Каждый субсчёт группы (кроме итогового *.09) закрывается за месяц
           встречной проводкой на итоговый субсчёт (90.09/91.09), обнуляя
           свой месячный оборот.
        2. Итоговый субсчёт переносится на 99.01.1: прибыль
           Дт *.09 — Кт 99.01.1, убыток — обратной проводкой.

        Универсально для обоих планов (коды субсчетов берутся из дерева,
        а не хардкодятся: 1С 90.01.1 vs 94н 90.01).
        """
        self.ensure_one()
        group = self._acc(group_code)
        result_sub = self._acc(result_sub_code)
        profit = self._acc('99.01.1') or self._acc('99.01') or self._acc('99')
        if not group or not result_sub or not profit:
            return
        if self._has_move_by_ref(ref):
            return
        # Листовые субсчета группы, кроме итогового (*.09) и самой группы.
        Account = self.env['rsbu.account'].sudo()
        subs = Account.search([
            ('id', 'child_of', group.id),
            ('id', '!=', group.id),
            ('id', '!=', result_sub.id),
            ('company_id', '=', self.company_id.id),
        ])
        # Только листья (без промежуточных групп вроде 90.01 над 90.01.1).
        leaf_subs = subs.filtered(lambda a: not a.child_ids)
        lines = []
        net = 0.0  # + прибыль (Кт группы больше), − убыток
        for sub in leaf_subs:
            t = self._month_turnover(sub)
            debit = round(t['debit'], 2)
            credit = round(t['credit'], 2)
            # Закрываем субсчёт встречной суммой на итоговый субсчёт.
            diff = round(credit - debit, 2)
            if diff > 0:
                # У субсчёта кредитовый оборот (выручка) → Дт суб — Кт *.09.
                lines.append({'account_id': sub.id, 'debit': diff,
                              'name': _('Закрытие субсчёта')})
                lines.append({'account_id': result_sub.id, 'credit': diff,
                              'name': _('Финрезультат')})
                net += diff
            elif diff < 0:
                # Дебетовый оборот (расходы/НДС) → Дт *.09 — Кт суб.
                amt = -diff
                lines.append({'account_id': result_sub.id, 'debit': amt,
                              'name': _('Финрезультат')})
                lines.append({'account_id': sub.id, 'credit': amt,
                              'name': _('Закрытие субсчёта')})
                net -= amt
        # Перенос итогового субсчёта на 99.01.1.
        net = round(net, 2)
        if net > 0:  # прибыль: Дт *.09 — Кт 99.01.1
            lines.append({'account_id': result_sub.id, 'debit': net,
                          'name': _('Прибыль от продаж')})
            lines.append({'account_id': profit.id, 'credit': net,
                          'name': _('Прибыль отнесена на 99')})
        elif net < 0:  # убыток: Дт 99.01.1 — Кт *.09
            amt = -net
            lines.append({'account_id': profit.id, 'debit': amt,
                          'name': _('Убыток отнесён на 99')})
            lines.append({'account_id': result_sub.id, 'credit': amt,
                          'name': _('Убыток от продаж')})
        if lines:
            self._new_move(ref, lines)

    def action_close_pl(self):
        """Закрыть счета продаж (90) и прочих доходов/расходов (91) на 99."""
        for rec in self:
            rec._close_result_group('90', '90.09', _('Закрытие счёта 90'))
            rec._close_result_group('91', '91.09', _('Закрытие счёта 91'))
        return True

    # ------------------------------------------------------------------
    # Регламент: реформация баланса (только декабрь)
    # ------------------------------------------------------------------
    def action_reform_balance(self):
        """Реформация баланса (закрытие года): сальдо 99 → 84.

        Выполняется только для декабря. Субсчета 90/91 к этому моменту
        обнулены ежемесячным закрытием (Этап 4); переносим итоговое сальдо
        99 (накопленную прибыль/убыток года) на 84.
        """
        for rec in self:
            if not rec._is_year_end():
                continue
            ref = _('Реформация баланса (99 → 84)')
            if rec._has_move_by_ref(ref):
                continue
            acc99 = rec._acc('99')
            acc84 = rec._acc('84')
            if not acc99 or not acc84:
                continue
            bal = acc99.get_balance(
                date_to=rec.date_to, company_id=rec.company_id.id,
                include_children=True)
            amount = round(bal['balance'], 2)
            if amount <= 0:
                continue
            profit = rec._acc('99.01.1') or rec._acc('99.01') or acc99
            # Прибыль закрывается Дт 90.09/91.09 — Кт 99.01.1, поэтому
            # прибыль года — КРЕДИТОВОЕ сальдо 99, убыток — ДЕБЕТОВОЕ.
            if bal['side'] == 'debit':
                # Дебетовое сальдо 99 → непокрытый убыток: Дт 84 — Кт 99.01.1.
                rec._new_move(ref, [
                    {'account_id': acc84.id, 'debit': amount,
                     'name': _('Непокрытый убыток года')},
                    {'account_id': profit.id, 'credit': amount,
                     'name': _('Списан убыток на 84')},
                ])
            else:
                # Кредитовое сальдо 99 → прибыль: Дт 99.01.1 — Кт 84.
                rec._new_move(ref, [
                    {'account_id': profit.id, 'debit': amount,
                     'name': _('Списана прибыль на 84')},
                    {'account_id': acc84.id, 'credit': amount,
                     'name': _('Нераспределённая прибыль года')},
                ])
        return True

    # ------------------------------------------------------------------
    # Регламент 1: вычет авансового НДС по зачтённым облагаемым авансам
    # ------------------------------------------------------------------
    def _vat_deduction_lines(self):
        """Строки вычета Дт 68.02 — Кт 76.АВ по каждому авансу-основанию.

        По каждому origin с начисленным авансовым НДС (Дт 76.АВ) вычитается
        доля, пропорциональная зачтённой ОБЛАГАЕМОЙ отгрузкой части аванса
        (Дт 62.02 по origin в проводке-реализации, содержащей НДС).
        """
        self.ensure_one()
        Line = self.env['rsbu.move.line'].sudo()
        vat_advance = self._role_account('vat_advance')     # 76.АВ
        vat_output = self._role_account('vat_output')        # 68.02/68.НДС
        advance = self._role_account('advance_received')     # 62.02
        if not (vat_advance and vat_output and advance):
            return []

        dom = [('company_id', '=', self.company_id.id), ('state', '=', 'posted'),
               ('date', '<=', self.date_to)]
        # НДС по origin (Дт 76.АВ).
        data = {}
        for ln in Line.search(dom + [('account_id', '=', vat_advance.id),
                                     ('debit', '>', 0),
                                     ('origin_move_id', '!=', False)]):
            d = data.setdefault(ln.origin_move_id.id, {
                'origin': ln.origin_move_id, 'vat': 0.0,
                'advance': 0.0, 'offset': 0.0, 'partner': ln.partner_id})
            d['vat'] += ln.debit
        # Сумма аванса и зачёт облагаемой отгрузкой (Дт/Кт 62.02 по origin).
        for ln in Line.search(dom + [('account_id', '=', advance.id),
                                     ('origin_move_id', 'in',
                                      list(data.keys()))]):
            d = data.get(ln.origin_move_id.id)
            if not d:
                continue
            if ln.credit:
                d['advance'] += ln.credit
            if ln.debit and self._move_has_vat(ln.move_id, vat_output):
                d['offset'] += ln.debit

        lines = []
        for d in data.values():
            if d['advance'] <= 0 or d['offset'] <= 0:
                continue
            share = min(1.0, d['offset'] / d['advance'])
            vat_deduct = round(d['vat'] * share, 2)
            if vat_deduct <= 0:
                continue
            lines.append({
                'account_id': vat_output.id, 'debit': vat_deduct,
                'name': _('Вычет авансового НДС')})
            lines.append({
                'account_id': vat_advance.id, 'credit': vat_deduct,
                'partner_id': d['partner'].id if d['partner'] else False,
                'origin_move_id': d['origin'].id,
                'name': _('Списан авансовый НДС')})
        return lines

    def _move_has_vat(self, move, vat_output):
        """Есть ли в проводке-реализации начисление НДС (Кт vat_output)."""
        return any(l.account_id == vat_output and l.credit > 0
                   for l in move.line_ids)

    def action_vat_deduction(self):
        """Сформировать проводку вычета авансового НДС (книга покупок)."""
        for rec in self:
            lines = rec._vat_deduction_lines()
            if lines:
                rec._new_move(_('Формирование записей книги покупок'), lines)
        return True

    # ------------------------------------------------------------------
    # Регламент 2: перенос налогов на ЕНС и начисление УСН
    # ------------------------------------------------------------------
    def action_ens_transfer(self):
        """Перенести НДС и УСН на ЕНС (68.90) по кредитовому сальдо счетов."""
        for rec in self:
            ens = rec._acc('68.90')
            vat = rec._role_account('vat_output') or rec._acc('68.02')
            usn = rec._acc('68.12')
            if not ens:
                # Счёт ЕНС есть в 1С-кодировке; в академическом плане 94н
                # его может не быть — перенос на ЕНС тогда пропускаем.
                continue
            lines = []
            for tax_acc in (vat, usn):
                if not tax_acc:
                    continue
                bal = tax_acc.get_balance(
                    date_to=rec.date_to, company_id=rec.company_id.id)
                # Кредитовое сальдо налога → переносим на ЕНС.
                amount = bal['balance'] if bal['side'] == 'credit' else 0.0
                amount = round(amount, 2)
                if amount <= 0:
                    continue
                lines.append({
                    'account_id': tax_acc.id, 'debit': amount,
                    'name': _('Перенос на ЕНС')})
                lines.append({
                    'account_id': ens.id, 'credit': amount,
                    'name': _('Перенос на ЕНС: %s') % tax_acc.code})
            if lines:
                rec._new_move(_('Перенос налогов на ЕНС'), lines)
        return True

    # ------------------------------------------------------------------
    # Регламент 3: начисление налога УСН (Дт 99.01.1 — Кт 68.12)
    # ------------------------------------------------------------------
    usn_tax_amount = fields.Monetary(
        string='Налог УСН к начислению', currency_field='currency_id',
        help='Сумма налога УСН за период. Рассчитывается нарастающим итогом '
             'с начала года кнопкой «Рассчитать налог УСН» (база КУДиР × '
             'ставка − вычет взносов − авансы прошлых периодов) либо '
             'вводится вручную. Начисляется проводкой Дт 99.01.1 — Кт 68.12.')
    usn_tax_base = fields.Monetary(
        string='База УСН (нараст.)', currency_field='currency_id',
        help='Налоговая база УСН нарастающим итогом с начала года: доход '
             'раздела I КУДиР (НДС уже исключён).')
    usn_reduction = fields.Monetary(
        string='Вычет (взносы, пособия)', currency_field='currency_id',
        help='Сумма страховых взносов и пособий, уменьшающая налог УСН '
             '«Доходы» (в пределах лимита). Заполняется расчётом из раздела '
             'IV КУДиР; при необходимости корректируется вручную.')
    usn_advance_paid = fields.Monetary(
        string='Авансы УСН прошлых периодов', currency_field='currency_id',
        help='Ранее начисленный налог УСН с начала года (обороты Дт 99.01.1 '
             'до начала периода), вычитается из налога нарастающим итогом.')
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id')

    def _year_start(self):
        """Первое января года периода (для расчёта нарастающим итогом)."""
        self.ensure_one()
        return self.date_to.replace(month=1, day=1) if self.date_to else False

    def _usn_income_base(self, date_from, date_to):
        """Доход раздела I КУДиР за интервал (НДС уже исключён)."""
        self.ensure_one()
        Kudir = self.env['rsbu.kudir.line'].sudo()
        Kudir.recompute_period(date_from, date_to, self.company_id)
        lines = Kudir.search([
            ('company_id', '=', self.company_id.id),
            ('section', '=', 'section_1'),
            ('date', '>=', date_from), ('date', '<=', date_to),
        ])
        return round(sum(lines.mapped('income_amount'))
                     - sum(lines.mapped('expense_amount')), 2)

    def _usn_reduction_amount(self, date_from, date_to):
        """Вычет по УСН «Доходы»: взносы/пособия (раздел IV КУДиР) за период."""
        self.ensure_one()
        Kudir = self.env['rsbu.kudir.line'].sudo()
        lines = Kudir.search([
            ('company_id', '=', self.company_id.id),
            ('section', '=', 'section_4'),
            ('date', '>=', date_from), ('date', '<=', date_to),
        ])
        return round(sum(lines.mapped('expense_amount')), 2)

    def _usn_advance_paid_amount(self, year_start):
        """Ранее начисленный УСН с начала года до начала периода (Дт 99.01.1)."""
        self.ensure_one()
        if not self.date_from:
            return 0.0
        profit = self._acc('99.01.1')
        if not profit:
            return 0.0
        Line = self.env['rsbu.move.line'].sudo()
        lines = Line.search([
            ('account_id', '=', profit.id), ('debit', '>', 0),
            ('company_id', '=', self.company_id.id),
            ('date', '>=', year_start), ('date', '<', self.date_from),
        ])
        return round(sum(lines.mapped('debit')), 2)

    def compute_usn_tax(self):
        """Рассчитать налог УСН нарастающим итогом с начала года.

        Алгоритм (УСН «Доходы» + НДС 5%, п.1 ст.248 НК; методика 1С):
          1. База = доход раздела I КУДиР с начала года (НДС уже исключён);
          2. Исчислено = база × ставка (rsbu_usn_rate);
          3. Уменьшение на взносы/пособия (раздел IV КУДиР) — в пределах
             лимита rsbu_usn_reduction_limit % от исчисленного (50% для
             организаций/ИП с работниками, 100% для ИП без работников);
          4. Минус ранее начисленный УСН с начала года (авансы прошлых
             периодов).
        Результат — налог к начислению за текущий период (Дт 99.01.1 —
        Кт 68.12). Взнос/пособия и авансы показываются отдельными полями
        для прозрачности; их можно скорректировать вручную перед
        начислением.
        """
        for rec in self:
            company = rec.company_id
            year_start = rec._year_start()
            if not year_start:
                continue
            base = rec._usn_income_base(year_start, rec.date_to)
            rate = (company.rsbu_usn_rate or 0.0) / 100.0
            computed = round(base * rate, 2)
            reduction = rec._usn_reduction_amount(year_start, rec.date_to)
            # Лимит уменьшения (для «Доходы»): не более N% исчисленного.
            limit_pct = (company.rsbu_usn_reduction_limit or 0.0) / 100.0
            if company.rsbu_usn_mode == 'usn_income' and limit_pct:
                reduction = min(reduction, round(computed * limit_pct, 2))
            advance_paid = rec._usn_advance_paid_amount(year_start)
            tax = round(computed - reduction - advance_paid, 2)
            rec.usn_tax_base = base
            rec.usn_reduction = reduction
            rec.usn_advance_paid = advance_paid
            rec.usn_tax_amount = max(tax, 0.0)
        return True

    def action_accrue_usn(self):
        """Начислить налог УСН: Дт 99.01.1 — Кт 68.12 на usn_tax_amount."""
        for rec in self:
            amount = round(rec.usn_tax_amount or 0.0, 2)
            if amount <= 0:
                continue
            if rec._has_move_by_ref(_('Начисление налога УСН')):
                continue
            profit = rec._acc('99.01.1') or rec._acc('99.01') or rec._acc('99')
            usn = rec._acc('68.12')
            if not (profit and usn):
                raise UserError(_('Не найдены счета 99.01.1 или 68.12.'))
            rec._new_move(_('Начисление налога УСН'), [
                {'account_id': profit.id, 'debit': amount,
                 'name': _('Начислен налог УСН')},
                {'account_id': usn.id, 'credit': amount,
                 'name': _('Налог УСН к уплате')},
            ])
        return True

    def action_close(self):
        """Полное закрытие месяца в порядке 1С.

        Цепочка (по методике 1С для УСН+НДС):
          1. Закрытие затрат 26 → 90.08 (директ-костинг);
          2. Налоги (только на конец квартала): расчёт и начисление УСН,
             вычет авансового НДС, перенос НДС/УСН на ЕНС;
          3. Финансовый результат: закрытие 90 → 99 и 91 → 99;
          4. Реформация баланса (только декабрь): сальдо 99 → 84.
        """
        for rec in self:
            rec._check_can_close()
            # 1. Затраты.
            rec.action_close_expenses()
            # 2. Налоги — на конец квартала (март/июнь/сентябрь/декабрь).
            if rec._is_quarter_end():
                rec.compute_usn_tax()
                if rec.usn_tax_amount:
                    rec.action_accrue_usn()
                rec.action_vat_deduction()
                rec.action_ens_transfer()
            # 3. Финрезультат.
            rec.action_close_pl()
            # 4. Реформация баланса (декабрь).
            if rec._is_year_end():
                rec.action_reform_balance()
            rec.state = 'done'
            # Закрытый месяц охраняется датой закрытия периода компании
            # (rsbu_journal): задним числом в него не провести.
            company = rec.company_id.sudo()
            if not company.rsbu_lock_date \
                    or company.rsbu_lock_date < rec.date_to:
                company.rsbu_lock_date = rec.date_to
        return True

    def _check_can_close(self):
        """Проверки перед закрытием месяца (даты, завершённость, порядок).

        1. Границы периода должны соответствовать ровно календарному месяцу
           period_month (защита от рассинхрона date_from/date_to).
        2. Нельзя закрывать месяц раньше его окончания (незавершённый или
           будущий месяц).
        3. Нельзя закрывать месяц раньше даты начала учёта РСБУ.
        4. Последовательность (как в 1С): предыдущий месяц должен быть
           закрыт — но только если он не раньше месяца начала учёта. Месяц
           начала учёта закрывается свободно (первый в цепочке).
        5. Повторно закрывать уже закрытый месяц нельзя.
        """
        import calendar
        self.ensure_one()
        if self.state == 'done':
            raise UserError(_('Месяц уже закрыт. Сначала переоткройте.'))
        if not self.period_month:
            raise UserError(_('Не задан месяц закрытия.'))
        # 1. Согласованность границ с месяцем.
        first = self.period_month.replace(day=1)
        last_day = calendar.monthrange(first.year, first.month)[1]
        expected_to = first.replace(day=last_day)
        if self.date_from != first or self.date_to != expected_to:
            raise UserError(_(
                'Период закрытия должен точно соответствовать календарному '
                'месяцу %(m)s %(y)s (с %(f)s по %(t)s). Проверьте поле '
                '«Месяц закрытия».',
                m=self._MONTH_NAMES[first.month], y=first.year,
                f=first, t=expected_to))
        # 2. Месяц должен быть завершён.
        if expected_to >= fields.Date.context_today(self):
            raise UserError(_(
                'Нельзя закрывать незавершённый или будущий месяц: закрытие '
                'возможно только после окончания месяца (%s).') % expected_to)
        # 3. Не раньше месяца начала учёта.
        start = self.company_id.rsbu_accounting_start
        start_month = start.replace(day=1) if start else False
        if start_month and first < start_month:
            raise UserError(_(
                'Учёт РСБУ ведётся с %(s)s. Месяцы до месяца начала учёта '
                'закрывать не требуется.', s=start))
        # 4. Последовательность — только если предыдущий месяц не раньше
        #    месяца начала учёта. Месяц начала учёта — первый в цепочке.
        if not (start_month and first <= start_month):
            prev_last = first - timedelta(days=1)
            prev_first = prev_last.replace(day=1)
            # Требуем закрытым предыдущий месяц, если он в периоде учёта
            # (>= месяца начала) и по нему есть проводки.
            in_accounting = not start_month or prev_first >= start_month
            Line = self.env['rsbu.move.line'].sudo()
            has_prev_postings = bool(Line.search_count([
                ('company_id', '=', self.company_id.id),
                ('state', '=', 'posted'),
                ('date', '>=', prev_first),
                ('date', '<=', prev_last),
            ]))
            if in_accounting and has_prev_postings:
                prev_closed = self.search_count([
                    ('company_id', '=', self.company_id.id),
                    ('state', '=', 'done'),
                    ('date_from', '=', prev_first),
                    ('date_to', '=', prev_last),
                ])
                if not prev_closed:
                    raise UserError(_(
                        'Сначала закройте предыдущий месяц (%(m)s %(y)s): '
                        'закрытие выполняется последовательно.',
                        m=self._MONTH_NAMES[prev_first.month],
                        y=prev_first.year))
        return True

    def action_reopen(self):
        """Отменить регламентные проводки и вернуть в черновик."""
        for rec in self:
            later = self.search_count([
                ('company_id', '=', rec.company_id.id),
                ('state', '=', 'done'),
                ('date_from', '>', rec.date_from),
            ])
            if later:
                raise UserError(_(
                    'Сначала переоткройте более поздние месяцы: '
                    'переоткрытие идёт в обратном порядке.'))
            company = rec.company_id.sudo()
            if company.rsbu_lock_date \
                    and company.rsbu_lock_date >= rec.date_from:
                company.rsbu_lock_date = rec.date_from - timedelta(days=1)
            moves = rec.move_ids.sudo()
            posted = moves.filtered(lambda m: m.state == 'posted')
            if posted:
                posted.action_draft()
            moves.unlink()
            rec.move_ids = [(5, 0, 0)]
            rec.state = 'draft'
        return True
