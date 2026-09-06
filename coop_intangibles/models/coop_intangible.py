# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CoopIntangible(models.Model):
    """Нематериальный актив кооператива.

    Рецептура сыра, программа учёта смен, товарный знак, сорт пшеницы —
    то, что у кооператива есть, но нельзя потрогать. Реестр отвечает на
    три вопроса разом: что принадлежит, чем это подтверждено и во сколько
    оценено.

    **Оценка и обеспечение — разные вещи, и путать их дорого.** Оценка
    показывает стоимость актива в балансе и сама по себе не обеспечивает
    ничего. Обеспечение — это залог, зарегистрированный там, где велит
    закон: для движимого имущества уведомление у нотариуса, для
    недвижимости запись в ЕГРН. Поэтому в карточке отдельно оценка и
    отдельно залог, и второе не подменяется первым.

    Учёт ведётся по ФСБУ 14/2022: первоначальная стоимость, срок полезного
    использования, накопленная амортизация. Бухгалтеру это нужно для
    отчётности, участнику — чтобы видеть остаточную стоимость, а не
    цифру, которой пять лет.
    """
    _name = 'coop.intangible'
    _description = 'Нематериальный актив'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(string='Актив', required=True, tracking=True)
    kind = fields.Selection([
        ('know_how', 'Ноу-хау и коммерческая тайна'),
        ('trademark', 'Товарный знак'),
        ('software', 'Программа или база данных'),
        ('patent', 'Патент или селекционное достижение'),
    ], string='Вид', required=True, default='know_how', index=True, tracking=True)

    owner_id = fields.Many2one(
        'res.partner', string='Правообладатель', required=True, index=True,
        tracking=True,
        help='Кому принадлежит исключительное право. Кооператив, '
             'организация или участник.')
    description = fields.Html(string='Описание')
    image_1920 = fields.Image(string='Изображение', max_width=1920, max_height=1920)
    image_512 = fields.Image(related='image_1920', max_width=512, max_height=512, store=True)

    # ── Правовая охрана ──────────────────────────────────────────────────
    #
    # Основание — не украшение карточки. У ноу-хау охрана держится на
    # режиме коммерческой тайны: нет приказа о введении режима — нет и
    # секрета производства (ст. 1465, 1467 ГК), сколько ни называй его
    # своим. У знака и патента охрана начинается с регистрации.
    legal_basis = fields.Char(
        string='Правовое основание', required=True,
        help='«Режим коммерческой тайны, приказ от 12.03.2025» или '
             '«Свидетельство № 812344, класс 29».')
    registration_number = fields.Char(string='Номер регистрации')
    registered_on = fields.Date(string='Дата регистрации')
    protection_until = fields.Date(
        string='Охрана до',
        help='У знака десять лет с продлением, у патента — свой срок. '
             'У ноу-хау срока нет, пока сохраняется тайна.')

    state = fields.Selection([
        ('draft', 'Черновик'),
        ('active', 'Право действует'),
        ('expired', 'Охрана прекращена'),
        ('disputed', 'Спор о праве'),
    ], string='Состояние', default='draft', required=True, index=True, tracking=True)

    # ── Учёт по ФСБУ 14/2022 ─────────────────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        default=lambda self: self.env.company.currency_id)
    initial_cost = fields.Monetary(
        string='Первоначальная стоимость', currency_field='currency_id',
        tracking=True,
        help='Фактические затраты на создание или приобретение.')
    useful_life_months = fields.Integer(
        string='Срок полезного использования, мес.',
        help='Ноль — актив с неопределённым сроком: он не амортизируется, '
             'но проверяется на обесценение.')
    accumulated_depreciation = fields.Monetary(
        string='Накопленная амортизация', currency_field='currency_id')
    residual_value = fields.Monetary(
        string='Остаточная стоимость', compute='_compute_residual', store=True,
        currency_field='currency_id')

    # ── Залог ────────────────────────────────────────────────────────────
    pledge_state = fields.Selection([
        ('none', 'Не оформлен'),
        ('notary', 'Уведомление у нотариуса'),
        ('rospatent', 'Зарегистрирован в Роспатенте'),
    ], string='Залог', default='none', required=True, index=True,
        help='Обеспечением актив становится только после регистрации '
             'залога там, где велит закон. Оценка сама по себе ничего не '
             'обеспечивает.')
    pledge_reference = fields.Char(string='Реквизиты залога')
    pledge_holder_id = fields.Many2one('res.partner', string='Залогодержатель')

    license_ids = fields.One2many(
        'coop.intangible.license', 'intangible_id', string='Лицензии')
    license_count = fields.Integer(compute='_compute_license_count', string='Лицензий')
    active_license_count = fields.Integer(
        compute='_compute_license_count', string='Действующих лицензий')

    contribution_ids = fields.One2many(
        'coop.project.contribution', 'intangible_id', string='Внесён в проекты')

    import_key = fields.Char(string='Ключ источника', index=True, copy=False)

    @api.depends('initial_cost', 'accumulated_depreciation')
    def _compute_residual(self):
        for record in self:
            record.residual_value = record.initial_cost - record.accumulated_depreciation

    @api.depends('license_ids.state')
    def _compute_license_count(self):
        for record in self:
            record.license_count = len(record.license_ids)
            record.active_license_count = len(record.license_ids.filtered(
                lambda l: l.state == 'active'))

    @api.constrains('accumulated_depreciation', 'initial_cost')
    def _check_depreciation(self):
        for record in self:
            if record.accumulated_depreciation > record.initial_cost:
                raise ValidationError(_(
                    'Накопленная амортизация больше первоначальной '
                    'стоимости. Актив не может износиться сильнее, чем '
                    'стоил.'))

    def action_activate(self):
        for record in self:
            if not record.legal_basis:
                raise UserError(_(
                    'Без правового основания актива нет. У ноу-хау охрана '
                    'держится на режиме коммерческой тайны, у знака и '
                    'патента — на регистрации.'))
            record.state = 'active'
        return True


class CoopIntangibleLicense(models.Model):
    """Лицензия на использование актива.

    Четыре условия задают, что именно куплено: срок, территория, тираж и
    исключительность. Без них «лицензия» — слово, по которому нельзя ни
    посчитать цену, ни разрешить спор.

    Исключительная лицензия запрещает правообладателю выдавать такие же
    другим и пользоваться самому в тех же пределах (ст. 1236 ГК). Разница
    с простой — не в цене, а в том, что продавец теряет: поэтому вид
    лицензии стоит рядом с ценой, а не в примечании.
    """
    _name = 'coop.intangible.license'
    _description = 'Лицензия на нематериальный актив'
    _inherit = ['mail.thread']
    _order = 'starts_on desc, id desc'
    _rec_name = 'display_name'

    display_name = fields.Char(compute='_compute_display_name', store=True)

    intangible_id = fields.Many2one(
        'coop.intangible', string='Актив', required=True, index=True,
        ondelete='cascade')
    licensor_id = fields.Many2one(
        'res.partner', related='intangible_id.owner_id', store=True,
        string='Правообладатель')
    licensee_id = fields.Many2one(
        'res.partner', string='Кому выдана', index=True,
        help='Пусто — лицензия выставлена на витрину и ждёт покупателя.')

    is_exclusive = fields.Boolean(
        string='Исключительная',
        help='Правообладатель не вправе выдавать такие же лицензии другим '
             'и сам пользоваться активом в этих пределах (ст. 1236 ГК).')
    territory = fields.Char(
        string='Территория', default='Российская Федерация',
        help='«Приморский край», «Российская Федерация», «без ограничений». '
             'Для кооперативов важно: рецепт продают соседнему району, а '
             'не конкуренту через дорогу.')
    starts_on = fields.Date(string='Начало', default=fields.Date.context_today)
    ends_on = fields.Date(
        string='Окончание',
        help='Пусто — бессрочно, в пределах срока охраны самого актива.')
    volume_limit = fields.Float(
        string='Тираж или объём', digits=(16, 3),
        help='Сколько разрешено выпустить по технологии. Ноль — без '
             'ограничения объёма.')
    volume_unit = fields.Char(string='Единица объёма', default='т')
    volume_used = fields.Float(string='Использовано', digits=(16, 3), readonly=True)

    currency_id = fields.Many2one(
        'res.currency', related='intangible_id.currency_id', store=True)
    price = fields.Monetary(string='Цена', currency_field='currency_id')
    royalty_percent = fields.Float(
        string='Роялти, %', digits=(5, 2),
        help='Периодические отчисления с выручки лицензиата — вместо '
             'единовременной цены или вместе с ней.')

    state = fields.Selection([
        ('draft', 'Черновик'),
        ('offered', 'Предложена'),
        ('active', 'Действует'),
        ('expired', 'Истекла'),
        ('revoked', 'Отозвана'),
    ], string='Состояние', default='draft', required=True, index=True, tracking=True)

    # Токенизация лицензии: право пользоваться делится и продаётся так же,
    # как право на будущий товар. Долями в самом исключительном праве это
    # не является — см. предупреждение в `is_share_of_right`.
    jetton_master_address = fields.Char(
        string='Адрес токена', readonly=True, copy=False,
        help='Если лицензия выпущена токенами, здесь адрес jetton-мастера.')
    is_share_of_right = fields.Boolean(
        string='Доля в самом праве',
        help='Не лицензия, а совместное обладание исключительным правом. '
             'Внимание: распоряжение исключительным правом на '
             'зарегистрированный объект подлежит государственной '
             'регистрации (ст. 1232 ГК) — токен фиксирует договорённость '
             'сторон, но не заменяет запись в Роспатенте.')

    import_key = fields.Char(string='Ключ источника', index=True, copy=False)

    @api.depends('intangible_id.name', 'licensee_id.name', 'is_exclusive')
    def _compute_display_name(self):
        for record in self:
            kind = _('исключительная') if record.is_exclusive else _('простая')
            record.display_name = '%s — %s лицензия%s' % (
                record.intangible_id.name or '',
                kind,
                ' (%s)' % record.licensee_id.name if record.licensee_id else '',
            )

    @api.constrains('is_exclusive', 'intangible_id', 'state', 'territory')
    def _check_exclusive_conflict(self):
        """Двух исключительных лицензий на одно и то же не бывает.

        Проверка по территории: исключительная лицензия на Приморский край
        и такая же на Вологодскую область друг другу не мешают, а две на
        одну территорию — прямое нарушение первой.
        """
        for record in self:
            if not record.is_exclusive or record.state not in ('offered', 'active'):
                continue
            clash = self.search([
                ('id', '!=', record.id),
                ('intangible_id', '=', record.intangible_id.id),
                ('is_exclusive', '=', True),
                ('state', 'in', ('offered', 'active')),
                ('territory', '=', record.territory),
            ], limit=1)
            if clash:
                raise ValidationError(_(
                    'На эту территорию уже выдана исключительная лицензия '
                    '(%s). Вторая такая же нарушает первую.'
                ) % clash.display_name)

    def action_activate(self):
        for record in self:
            if not record.licensee_id:
                raise UserError(_(
                    'Лицензия без лицензиата не действует: должно быть '
                    'видно, кому разрешено.'))
            record.state = 'active'
        return True

    def action_revoke(self):
        self.write({'state': 'revoked'})
        return True


class CoopProjectContribution(models.Model):
    """Вклад нематериальным активом.

    Рецептура или программа вносятся в проект наравне с деньгами и трудом
    — по денежной оценке, как и всё остальное. Ссылка на сам актив нужна
    затем, чтобы вклад «программа учёта смен» можно было проверить: вот
    актив, вот основание, вот кому принадлежит.
    """
    _inherit = 'coop.project.contribution'

    intangible_id = fields.Many2one(
        'coop.intangible', string='Нематериальный актив', index=True,
        help='Заполняется, когда вклад — право, а не вещь и не деньги.')
