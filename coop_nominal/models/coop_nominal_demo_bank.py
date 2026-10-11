# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models

# Как демо-банк сбоит. Сбой выбирается по ключу распоряжения, поэтому он
# повторяем: одна и та же выплата на стенде ведёт себя одинаково.
#   lost   — поручение принято, а ответ потерялся: «ответа нет», потом
#            банк на вопрос отвечает «принято»;
#   down   — банк недоступен при первой отправке: поручения у него нет,
#            на вопрос он отвечает «не найдено», и выплата уходит снова;
#   reject — отказ: «счёт получателя закрыт».
FAULTS = {0: 'lost', 1: 'down', 2: 'reject'}


class CoopNominalDemoOrder(models.Model):
    """Поручение в демо-банке — то, что банк знает о нашем распоряжении.

    Одно на ключ идемпотентности: повтор с тем же ключом банк узнаёт и
    второй раз не исполняет.
    """
    _name = 'coop.nominal.demo.order'
    _description = 'Поручение в банке'
    _order = 'id desc'

    account_id = fields.Many2one(
        'coop.nominal.account', string='Счёт', required=True,
        ondelete='cascade', index=True)
    payout_id = fields.Many2one(
        'coop.nominal.payout', string='Выплата', ondelete='set null', index=True)
    idempotency_key = fields.Char(string='Ключ', required=True, index=True)
    number = fields.Char(string='Номер поручения')
    amount = fields.Monetary(string='Сумма', currency_field='currency_id')
    currency_id = fields.Many2one(related='account_id.currency_id')
    recipient_name = fields.Char(string='Получатель')
    recipient_inn = fields.Char(string='ИНН получателя')
    recipient_account = fields.Char(string='Счёт получателя')
    recipient_bic = fields.Char(string='БИК банка получателя')
    purpose = fields.Char(string='Назначение')
    state = fields.Selection([
        ('review', 'На проверке'),
        ('accepted', 'Принято'),
        ('rejected', 'Отказано'),
    ], string='Состояние', required=True)
    reason = fields.Char(string='Причина отказа')
    in_statement = fields.Boolean(string='Списано в выписке', index=True)

    _key_unique = models.Constraint(
        'unique(account_id, idempotency_key)',
        'Банк уже знает поручение с этим ключом.',
    )

    def _answer(self):
        self.ensure_one()
        return {'status': self.state, 'bank_ref': str(4100000 + self.id),
                'reason': self.reason}


class CoopNominalBankAdapterDemo(models.AbstractModel):
    """Демо-банк: принимает распоряжения, иногда сбоит, раз в день и после
    исполнения поручений отдаёт выписку файлом 1С.

    Сбой можно задать контекстом `coop_demo_fault` (lost, down, reject,
    none) — так его выбирают тесты.
    """
    _name = 'coop.nominal.bank.adapter.demo'
    _inherit = 'coop.nominal.bank.adapter'
    _description = 'Подключение банка по API'

    def _fault(self, payout):
        forced = self.env.context.get('coop_demo_fault')
        if forced:
            return None if forced == 'none' else forced
        return FAULTS.get(int(payout.idempotency_key[:8], 16) % 10)

    def _find_order(self, payout):
        return self.env['coop.nominal.demo.order'].sudo().search([
            ('account_id', '=', payout.account_id.id),
            ('idempotency_key', '=', payout.idempotency_key)], limit=1)

    def _submit(self, payouts):
        Order = self.env['coop.nominal.demo.order'].sudo()
        answers = {}
        for payout in payouts:
            order = self._find_order(payout)
            if order:
                # Повтор: банк узнал ключ и отвечает про то же поручение.
                answers[payout.id] = order._answer()
                continue
            fault = self._fault(payout)
            if fault == 'down' and not payout.submit_count:
                answers[payout.id] = {'status': 'timeout'}
                continue
            valid = (re.fullmatch(r'\d{20}', payout.recipient_account or '')
                     and re.fullmatch(r'\d{9}', payout.recipient_bic or ''))
            if not valid:
                state, reason = 'rejected', _('Неверные реквизиты получателя.')
            elif fault == 'reject':
                state, reason = 'rejected', _('Счёт получателя закрыт.')
            else:
                state, reason = ('review' if payout.state == 'bank_review' else 'accepted'), False
            order = Order.create({
                'account_id': payout.account_id.id,
                'payout_id': payout.id,
                'idempotency_key': payout.idempotency_key,
                'number': payout.order_number,
                'amount': payout.amount,
                'recipient_name': payout.recipient_name,
                'recipient_inn': payout.recipient_inn,
                'recipient_account': payout.recipient_account,
                'recipient_bic': payout.recipient_bic,
                'purpose': payout.purpose,
                'state': state,
                'reason': reason,
            })
            answers[payout.id] = {'status': 'timeout'} if fault == 'lost' else order._answer()
        return answers

    def _status(self, payouts):
        answers = {}
        for payout in payouts:
            order = self._find_order(payout)
            if not order:
                answers[payout.id] = {'status': 'not_found'}
                continue
            if order.state == 'review':
                order.state = 'accepted'  # банк закончил проверку
            answers[payout.id] = order._answer()
        return answers

    def _fetch_statement(self, account):
        """Выписка за сегодня: принятые поручения списаны. Пустую тоже
        отдаём раз в день — по ней сверка видит, что банк на связи."""
        orders = self.env['coop.nominal.demo.order'].sudo().search([
            ('account_id', '=', account.id), ('state', '=', 'accepted'),
            ('in_statement', '=', False)], order='id')
        today = fields.Date.context_today(self)
        if not orders and account.statement_date and account.statement_date >= today:
            return None
        day = today.strftime('%d.%m.%Y')
        owner = account.owner_id
        start = account.ledger_balance
        end = start - sum(orders.mapped('amount'))
        lines = [
            '1CClientBankExchange', 'ВерсияФормата=1.03', 'Кодировка=Windows',
            'Отправитель=%s' % (account.bank_name or ''), 'ДатаСоздания=%s' % day,
            'ВремяСоздания=%s' % fields.Datetime.now().strftime('%H:%M:%S.%f'),
            'СекцияРасчСчет', 'ДатаНачала=%s' % day, 'ДатаКонца=%s' % day,
            'РасчСчет=%s' % account.account_number,
            'НачальныйОстаток=%.2f' % start, 'ВсегоСписано=%.2f' % (start - end),
            'КонечныйОстаток=%.2f' % end, 'КонецРасчСчет',
        ]
        for order in orders:
            lines += [
                'СекцияДокумент=Платежное поручение',
                'Номер=%s' % (order.number or order.id), 'Дата=%s' % day,
                'Сумма=%.2f' % order.amount, 'ДатаСписано=%s' % day,
                'ПлательщикСчет=%s' % account.account_number,
                'ПлательщикИНН=%s' % (owner.vat or ''), 'Плательщик1=%s' % owner.name,
                'ПолучательСчет=%s' % order.recipient_account,
                'ПолучательИНН=%s' % (order.recipient_inn or ''),
                'Получатель1=%s' % order.recipient_name,
                'ПолучательБИК=%s' % order.recipient_bic,
                'НазначениеПлатежа=%s' % (order.purpose or ''),
                'КонецДокумента',
            ]
        lines += ['КонецФайла', '']
        orders.write({'in_statement': True})
        return '\r\n'.join(lines).encode('cp1251', errors='replace')


class CoopNominalAccountDemo(models.Model):
    _inherit = 'coop.nominal.account'

    def _fetch_statement(self):
        """Забрать у банка новую выписку и провести её."""
        for account in self.sudo():
            data = account._bank_adapter()._fetch_statement(account)
            if data:
                account._import_statement(data, 'bank_%s.txt' % fields.Date.context_today(account))
        return True

    def action_bank_exchange(self):
        self.ensure_one()
        self._cron_bank_accounts()
        return True

    @api.model
    def _cron_bank(self):
        return self.search([('adapter', '!=', 'manual')])._cron_bank_accounts()

    def _cron_bank_accounts(self):
        """Отдать очередь, опросить банк и забрать выписку — по счетам
        с подключением. Счёт с расхождением ничего не отдаёт, но выписку
        забирает: она может расхождение снять."""
        Payout = self.env['coop.nominal.payout'].sudo()
        for account in self.sudo().filtered(lambda a: a.adapter != 'manual'):
            if not account.payouts_blocked:
                live = Payout.search([('account_id', '=', account.id),
                                      ('state', 'in', ('queued', 'bank_review', 'sent', 'unknown'))])
                live._submit_to_bank()
                live._poll_bank()
            account._fetch_statement()
        return True
