# -*- coding: utf-8 -*-
"""Наполнение номинального счёта: полгода жизни по неделям.

Удержания заводятся на настоящие позиции графиков оплат сделок, деньги
ходят только выписками банка (файлы 1С через `_import_statement`), акты,
выплаты, возвраты и споры — теми же методами, что и в работе. Поэтому
книга сходится с выпиской по построению, а состояния удержаний
соответствуют сделкам: завершённые выплачены, спорные заморожены,
отменённые сняты, просроченные ждут денег.

Срабатывает один раз: если счёт оператора уже есть, ничего не делает.
"""
import logging
import random
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

ACCOUNT_NAME = 'Номинальный счёт ДАО КООПТЕХ'
WEEKS = 26
INN10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
INN11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
INN12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _inn(rnd, company):
    digits = [rnd.randint(1, 9), rnd.randint(0, 9)] + [rnd.randint(0, 9) for _i in range(7)]
    if company:
        digits.append(sum(d * w for d, w in zip(digits, INN10)) % 11 % 10)
        return ''.join(map(str, digits))
    digits.append(rnd.randint(0, 9))
    digits.append(sum(d * w for d, w in zip(digits, INN11)) % 11 % 10)
    digits.append(sum(d * w for d, w in zip(digits, INN12)) % 11 % 10)
    return ''.join(map(str, digits))


def _bank_account(rnd, prefix, bic):
    """Счёт с верным контрольным ключом (по трём последним цифрам БИК)."""
    body = prefix + '0' + ''.join(str(rnd.randint(0, 9)) for _i in range(11))
    digits = [int(c) for c in bic[-3:] + body]
    total = sum((d * (7, 1, 3)[i % 3]) % 10 for i, d in enumerate(digits))
    key = (total % 10) * 3 % 10
    return body[:8] + str(key) + body[9:]


class CoopNominalAccountFill(models.Model):
    _inherit = 'coop.nominal.account'

    @api.model
    def _fill(self):
        if self.with_context(active_test=False).search_count([('name', '=', ACCOUNT_NAME)]):
            return False
        env = self.env(context=dict(self.env.context, tracking_disable=True,
                                    mail_notrack=True, mail_create_nolog=True))
        return env['coop.nominal.account'].sudo()._fill_run()

    def _fill_requisites(self, partners, rnd):
        """ИНН и расчётный счёт тем, у кого их нет: без них не уйдёт ни
        оплата, ни выплата."""
        banks = self.env['ru.bank'].sudo().search(
            [('corr_acc_ids', '!=', False)], limit=60) if 'ru.bank' in self.env else []
        Bank = self.env['res.partner.bank'].sudo()
        russia = self.env.ref('base.ru')
        for partner in partners:
            company = partner.is_company
            if not partner.vat:
                vals = {'vat': _inn(rnd, company)}
                if not partner.country_id:
                    vals['country_id'] = russia.id
                partner.with_context(no_vat_validation=True).write(vals)
            if not partner.bank_ids:
                bank = rnd.choice(banks) if banks else None
                bic = bank.bic if bank else '044525225'
                Bank.create({
                    'partner_id': partner.id,
                    'account_number': _bank_account(
                        rnd, '40702810' if company else '40817810', bic),
                    'bank_bic': bic,
                    'bank_name': bank.name if bank else 'ПАО СБЕРБАНК',
                })

    def _fill_run(self):
        rnd = random.Random(20261011)
        today = fields.Date.context_today(self)
        start = today - timedelta(weeks=WEEKS)
        start -= timedelta(days=start.weekday())  # с понедельника
        Payment = self.env['coop.deal.payment'].sudo()
        payments = Payment.search([
            ('amount', '>', 0), ('payer_id', '!=', False), ('payee_id', '!=', False),
            ('deal_id.state', 'in', ('active', 'acceptance', 'done', 'disputed',
                                     'agreed', 'cancelled')),
        ], order='due_on, id').filtered(lambda p: p.payer_id != p.payee_id)

        def pay_day(p):
            return p.paid_on if p.state == 'paid' and p.paid_on else p.due_on

        past = payments.filtered(
            lambda p: p.state == 'paid' and start <= pay_day(p) <= today - timedelta(days=2))
        overdue = payments.filtered(lambda p: p.state == 'overdue' and p.due_on >= start)
        planned = payments.filtered(lambda p: p.state == 'planned')
        cancelled = payments.filtered(lambda p: p.state == 'cancelled')
        chosen = (past[:120] | overdue[:24] | planned[:28] | cancelled[:10])
        if not chosen:
            _logger.info('Номинальный счёт: графиков оплат нет, наполнять нечем')
            return False

        operator = self.env['res.partner'].sudo().search(
            [('name', '=', 'ДАО КООПТЕХ — оператор платформы')], limit=1) \
            or self.env.company.partner_id
        self._fill_requisites(operator | chosen.payer_id | chosen.payee_id, rnd)
        operator.is_company = True
        account = self.create({
            'name': ACCOUNT_NAME,
            'owner_id': operator.id,
            'bank_name': 'ПАО СБЕРБАНК',
            'bank_bic': '044525225',
            'account_number': _bank_account(rnd, '40702810', '044525225'),
            'adapter': 'demo',
            'setting_ids': [(0, 0, {
                'date_from': start - timedelta(days=7), 'fee_percent': 2.0,
                'fee_vat_percent': 20.0, 'note': 'Договор номинального счёта',
            })],
        })
        Hold = self.env['coop.nominal.hold'].sudo()
        holds = {}
        for payment in chosen:
            holds[payment.id] = Hold.create({
                'account_id': account.id, 'payment_id': payment.id,
                'payer_id': payment.payer_id.id, 'payee_id': payment.payee_id.id,
                'amount': payment.amount,
            })
        for payment in cancelled[:10]:
            holds[payment.id]._cancel()

        # Чем кончается история каждого оплаченного удержания.
        plan = {}
        for payment in past[:120]:
            deal_state = payment.deal_id.state
            roll = rnd.random()
            if deal_state == 'disputed':
                goal = 'frozen'
            elif deal_state == 'done':
                goal = 'refunded' if roll < 0.08 else 'paid_out'
            elif deal_state == 'acceptance':
                goal = 'held_seller'
            else:
                goal = 'held_buyer' if roll < 0.7 else 'paid_out'
            plan[payment.id] = {
                'hold': holds[payment.id], 'goal': goal,
                'pay_on': max(pay_day(payment), start),
                'code': roll > 0.12,  # без кода — ищем по ИНН и сумме
                'act_after': rnd.randint(3, 21),
            }

        lost = rnd.sample(list(plan), 3)  # придут с ошибкой в назначении
        Order = self.env['coop.nominal.demo.order'].sudo()
        number, pending_unrecognized = 1000, []
        week = start
        while week <= today:
            end = min(week + timedelta(days=6), today - timedelta(days=1))
            if end < week:
                break
            docs = []
            for pid, item in plan.items():
                if week <= item['pay_on'] <= end and item['hold'].state == 'awaiting':
                    number += 1
                    hold, payer = item['hold'], item['hold'].payer_id
                    if pid in lost:
                        purpose = 'Оплата по договору, сумма %s' % hold.amount
                        pending_unrecognized.append(hold)
                    elif item['code']:
                        purpose = 'Оплата по сделке %s, %s' % (hold.code, hold.deal_id.name)
                    else:
                        purpose = 'Оплата по договору %s' % (hold.deal_id.number or '')
                    doc = self._fill_doc('in', number, item['pay_on'], hold.amount,
                                         payer, purpose)
                    if pid in lost:
                        doc['them']['inn'] = ''  # платили с личной карты, без ИНН
                    docs.append(doc)
            # Списания по поручениям, которые банк принял на прошлой неделе.
            for order in Order.search([('account_id', '=', account.id),
                                       ('state', '=', 'accepted'), ('in_statement', '=', False)]):
                payout = order.payout_id
                day = min(end, week + timedelta(days=rnd.randint(0, 2)))
                docs.append(self._fill_doc('out', order.number, day, order.amount,
                                           partner=None, purpose=order.purpose, order=order))
                order.in_statement = True
            # Оператор забирает накопленную комиссию в последнюю неделю месяца.
            fee_due = -self.env['coop.nominal.entry']._leg_sum(account, 'fee')
            if (end + timedelta(days=7)).month != end.month and fee_due > 0:
                number += 1
                docs.append(self._fill_doc('out', number, end, round(fee_due, 2), operator,
                                           'Перечисление вознаграждения оператора за %s' %
                                           end.strftime('%m.%Y')))
            # Чужой платёж раз в квартал — пусть сверке будет что разбирать.
            if week.month in (1, 4, 7, 10) and week.day <= 7:
                number += 1
                stranger = self.env['res.partner'].sudo().browse(
                    rnd.choice((chosen.payer_id).ids))
                docs.append(self._fill_doc('in', number, end, float(rnd.randint(5, 60) * 1000),
                                           stranger, 'Оплата по счёту № %s' % rnd.randint(100, 999)))
            account._fill_import(docs, week, end)

            # Неделя прошла: акты, выплаты, возвраты, споры.
            for item in plan.values():
                hold = item['hold']
                act_on = item['pay_on'] + timedelta(days=item['act_after'])
                if hold.state not in ('held_buyer', 'held_seller') or act_on > end:
                    continue
                if item['goal'] in ('paid_out', 'held_seller') and hold.state == 'held_buyer':
                    hold._act(act_on)
                if item['goal'] == 'paid_out' and hold.state == 'held_seller':
                    hold._queue_payout()
                elif item['goal'] == 'refunded' and hold.state == 'held_buyer':
                    hold._queue_refund()
                elif item['goal'] == 'frozen':
                    hold._freeze()
            live = self.env['coop.nominal.payout'].sudo().search([
                ('account_id', '=', account.id), ('state', 'in', ('queued', 'unknown'))])
            live._submit_to_bank()
            live._poll_bank()
            if end < today - timedelta(days=14):
                for failed in live.filtered(lambda p: p.state == 'failed'):
                    failed.action_retry().with_context(coop_demo_fault='none')._submit_to_bank()
            # Нераспознанное разбирают руками через неделю-две.
            for line in account.statement_ids.line_ids.filtered(
                    lambda l: l.state == 'unrecognized' and l.direction == 'in'
                    and l.date < end - timedelta(days=7)
                    and not l.refund_payout_ids.filtered(
                        lambda p: p.state not in ('failed', 'cancelled', 'executed'))):
                match = [item['hold'] for item in plan.values()
                         if item['hold'].state == 'awaiting'
                         and item['hold'].amount == line.amount
                         and (item['hold'] in pending_unrecognized
                              or item['hold'].payer_id.vat == line.partner_inn)]
                if match:
                    line._resolve_holds(match[0])
                elif end < today - timedelta(days=21):
                    line._resolve_refund()
            week += timedelta(days=7)
        account._reconcile()
        _logger.info('Номинальный счёт наполнен: удержаний %s, выписок %s',
                     len(holds), len(account.statement_ids))
        return True

    def _fill_doc(self, direction, number, date, amount, partner, purpose,
                  order=None):
        if order:
            them = {'name': order.recipient_name, 'inn': order.recipient_inn or '',
                    'account': order.recipient_account, 'bic': order.recipient_bic}
        else:
            bank = partner.bank_ids[:1]
            them = {'name': partner.name, 'inn': partner.vat or '',
                    'account': bank.account_number or '', 'bic': bank.bank_bic or ''}
        return {'direction': direction, 'number': str(number), 'date': date,
                'amount': amount, 'them': them, 'purpose': purpose}

    def _fill_import(self, docs, date_from, date_to):
        """Выписка за неделю файлом 1С — тем же путём, что от банка."""
        self.ensure_one()
        owner = self.owner_id
        us = {'name': owner.name, 'inn': owner.vat, 'account': self.account_number,
              'bic': self.bank_bic}
        start = self.ledger_balance
        total_in = sum(d['amount'] for d in docs if d['direction'] == 'in')
        total_out = sum(d['amount'] for d in docs if d['direction'] == 'out')
        lines = ['1CClientBankExchange', 'ВерсияФормата=1.03', 'Кодировка=Windows',
                 'Отправитель=%s' % self.bank_name, 'СекцияРасчСчет',
                 'ДатаНачала=%s' % date_from.strftime('%d.%m.%Y'),
                 'ДатаКонца=%s' % date_to.strftime('%d.%m.%Y'),
                 'РасчСчет=%s' % self.account_number, 'НачальныйОстаток=%.2f' % start,
                 'ВсегоПоступило=%.2f' % total_in, 'ВсегоСписано=%.2f' % total_out,
                 'КонечныйОстаток=%.2f' % (start + total_in - total_out), 'КонецРасчСчет']
        for doc in sorted(docs, key=lambda d: d['date']):
            payer, payee = (doc['them'], us) if doc['direction'] == 'in' else (us, doc['them'])
            day = doc['date'].strftime('%d.%m.%Y')
            lines += ['СекцияДокумент=Платежное поручение', 'Номер=%s' % doc['number'],
                      'Дата=%s' % day, 'Сумма=%.2f' % doc['amount'],
                      ('ДатаПоступило=%s' if doc['direction'] == 'in' else 'ДатаСписано=%s') % day]
            for prefix, side in (('Плательщик', payer), ('Получатель', payee)):
                lines += ['%sСчет=%s' % (prefix, side['account']), '%sИНН=%s' % (prefix, side['inn']),
                          '%s1=%s' % (prefix, side['name']), '%sБИК=%s' % (prefix, side['bic'])]
            lines += ['НазначениеПлатежа=%s' % doc['purpose'], 'КонецДокумента']
        lines += ['КонецФайла', '']
        data = '\r\n'.join(lines).encode('cp1251', errors='replace')
        return self._import_statement(data, 'kl_to_1c_%s.txt' % date_to.strftime('%Y%m%d'))
