# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .coop_nominal_payout import LIVE

# Что банк ответил на распоряжение или на вопрос о нём.
#   accepted  — принял к исполнению;
#   review    — принял, но сначала проверит основание (контроль банка);
#   rejected  — отказал, денег не спишет;
#   timeout   — ответа нет: не знаем, принял ли;
#   not_found — распоряжения с этим ключом у банка нет.
BANK_ANSWERS = ('accepted', 'review', 'rejected', 'timeout', 'not_found')


class CoopNominalBankAdapter(models.AbstractModel):
    """Подключение банка к номинальному счёту.

    Каждое подключение — своя модель `coop.nominal.bank.adapter.<код>`
    с тремя действиями: отдать распоряжения, спросить о них, забрать
    выписку. Ответ банка — подсказка: исполненной выплату делает только
    списание в выписке.

    Распоряжение уходит с ключом идемпотентности выплаты. Повтор с тем же
    ключом банк не исполнит второй раз — на этом держатся повторы после
    обрыва связи.
    """
    _name = 'coop.nominal.bank.adapter'
    _description = 'Подключение банка'

    def _submit(self, payouts):
        """Отдать распоряжения. Возвращает {id выплаты: ответ}, где ответ —
        словарь с ключами status (из BANK_ANSWERS), bank_ref, reason."""
        raise NotImplementedError

    def _status(self, payouts):
        """Спросить о распоряжениях. Ответ — как у `_submit`."""
        raise NotImplementedError

    def _fetch_statement(self, account):
        """Выписка файлом 1С или None, если новой нет."""
        raise NotImplementedError


class CoopNominalBankAdapterManual(models.AbstractModel):
    """Ручной режим: распоряжения уходят файлом платёжек, ответы банка
    сотрудник отмечает сам, выписку загружает сам."""
    _name = 'coop.nominal.bank.adapter.manual'
    _inherit = 'coop.nominal.bank.adapter'
    _description = 'Подключение банка: вручную'

    def _submit(self, payouts):
        raise UserError(_(
            'Счёт ведётся вручную: выплаты уходят в банк файлом платёжек.'))

    def _status(self, payouts):
        return {}

    def _fetch_statement(self, account):
        return None


class CoopNominalAccountBank(models.Model):
    _inherit = 'coop.nominal.account'

    def _bank_adapter(self):
        self.ensure_one()
        return self.env['coop.nominal.bank.adapter.%s' % self.adapter]


class CoopNominalPayoutBank(models.Model):
    """Путь выплаты через банк.

    в очереди → (банк принял) отправлено → (списание в выписке) исполнено;
    с контролем банка — через «на проверке банка». Отказ банка — «отклонено»:
    по удержанию можно поставить новую попытку с новым ключом, когда
    причина устранена. Нет ответа — «ответа нет»: спрашиваем банк, и если
    распоряжения у него нет, отдаём его ещё раз с тем же ключом.
    """
    _inherit = 'coop.nominal.payout'

    bank_ref = fields.Char(string='Номер в банке', readonly=True)
    failure_reason = fields.Char(string='Причина отказа', readonly=True)
    submit_count = fields.Integer(
        string='Отправок в банк', readonly=True,
        help='Сколько раз распоряжение с этим ключом уходило в банк. '
             'Больше одного — были обрывы связи; банк исполнит его один раз.')
    submitted_at = fields.Datetime(string='Отправлено', readonly=True)
    # Порог автовыплаты: распоряжение банку подписывает владелец счёта.
    # До порога за него подписывает подключение, выше — уполномоченный
    # человек оператора: взлом сервера не должен открывать весь счёт.
    signed_by_id = fields.Many2one(
        'res.users', string='Подписал', readonly=True, tracking=True)
    signed_at = fields.Datetime(string='Подписано', readonly=True)
    needs_signature = fields.Boolean(
        string='Ждёт подписи', compute='_compute_needs_signature',
        search='_search_needs_signature',
        help='Сумма выше порога автовыплаты: в банк выплата уйдёт после '
             'подписи уполномоченного.')

    @api.depends('hold_id', 'source_line_id', 'kind', 'version')
    def _compute_display_name(self):
        kinds = dict(self._fields['kind']._description_selection(self.env))
        for record in self:
            source = record.hold_id.code or record.source_line_id.display_name or ''
            record.display_name = _('%(kind)s %(source)s, попытка %(version)s') % {
                'kind': kinds.get(record.kind, ''), 'source': source,
                'version': record.version or 1}

    def _over_limit(self):
        """Выше порога автовыплаты счёта. Ручной режим порога не знает:
        платёжки и так подписывает сотрудник в клиент-банке."""
        self.ensure_one()
        account = self.account_id
        return account.adapter != 'manual' and self.currency_id.compare_amounts(
            self.amount, account.auto_payout_limit or 0.0) > 0

    @api.depends('amount', 'state', 'signed_by_id', 'submit_count', 'batch_id',
                 'account_id.adapter', 'account_id.auto_payout_limit')
    def _compute_needs_signature(self):
        for record in self:
            record.needs_signature = bool(
                record.id and not record.signed_by_id
                and record.state in ('queued', 'bank_review') and not record._in_bank()
                and record._over_limit())

    def _search_needs_signature(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            return NotImplemented
        waiting = self.sudo().search([
            ('signed_by_id', '=', False), ('state', 'in', ('queued', 'bank_review')),
        ]).filtered('needs_signature')
        positive = (operator == '=') == value
        return [('id', 'in' if positive else 'not in', waiting.ids)]

    def action_sign(self):
        """Подпись уполномоченного: выплата выше порога уйдёт в банк
        следующим обменом."""
        if not (self.env.is_superuser() or self.env.user.has_group('base.group_system')):
            raise UserError(_('Подписывает выплату уполномоченный оператора счёта.'))
        for record in self.sudo():
            if not record.needs_signature:
                raise UserError(_(
                    'Выплата %s подписи не ждёт.') % record.display_name)
            record.write({'signed_by_id': self.env.user.id,
                          'signed_at': fields.Datetime.now()})
        return True

    def _in_bank(self):
        """Распоряжение уже у банка: отдано подключением или файлом."""
        self.ensure_one()
        return self.state in ('sent', 'unknown') or (
            self.state == 'bank_review' and bool(self.submit_count or self.batch_id))

    def _apply_bank_answer(self, answer):
        """Перевести выплату по ответу банка. Исполненной её не делает
        никакой ответ: только выписка."""
        self.ensure_one()
        status = answer.get('status')
        if status not in BANK_ANSWERS:
            raise UserError(_('Банк ответил непонятно: %s.') % status)
        vals = {}
        if answer.get('bank_ref'):
            vals['bank_ref'] = answer['bank_ref']
        if status == 'accepted':
            vals['state'] = 'sent'
        elif status == 'review':
            vals['state'] = 'bank_review'
        elif status == 'rejected':
            vals.update({'state': 'failed',
                         'failure_reason': answer.get('reason') or _('Банк отказал.')})
        elif status in ('timeout', 'not_found'):
            vals['state'] = 'unknown'
        self.write(vals)

    def _submit_to_bank(self):
        """Отдать в банк выплаты из очереди и те, о которых банк не знает."""
        for account, payouts in self.grouped('account_id').items():
            payouts = payouts.filtered(lambda p: p.state in ('queued', 'unknown') or (
                p.state == 'bank_review' and not p._in_bank()))
            if not payouts:
                continue
            account._check_payouts_allowed()
            # Выше порога без подписи — ждут в очереди, остальные идут.
            payouts -= payouts.filtered('needs_signature')
            if not payouts:
                continue
            # Без реквизитов банк поручение не примет — сразу отказ, чтобы
            # одна такая выплата не держала остальные.
            incomplete = payouts.filtered(lambda p: not (
                p.recipient_name and p.recipient_account and p.recipient_bic))
            for payout in incomplete:
                payout._apply_bank_answer({'status': 'rejected', 'reason': _(
                    'Нет реквизитов получателя: название, счёт или БИК.')})
            payouts -= incomplete
            if not payouts:
                continue
            account._prepare_orders(payouts)
            answers = account._bank_adapter()._submit(payouts)
            now = fields.Datetime.now()
            for payout in payouts:
                payout.write({'submit_count': payout.submit_count + 1,
                              'submitted_at': now})
                payout._apply_bank_answer(
                    answers.get(payout.id) or {'status': 'timeout'})
        return True

    def _poll_bank(self):
        """Спросить банк о выплатах в работе. Не нашёл распоряжения после
        обрыва — отдаём его снова: ключ тот же, двойного списания не будет."""
        for account, payouts in self.grouped('account_id').items():
            payouts = payouts.filtered(lambda p: p.state in LIVE and p._in_bank())
            if not payouts:
                continue
            answers = account._bank_adapter()._status(payouts)
            lost = self.browse()
            for payout in payouts:
                answer = answers.get(payout.id)
                if not answer:
                    continue
                if answer['status'] == 'not_found' and payout.state == 'unknown':
                    lost |= payout
                    continue
                payout._apply_bank_answer(answer)
            if lost:
                lost._submit_to_bank()
        return True

    # Действия сотрудника

    def _source_waits(self):
        """Ждёт ли источник выплаты новой попытки: удержание всё ещё в
        очереди выплаты или возврата, строка — нераспознанная."""
        self.ensure_one()
        siblings = self.source_line_id.refund_payout_ids | self.hold_id.payout_ids
        if (siblings - self).filtered(lambda p: p.state in LIVE):
            return False  # новая попытка уже идёт
        if self.source_line_id:
            return self.source_line_id.state == 'unrecognized'
        expected = 'payout_queued' if self.kind == 'payout' else 'refund_queued'
        return self.hold_id.state == expected

    def action_retry(self):
        """Новая попытка после отказа: новый ключ и свежие реквизиты —
        получатель мог их исправить."""
        Payout = self.env['coop.nominal.payout'].sudo()
        new = Payout
        for record in self.sudo():
            if record.state != 'failed':
                raise UserError(_('Повторить можно только отклонённую выплату.'))
            if not record._source_waits():
                raise UserError(_('Источник выплаты уже не ждёт её: повторять нечего.'))
            record.account_id._check_payouts_allowed()
            vals = {'kind': record.kind}
            if record.source_line_id:
                vals.update(source_line_id=record.source_line_id.id,
                            amount=record.source_line_id.amount)
            else:
                vals.update(hold_id=record.hold_id.id, partner_id=record.partner_id.id,
                            amount=-self.env['coop.nominal.entry']._leg_sum(
                                record.account_id, 'holder', hold=record.hold_id,
                                partner=record.partner_id))
            new |= Payout.create(vals)
        return new

    def action_cancel(self):
        """Снять выплату, пока она не в банке, или отказаться от
        отклонённой: деньги удержания снова лежат за бенефициаром."""
        for record in self.sudo():
            if record._in_bank() or record.state not in ('queued', 'bank_review', 'failed'):
                raise UserError(_(
                    'Выплата уже в банке или закрыта: снять её нельзя, '
                    'ждите выписку или отказ банка.'))
            if record.state != 'failed':
                record.state = 'cancelled'
            hold = record.hold_id
            if hold and record._source_waits():
                hold.state = 'held_seller' if record.kind == 'payout' else 'held_buyer'
        return True

    def action_mark_rejected(self):
        """Ручной режим: банк отказал в клиент-банке."""
        for record in self.sudo():
            if record.state not in ('sent', 'bank_review', 'unknown'):
                raise UserError(_('Отклонить можно только выплату, отправленную в банк.'))
            record._apply_bank_answer({
                'status': 'rejected',
                'reason': _('Отказ банка отметил %s.') % self.env.user.name})
        return True

    def action_mark_accepted(self):
        """Ручной режим: банк закончил проверку и принял поручение."""
        for record in self.sudo():
            if record.state != 'bank_review':
                raise UserError(_('Отметка нужна только выплате на проверке банка.'))
            record._apply_bank_answer({'status': 'accepted'})
        return True
