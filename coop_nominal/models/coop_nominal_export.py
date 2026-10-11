# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes

# Назначение платежа в платёжке — не длиннее 210 знаков.
PURPOSE_MAX = 210


class CoopNominalPaymentBatch(models.Model):
    """Реестр платёжек: файл 1С, который сотрудник оператора загружает в
    клиент-банк и там подписывает.

    Выплата попадает в реестр один раз: второй файл с той же выплатой —
    это второй платёж. Поэтому реестр не правят и не удаляют, а потерянный
    файл скачивают заново из этого же реестра.
    """
    _name = 'coop.nominal.payment.batch'
    _description = 'Реестр платёжек по номинальному счёту'
    _order = 'id desc'

    name = fields.Char(string='Реестр', readonly=True)
    account_id = fields.Many2one(
        'coop.nominal.account', string='Счёт', required=True,
        ondelete='restrict', index=True, readonly=True)
    currency_id = fields.Many2one(related='account_id.currency_id')
    date = fields.Date(string='Дата', readonly=True)
    created_by_id = fields.Many2one('res.users', string='Выгрузил', readonly=True)
    payout_ids = fields.One2many(
        'coop.nominal.payout', 'batch_id', string='Выплаты')
    payout_count = fields.Integer(string='Платёжек', readonly=True)
    amount_total = fields.Monetary(
        string='Сумма', currency_field='currency_id', readonly=True)
    file = fields.Binary(string='Файл', attachment=True, readonly=True)
    file_name = fields.Char(string='Имя файла', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('coop_nominal_export'):
            raise UserError(_('Реестр появляется только выгрузкой выплат со счёта.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('coop_nominal_export'):
            raise UserError(_('Выгруженный реестр не правится.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_('Выгруженный реестр не удаляется.'))

    def action_download(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/file/%s?download=true' % (
                self._name, self.id, self.file_name),
            'target': 'self',
        }


class CoopNominalPayoutExport(models.Model):
    _inherit = 'coop.nominal.payout'

    batch_id = fields.Many2one(
        'coop.nominal.payment.batch', string='Реестр платёжек', readonly=True,
        ondelete='restrict', index=True)
    order_number = fields.Char(
        string='Номер платёжки', readonly=True, index=True,
        help='Номер платёжного поручения в реестре: по нему списание в '
             'выписке находит свою выплату, даже если в назначении нет кода.')
    sent_on = fields.Date(string='Выгружено', readonly=True)
    recipient_bank_name = fields.Char(string='Банк получателя', readonly=True)
    recipient_corr_account = fields.Char(string='Корр. счёт банка получателя', readonly=True)
    purpose = fields.Char(string='Назначение платежа', readonly=True)

    def _payment_purpose(self):
        """Назначение платёжки. Код удержания — первым: выписка находит по
        нему выплату, а длинное название сделки банк может обрезать."""
        self.ensure_one()
        line = self.source_line_id
        if line:
            text = _('Возврат ошибочно зачисленных средств по п/п №%(number)s '
                     'от %(date)s. Без налога (НДС)') % {
                'number': line.number or '?',
                'date': line.date.strftime('%d.%m.%Y')}
        else:
            hold = self.hold_id
            text = (_('%(code)s. Выплата по безопасной сделке «%(deal)s». '
                      'Без налога (НДС)') if self.kind == 'payout' else
                    _('%(code)s. Возврат по безопасной сделке «%(deal)s». '
                      'Без налога (НДС)')) % {
                'code': hold.code, 'deal': hold.deal_id.name or ''}
        return text[:PURPOSE_MAX]


def _ru_bank(env, bic):
    """Название банка и корр. счёт по БИК из справочника банков России.

    Справочник ставит модуль l10n_ru_banks; без него — пусто, и клиент-банк
    подставит корр. счёт по БИК сам.
    """
    if not bic or 'ru.bank' not in env:
        return '', ''
    bank = env['ru.bank'].sudo().search([('bic', '=', bic)], limit=1)
    return bank.name or '', bank.corr_acc_ids[:1].corr_acc or ''


class CoopNominalAccountExport(models.Model):
    _inherit = 'coop.nominal.account'

    bank_corr_account = fields.Char(string='Корр. счёт банка')
    last_order_number = fields.Integer(
        string='Последний номер платёжки', readonly=True,
        help='Номера платёжек сквозные по счёту: банк не примет два '
             'поручения с одним номером за день.')
    batch_ids = fields.One2many(
        'coop.nominal.payment.batch', 'account_id', string='Реестры платёжек')

    def _exportable_payouts(self):
        """Выплаты, которые ещё не уходили в банк ни одним файлом.

        Выплата на проверке банка тоже идёт файлом: проверяет банк
        поручение, а не запись в реестре.
        """
        self.ensure_one()
        return self.env['coop.nominal.payout'].sudo().search([
            ('account_id', '=', self.id),
            ('state', 'in', ('queued', 'bank_review')),
            ('batch_id', '=', False),
        ], order='id')

    def _export_payouts(self):
        """Выгрузить очередь выплат файлом платёжек 1С.

        Выплаты из файла считаются отправленными в банк: снять их с
        очереди спором уже нельзя, исполненными их сделает выписка.
        """
        self.ensure_one()
        account = self.sudo()
        if account.adapter != 'manual':
            raise UserError(_(
                'Счёт %s подключён к банку: выплаты уходят без файла, второй '
                'файл заплатил бы дважды.') % account.display_name)
        account._check_payouts_allowed()
        payouts = account._exportable_payouts()
        if not payouts:
            raise UserError(_('Выгружать нечего: в очереди нет выплат.'))
        account._prepare_orders(payouts)
        today = fields.Date.context_today(self)
        file_name = 'payouts_%s_%s.txt' % (today.strftime('%Y%m%d'), payouts[0].order_number)
        content = account._payment_file(payouts, today)
        batch = self.env['coop.nominal.payment.batch'].sudo().with_context(
            coop_nominal_export=True).create({
                'name': _('Реестр от %(date)s, №%(first)s–%(last)s') % {
                    'date': today.strftime('%d.%m.%Y'),
                    'first': payouts[0].order_number,
                    'last': payouts[-1].order_number},
                'account_id': account.id,
                'date': today,
                'created_by_id': self.env.user.id,
                'payout_count': len(payouts),
                'amount_total': sum(payouts.mapped('amount')),
                'file': BinaryBytes(content, filename=file_name),
                'file_name': file_name,
            })
        payouts.write({'batch_id': batch.id, 'sent_on': today})
        # На проверке банка выплата и остаётся: банк ещё смотрит основание.
        payouts.filtered(lambda p: p.state == 'queued').write({'state': 'sent'})
        return batch.with_env(self.env)

    def _prepare_orders(self, payouts):
        """Проверить реквизиты и пронумеровать поручения. Номер и
        назначение даются один раз: повтор того же поручения идёт под
        прежним номером."""
        self.ensure_one()
        account = self.sudo()
        owner = account.owner_id
        if not (owner.vat and account.account_number and account.bank_bic):
            raise UserError(_(
                'У счёта %s не хватает реквизитов плательщика: ИНН владельца, '
                'расчётного счёта или БИК банка.') % account.display_name)
        incomplete = payouts.filtered(lambda p: not (
            p.recipient_name and p.recipient_account and p.recipient_bic))
        if incomplete:
            raise UserError(_(
                'Нет реквизитов получателя (название, счёт, БИК) у выплат: '
                '%s. Снимите их с очереди или поставьте заново после того, '
                'как получатель заполнит реквизиты.') % ', '.join(
                    p.recipient_name or p.partner_id.display_name or str(p.id)
                    for p in incomplete))
        number = account.last_order_number
        for payout in payouts.filtered(lambda p: not p.order_number):
            number += 1
            bank_name, corr_account = _ru_bank(self.env, payout.recipient_bic)
            payout.write({
                'order_number': str(number),
                'purpose': payout._payment_purpose(),
                'recipient_bank_name': bank_name,
                'recipient_corr_account': corr_account,
            })
        account.last_order_number = number
        return True

    def _payment_file(self, payouts, date):
        """Файл 1CClientBankExchange с платёжными поручениями, в Windows-1251."""
        self.ensure_one()
        owner = self.owner_id
        payer_kpp = owner.kpp if 'kpp' in owner._fields else ''
        bank_name, corr_account = _ru_bank(self.env, self.bank_bic)
        bank_name = self.bank_name or bank_name
        corr_account = self.bank_corr_account or corr_account
        now = fields.Datetime.context_timestamp(self, datetime.now())
        day = date.strftime('%d.%m.%Y')
        lines = [
            '1CClientBankExchange',
            'ВерсияФормата=1.03',
            'Кодировка=Windows',
            'Отправитель=ДАО КООПТЕХ',
            'Получатель=',
            'ДатаСоздания=%s' % day,
            'ВремяСоздания=%s' % now.strftime('%H:%M:%S'),
            'ДатаНачала=%s' % day,
            'ДатаКонца=%s' % day,
            'РасчСчет=%s' % self.account_number,
            'Документ=Платежное поручение',
        ]
        for payout in payouts:
            lines += [
                'СекцияДокумент=Платежное поручение',
                'Номер=%s' % payout.order_number,
                'Дата=%s' % day,
                'Сумма=%.2f' % payout.amount,
                'ПлательщикСчет=%s' % self.account_number,
                'Плательщик=ИНН %s %s' % (owner.vat, owner.name),
                'ПлательщикИНН=%s' % owner.vat,
                'ПлательщикКПП=%s' % (payer_kpp or ''),
                'Плательщик1=%s' % owner.name,
                'ПлательщикРасчСчет=%s' % self.account_number,
                'ПлательщикБанк1=%s' % bank_name,
                'ПлательщикБИК=%s' % self.bank_bic,
                'ПлательщикКорсчет=%s' % corr_account,
                'ПолучательСчет=%s' % payout.recipient_account,
                'Получатель=%s' % (
                    'ИНН %s %s' % (payout.recipient_inn, payout.recipient_name)
                    if payout.recipient_inn else payout.recipient_name),
                'ПолучательИНН=%s' % (payout.recipient_inn or ''),
                'ПолучательКПП=%s' % (payout.recipient_kpp or ''),
                'Получатель1=%s' % payout.recipient_name,
                'ПолучательРасчСчет=%s' % payout.recipient_account,
                'ПолучательБанк1=%s' % (payout.recipient_bank_name or ''),
                'ПолучательБИК=%s' % payout.recipient_bic,
                'ПолучательКорсчет=%s' % (payout.recipient_corr_account or ''),
                'ВидОплаты=01',
                'Очередность=5',
                'Код=0',
                'НазначениеПлатежа=%s' % payout.purpose,
                'КонецДокумента',
            ]
        lines += ['КонецФайла', '']
        return '\r\n'.join(lines).encode('cp1251', errors='replace')

    def action_export_payouts(self):
        self.ensure_one()
        batch = self._export_payouts()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'coop.nominal.payment.batch',
            'res_id': batch.id,
            'view_mode': 'form',
        }
