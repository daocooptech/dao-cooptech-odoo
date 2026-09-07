# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CoopCession(models.Model):
    """Предложение уступить требование по сделке.

    Участнику должны через месяц, а деньги нужны сейчас. Он предлагает
    своё требование другому участнику: тот платит меньше номинала, но
    сразу, и дальше сам ждёт срока. Юридически это уступка требования,
    глава 24 ГК.

    Это **доска предложений, а не биржа**, и разница не косметическая.
    Как только заявки начинают сводиться по цене автоматически, получаются
    организованные торги, а их вправе проводить только биржа по лицензии
    Банка России (ст. 5 ФЗ «Об организованных торгах»). Поэтому здесь
    отклик никого ни к чему не обязывает: он открывает переговоры, а
    уступка оформляется договором сторон. Экономический результат для
    участника тот же, лицензия не нужна.

    Три правила встроены в модель, а не написаны мелким шрифтом:

    - размещается только требование, **подтверждённое обеими сторонами**
      (акт по сделке) и не погашенное деньгами. Иначе доска станет местом
      продажи несуществующих долгов, и первый же такой случай закроет её
      целиком;
    - приобретатель — **только участник платформы**. П. 2 ст. 388 ГК
      разрешает ограничить круг, и это защита должника: требование не
      уходит к постороннему без ведома того, кто по нему платит;
    - **должник уведомляется**. Для него уведомление — условие
      действительности уступки (ст. 382, 385 ГК): не уведомили, и
      исполнение прежнему кредитору остаётся надлежащим.

    Цена и дисконт хранятся как есть, без «рекомендуемой» и без подсказок
    рынка: подсказка платформы о справедливой цене — это уже влияние на
    ценообразование, чего мы себе не позволяем.
    """
    _name = 'coop.cession'
    _description = 'Предложение об уступке требования'
    _inherit = ['mail.thread']
    _order = 'published_on desc, id desc'
    _rec_name = 'display_name'

    display_name = fields.Char(compute='_compute_display_name', store=True)

    deal_id = fields.Many2one(
        'coop.deal', string='Требование по сделке', required=True, index=True,
        ondelete='cascade',
        help='Основание требования. Уступается не абстрактный долг, а '
             'конкретное требование по конкретной сделке.')

    creditor_id = fields.Many2one(
        'res.partner', string='Уступает', required=True, index=True,
        help='Текущий кредитор — тот, кому по сделке должны.')
    debtor_id = fields.Many2one(
        'res.partner', string='Должник', required=True, index=True,
        help='Тот, кто платит по требованию. Его уведомляют об уступке.')

    currency_id = fields.Many2one(
        'res.currency', related='deal_id.currency_id', store=True, readonly=True)
    amount = fields.Monetary(
        string='Сумма требования', required=True, currency_field='currency_id',
        help='Номинал: сколько должник должен по сделке.')
    price = fields.Monetary(
        string='Цена уступки', required=True, currency_field='currency_id',
        help='Сколько участник просит за требование. Обычно меньше '
             'номинала: покупатель ждёт срока вместо продавца.')
    discount = fields.Monetary(
        string='Дисконт', compute='_compute_discount', store=True,
        currency_field='currency_id')
    discount_percent = fields.Float(
        string='Дисконт, %', compute='_compute_discount', store=True)

    due_date = fields.Date(
        string='Срок исполнения', index=True,
        help='Когда должник обязан заплатить по сделке.')

    state = fields.Selection([
        ('draft', 'Черновик'),
        ('published', 'Размещено'),
        ('negotiating', 'Идут переговоры'),
        ('done', 'Уступлено'),
        ('cancelled', 'Снято'),
    ], string='Состояние', default='draft', required=True, index=True,
        tracking=True)

    published_on = fields.Datetime(string='Размещено', readonly=True, index=True)
    assignee_id = fields.Many2one(
        'res.partner', string='Приобретатель', readonly=True, index=True,
        help='С кем в итоге оформлена уступка.')
    ceded_on = fields.Date(string='Дата уступки', readonly=True)

    debtor_notified_on = fields.Date(
        string='Должник уведомлён', readonly=True,
        help='Без уведомления исполнение прежнему кредитору остаётся '
             'надлежащим (ст. 382 ГК), то есть уступка для должника не '
             'работает.')

    response_ids = fields.One2many(
        'coop.cession.response', 'cession_id', string='Отклики')
    response_count = fields.Integer(
        string='Откликов', compute='_compute_response_count')

    note = fields.Text(
        string='Условия',
        help='«Готов уступить с рассрочкой оплаты в две недели» — то, чего '
             'не выразить одной ценой.')

    is_mine = fields.Boolean(
        string='Моё предложение', compute='_compute_is_mine',
        search='_search_is_mine',
        help='Своё — то, что размещено от лица участника или от лица '
             'организации, счета которой он ведёт.')

    import_key = fields.Char(string='Ключ источника', index=True, copy=False)

    _price_positive = models.Constraint(
        'check(price > 0)',
        'Цена уступки должна быть больше нуля.',
    )
    _amount_positive = models.Constraint(
        'check(amount > 0)',
        'Уступать требование на ноль не имеет смысла.',
    )

    @api.depends('deal_id.number', 'debtor_id.name', 'amount')
    def _compute_display_name(self):
        for record in self:
            record.display_name = '%s — требование к %s' % (
                record.deal_id.number or _('Без номера'),
                record.debtor_id.name or _('не указан'),
            )

    @api.depends('amount', 'price')
    def _compute_discount(self):
        for record in self:
            record.discount = record.amount - record.price
            record.discount_percent = (
                record.discount / record.amount * 100 if record.amount else 0.0
            )

    @api.depends('response_ids')
    def _compute_response_count(self):
        for record in self:
            record.response_count = len(record.response_ids)

    def _my_partners(self):
        """Партнёры, от чьего лица действует пользователь.

        Не один партнёр, а набор: участник ведёт счета своей организации
        и размещает предложения от её имени. Тот же набор используют
        правила видимости — иначе «мои предложения» и «что мне видно»
        разошлись бы.
        """
        return self.env.user.coop_treasury_partner_ids

    @api.depends_context('uid')
    def _compute_is_mine(self):
        mine = self._my_partners()
        for record in self:
            record.is_mine = record.creditor_id in mine

    def _search_is_mine(self, operator, value):
        # Odoo приводит «= True» к «in {True}» ещё до вызова поиска и
        # передаёт при этом свой набор, а не список. Поэтому значение
        # разбирается как последовательность, а не сверяется с типом:
        # иначе вкладка «моё» падала с ошибкой прямо при открытии.
        if isinstance(value, bool):
            wanted = value
        else:
            items = list(value)
            if len(items) != 1 or not isinstance(items[0], bool):
                raise ValueError('Поддерживается только «моё: да» или «моё: нет».')
            wanted = items[0]
        if operator in ('=', 'in'):
            positive = wanted
        elif operator in ('!=', 'not in'):
            positive = not wanted
        else:
            raise ValueError('Поддерживается только «моё: да» или «моё: нет».')
        return [('creditor_id', 'in' if positive else 'not in',
                 self._my_partners().ids)]

    @api.constrains('creditor_id', 'debtor_id')
    def _check_parties(self):
        for record in self:
            if record.creditor_id == record.debtor_id:
                raise ValidationError(_(
                    'Уступить требование самому себе нельзя: должник и '
                    'кредитор — это две разные стороны.'))

    @api.constrains('amount', 'price')
    def _check_price_not_above_nominal(self):
        """Цена выше номинала — почти всегда ошибка ввода.

        Запрещать её незачем: стороны вправе договориться о чём угодно,
        и бывают требования с процентами. Но молча пропускать опечатку в
        разряде тоже не годится, поэтому предел — двойной номинал.
        """
        for record in self:
            if record.price > record.amount * 2:
                raise ValidationError(_(
                    'Цена уступки больше двойного номинала требования. '
                    'Похоже на опечатку в разряде.'))

    @api.onchange('deal_id')
    def _onchange_deal_id(self):
        """Подставить стороны, сумму и срок из ближайшего платежа.

        Кто кому должен — берётся из графика платежей (`payer_id` и
        `payee_id`), а не из порядка сторон сделки. Порядок сторон ничего
        о направлении долга не говорит: «первая» — это порядок полей, а не
        старшинство, и на покупке знак перевернулся бы. В `coop_deals` об
        эти грабли уже наступали, там об этом написано прямо.

        Если графика нет, поля сторон остаются пустыми: угадывать за
        участника, кто кому должен, — ровно тот случай, когда ошибиться
        хуже, чем не подсказать.
        """
        for record in self:
            deal = record.deal_id
            if not deal:
                continue
            payment = deal.payment_ids.filtered(lambda p: not p.paid_on)[:1]
            if payment:
                record.creditor_id = payment.payee_id
                record.debtor_id = payment.payer_id
                record.due_date = payment.due_on
            else:
                record.due_date = deal.closed_on
            record.amount = deal.amount_due or deal.amount
            record.price = record.price or deal.amount_due or deal.amount

    def action_publish(self):
        """Разместить предложение на витрине.

        Здесь и только здесь проверяется, что требование вообще годится:
        акт подтверждён обеими сторонами, деньги ещё не уплачены, уступка
        не запрещена. Проверка на действии, а не на записи, потому что
        черновик участник вправе завести на что угодно и дособрать
        документы потом.
        """
        for record in self:
            deal = record.deal_id
            if not deal.act_confirmed_a or not deal.act_confirmed_b:
                raise UserError(_(
                    'Акт по сделке подтверждён не обеими сторонами. Пока '
                    'работа не принята, требования ещё нет — размещать '
                    'нечего.'))
            if deal.amount_due <= 0:
                raise UserError(_(
                    'По сделке ничего не должны: остаток уже уплачен.'))
            if deal.cession_forbidden:
                raise UserError(_(
                    'Уступка требования по этой сделке запрещена. %s'
                ) % (deal.cession_forbidden_reason or ''))
            if record.creditor_id not in (deal.party_a_id, deal.party_b_id):
                raise UserError(_(
                    'Уступить требование может только сторона сделки.'))
            record.write({
                'state': 'published',
                'published_on': fields.Datetime.now(),
            })
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    def action_respond(self):
        """Откликнуться на предложение.

        Отклик ни к чему не обязывает и ничего не сводит автоматически —
        он открывает переговоры. Автоматическое сведение по цене
        превратило бы доску в организованные торги.
        """
        me = self.env.user._coop_acting_partner()
        for record in self:
            if record.state not in ('published', 'negotiating'):
                raise UserError(_('Предложение снято или уже исполнено.'))
            if me == record.creditor_id:
                raise UserError(_(
                    'Это ваше собственное предложение.'))
            if record.response_ids.filtered(lambda r: r.partner_id == me):
                raise UserError(_('Вы уже откликнулись на это предложение.'))
            self.env['coop.cession.response'].create({
                'cession_id': record.id,
                'partner_id': me.id,
            })
            record.state = 'negotiating'
        return True

    def action_complete(self):
        """Оформить уступку выбранному приобретателю.

        Уведомление должника ставится тем же действием, а не отдельной
        галочкой «потом»: до уведомления исполнение прежнему кредитору
        остаётся надлежащим, и уступка для должника попросту не работает.
        """
        for record in self:
            accepted = record.response_ids.filtered(lambda r: r.state == 'accepted')
            if len(accepted) != 1:
                raise UserError(_(
                    'Отметьте ровно один принятый отклик: уступка '
                    'оформляется с одним приобретателем.'))
            record.write({
                'state': 'done',
                'assignee_id': accepted.partner_id.id,
                'ceded_on': fields.Date.context_today(record),
                'debtor_notified_on': fields.Date.context_today(record),
            })
            record.deal_id.message_post(body=_(
                'Требование по сделке уступлено: %(from)s → %(to)s. '
                'Должник уведомлён.',
                **{'from': record.creditor_id.name, 'to': accepted.partner_id.name},
            ))
        return True


class CoopCessionResponse(models.Model):
    """Отклик на предложение об уступке.

    Отдельной записью, а не полем «кто откликнулся»: откликов бывает
    несколько, и кредитору важно видеть все, чтобы выбрать. Выбор — его,
    платформа никого не назначает.
    """
    _name = 'coop.cession.response'
    _description = 'Отклик на предложение об уступке'
    _order = 'create_date desc, id desc'

    cession_id = fields.Many2one(
        'coop.cession', string='Предложение', required=True, index=True,
        ondelete='cascade')
    partner_id = fields.Many2one(
        'res.partner', string='Откликнулся', required=True, index=True)
    message = fields.Text(string='Что предлагает')
    state = fields.Selection([
        ('new', 'Новый'),
        ('accepted', 'Принят'),
        ('declined', 'Отклонён'),
    ], string='Состояние', default='new', required=True, index=True)

    _one_response_per_partner = models.Constraint(
        'unique(cession_id, partner_id)',
        'Откликнуться на одно предложение можно один раз.',
    )

    def action_accept(self):
        """Принять отклик. Остальные по этому предложению отклоняются.

        Не потому, что платформа так решила, а потому что уступается одно
        требование: у него может быть только один приобретатель.
        """
        for record in self:
            others = record.cession_id.response_ids - record
            others.write({'state': 'declined'})
            record.state = 'accepted'
        return True

    def action_decline(self):
        self.write({'state': 'declined'})
        return True
