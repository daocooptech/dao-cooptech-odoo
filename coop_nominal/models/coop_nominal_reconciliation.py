# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models

# Через сколько дней выгруженная, но не списанная выплата — повод звонить в банк.
STALE_DAYS = 3


class CoopNominalReconciliation(models.Model):
    """Ежедневная сверка номинального счёта.

    Раз в день смотрим: есть ли выписка за вчера, сходится ли с ней книга,
    не висит ли нераспознанное и не застряли ли в банке выгруженные
    выплаты. Запись за день одна: повторная сверка её обновляет, а история
    по дням показывает, сколько счёт простоял с расхождением.
    """
    _name = 'coop.nominal.reconciliation'
    _description = 'Сверка номинального счёта'
    _order = 'date desc, id desc'

    account_id = fields.Many2one(
        'coop.nominal.account', string='Счёт', required=True,
        ondelete='cascade', index=True, readonly=True)
    currency_id = fields.Many2one(related='account_id.currency_id')
    date = fields.Date(string='Дата сверки', required=True, readonly=True)
    statement_date = fields.Date(string='Выписка на дату', readonly=True)
    statement_balance = fields.Monetary(
        string='Остаток по выписке', currency_field='currency_id', readonly=True)
    ledger_balance = fields.Monetary(
        string='Остаток по реестру', currency_field='currency_id', readonly=True)
    discrepancy = fields.Monetary(
        string='Расхождение', currency_field='currency_id', readonly=True)
    unrecognized_balance = fields.Monetary(
        string='Нераспознанное', currency_field='currency_id', readonly=True)
    unrecognized_count = fields.Integer(string='Строк не разобрано', readonly=True)
    stale_payout_count = fields.Integer(
        string='Выплат застряло в банке', readonly=True,
        help='Выгружены в банк больше %s дней назад, а списания в выписке нет.'
             % STALE_DAYS)
    state = fields.Selection([
        ('ok', 'Сходится'),
        ('problem', 'Есть что разобрать'),
    ], string='Итог', readonly=True, index=True)
    note = fields.Text(string='Что не так', readonly=True)

    _day_unique = models.Constraint(
        'unique(account_id, date)',
        'Сверка счёта за день — одна.',
    )


class CoopNominalAccountReconciliation(models.Model):
    _inherit = 'coop.nominal.account'

    reconciliation_ids = fields.One2many(
        'coop.nominal.reconciliation', 'account_id', string='Сверки')

    def _reconcile(self, date=None):
        """Сверить счета на дату (по умолчанию сегодня) и записать итог.

        Выписку ждём за вчерашний день: сегодняшняя ещё не закрыта.
        О неладном пишем в ленту счёта — её видят подписчики.
        """
        date = date or fields.Date.context_today(self)
        Line = self.env['coop.nominal.statement.line'].sudo()
        Payout = self.env['coop.nominal.payout'].sudo()
        Reconciliation = self.env['coop.nominal.reconciliation'].sudo()
        result = Reconciliation
        for account in self.sudo():
            currency = account.currency_id
            unrecognized = Line.search([
                ('account_id', '=', account.id), ('state', '=', 'unrecognized')])
            stale = Payout.search_count([
                ('account_id', '=', account.id),
                ('state', 'in', ('sent', 'bank_review', 'unknown')),
                ('sent_on', '<', date - timedelta(days=STALE_DAYS)),
            ])
            problems = []
            expected = date - timedelta(days=1)
            if not account.statement_date:
                problems.append(_('Выписка по счёту ещё ни разу не загружена.'))
            elif account.statement_date < expected:
                problems.append(_(
                    'Нет выписки за %(expected)s: последняя загружена на %(last)s.') % {
                    'expected': expected.strftime('%d.%m.%Y'),
                    'last': account.statement_date.strftime('%d.%m.%Y')})
            if account.statement_date and not currency.is_zero(account.discrepancy):
                problems.append(_(
                    'Реестр расходится с выпиской на %s: выплаты остановлены.')
                    % account.discrepancy)
            if unrecognized:
                problems.append(_(
                    'Не разобрано строк выписки: %(count)s, нераспознанное '
                    '%(amount)s.') % {
                    'count': len(unrecognized),
                    'amount': account.unrecognized_balance})
            if stale:
                problems.append(_(
                    'Выплат выгружено в банк больше %(days)s дней назад и не '
                    'видно в выписке: %(count)s.') % {
                    'days': STALE_DAYS, 'count': stale})
            vals = {
                'statement_date': account.statement_date,
                'statement_balance': account.statement_balance,
                'ledger_balance': account.ledger_balance,
                'discrepancy': account.discrepancy if account.statement_date else 0.0,
                'unrecognized_balance': account.unrecognized_balance,
                'unrecognized_count': len(unrecognized),
                'stale_payout_count': stale,
                'state': 'problem' if problems else 'ok',
                'note': '\n'.join(problems) or False,
            }
            record = Reconciliation.search([
                ('account_id', '=', account.id), ('date', '=', date)])
            if record:
                record.write(vals)
            else:
                record = Reconciliation.create(dict(vals, account_id=account.id, date=date))
            if problems:
                account.message_post(body=_('Сверка за %(date)s: %(problems)s') % {
                    'date': date.strftime('%d.%m.%Y'),
                    'problems': ' '.join(problems)})
            result |= record
        return result.with_env(self.env)

    @api.model
    def _cron_reconcile(self):
        self.search([])._reconcile()

    def action_reconcile(self):
        self._reconcile()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Сверки'),
            'res_model': 'coop.nominal.reconciliation',
            'view_mode': 'list',
            'domain': [('account_id', 'in', self.ids)],
        }
