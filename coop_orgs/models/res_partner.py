# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from odoo import _, api, fields, models

# Артели: производственный кооператив и сельхозпроизводственный.
ARTEL_KINDS = ('production', 'agri_production')

# Публичные документы организации (решение 704): поле карточки → вид
# документа в разделе «Документы».
PUBLIC_DOCS = {
    'charter': ('coop_charter_doc_id', 'charter'),
    'fees': ('coop_fees_rules_doc_id', 'regulation'),
    'profit': ('coop_profit_rules_doc_id', 'regulation'),
    'report': ('coop_report_doc_id', 'report'),
}


class ResPartner(models.Model):
    """Организация как участник платформы.

    Та же модель, что и человек, с признаком компании. Это не экономия на
    моделях: организация выступает стороной сделки наравне с человеком, и
    если развести их на две модели, каждую сделку придётся описывать
    дважды — отдельно для людей, отдельно для организаций.
    """
    _inherit = 'res.partner'

    # ── Реквизиты ────────────────────────────────────────────────────────
    #
    # ИНН и ОГРН хранятся отдельно от штатного vat. В vat Odoo кладёт
    # налоговый номер в международном формате («RU7707083893»), и он же
    # используется в проверках контрагентов. Российской организации в
    # каталоге нужен именно ИНН как он написан в выписке, без префикса.
    coop_inn = fields.Char(
        string='ИНН', size=12, index=True,
        help='10 цифр у организации, 12 у индивидуального предпринимателя.')
    coop_kpp = fields.Char(string='КПП', size=9)
    coop_ogrn = fields.Char(
        string='ОГРН', size=15,
        help='13 цифр у организации, 15 у индивидуального предпринимателя.')
    coop_registered_on = fields.Date(string='Дата регистрации')

    # ── Вид деятельности ─────────────────────────────────────────────────
    #
    # По ОКВЭД, а не по «сфере деятельности» из справочника вакансий:
    # кооператив занимается сельским хозяйством, а не «рабочим
    # персоналом». Решение владельца 15 сентября 2026.
    #
    # Класс — то, что выбирают; раздел считается от него и хранится,
    # потому что по нему раскладываются полки каталога, а группировать
    # по несохранённому полю нельзя.
    coop_okved_id = fields.Many2one(
        'coop.okved', string='Основной вид деятельности',
        domain=[('parent_id', '!=', False)], index=True, ondelete='restrict',
        help='Класс ОКВЭД: две цифры. Берётся из выписки — тот код, '
             'который у организации указан основным.')
    coop_okved_section_id = fields.Many2one(
        'coop.okved', string='Раздел ОКВЭД',
        related='coop_okved_id.parent_id', store=True, index=True)
    # Строка под названием на плитке каталога — как специализации под
    # именем у людей (решение 411, Н1; владелец 26.09: «организации можно
    # по ОКВЭД»). Название класса без кода: код читает бухгалтер, а не
    # человек, выбирающий, с кем работать.
    coop_okved_name = fields.Char(related='coop_okved_id.name', string='Вид деятельности')
    coop_okved_code = fields.Char(
        string='Код ОКВЭД', size=8,
        help='Полный код, как он написан в выписке: 01.13.1. Хранится '
             'строкой — разбирать классификатор до шестого знака ради '
             'каталога незачем, а для сверки с реестром код нужен целиком.')

    # Решение 657 п. 3: долю итога года в неделимый фонд задаёт кооператив
    # в уставе, платформа только применяет её при распределении.
    coop_indivisible_fund_percent = fields.Float(
        string='В неделимый фонд, %', digits=(5, 2), default=0.0,
        help='Доля итога года, которая по уставу уходит в неделимый фонд '
             'и не делится между членами. Задаёт кооператив, платформа '
             'применяет при распределении. По умолчанию 0 %.')

    @api.constrains('coop_indivisible_fund_percent')
    def _check_coop_indivisible_fund_percent(self):
        for record in self:
            if not 0 <= record.coop_indivisible_fund_percent <= 100:
                raise ValidationError(_(
                    'Доля в неделимый фонд — от 0 до 100 %.'))

    # Решение 511 (26.10.2026, «оба пути»): основа кооперативных выплат —
    # пункт устава. Потребительский кооператив делит по обороту, считая и
    # работы по ГПХ (ст. 1 3085-1, устав); артель — по личному трудовому
    # участию (ст. 12 41-ФЗ), по паям — не более 50 %. Значение следует за
    # видом кооператива, ручной выбор держится, пока допустим.
    coop_payout_basis = fields.Selection([
        ('turnover', 'По обороту и работам'),
        ('labor', 'По трудовому участию'),
    ], string='Основа кооперативных выплат',
        compute='_compute_coop_payout_basis', store=True, readonly=False,
        help='Как устав делит итог года между членами. Потребительский '
             'кооператив — по участию в обороте, включая работы по '
             'договорам подряда; артель — по личному трудовому участию.')

    @api.depends('coop_cooperative_kind')
    def _compute_coop_payout_basis(self):
        for partner in self:
            allowed = partner._coop_payout_bases_allowed()
            if partner.coop_payout_basis not in allowed:
                partner.coop_payout_basis = allowed[0] if allowed else False

    def _coop_payout_bases_allowed(self):
        self.ensure_one()
        kind = self.coop_cooperative_kind
        if not kind:
            return ()
        return ('labor',) if kind in ARTEL_KINDS else ('turnover',)

    @api.constrains('coop_payout_basis', 'coop_cooperative_kind')
    def _check_coop_payout_basis(self):
        for partner in self:
            basis = partner.coop_payout_basis
            if basis and basis not in partner._coop_payout_bases_allowed():
                raise ValidationError(_(
                    'По личному трудовому участию делит только артель '
                    '(ст. 12 41-ФЗ); потребительский кооператив — по '
                    'обороту, с работами по ГПХ (решение 511).')
                    if basis == 'labor' else _(
                    'Артель делит итог года по личному трудовому участию '
                    '(ст. 12 41-ФЗ), не по обороту (решение 511).'))

    # Решение 704: устав, положения и отчётность — файлами в «Документах»
    # организации, карточка ссылается на документ платформы, а не на
    # чужой сайт: у файла есть отпечаток и редакции, и он не пропадёт
    # вместе с сайтом.
    coop_charter_doc_id = fields.Many2one(
        'coop.document', string='Устав', ondelete='set null',
        domain="[('party_a_id', '=', id), ('is_public', '=', True)]",
        help='Действующая редакция устава. Для кооператива это не '
             'формальность: правила приёма, голосования и распределения '
             'записаны там, а не на платформе.')

    # ── Условия вступления (задача 445, решения 677 и 679) ────────────────
    #
    # Владелец 13.11.2026: при заявке «можно дать описание процессу, какие
    # плюсы и подводные камни от вступления, документы кооператива (устав,
    # положение о программе и тд)». Документы — ссылками, как и устав:
    # кооператив держит действующие редакции у себя.
    coop_fees_rules_doc_id = fields.Many2one(
        'coop.document', string='Положение о взносах', ondelete='set null',
        domain="[('party_a_id', '=', id), ('is_public', '=', True)]",
        help='Размер и порядок вступительного и паевого взносов, возврат '
             'пая при выходе.')
    coop_profit_rules_doc_id = fields.Many2one(
        'coop.document', string='Положение о распределении прибыли',
        ondelete='set null',
        domain="[('party_a_id', '=', id), ('is_public', '=', True)]")
    coop_report_doc_id = fields.Many2one(
        'coop.document', string='Последняя отчётность', ondelete='set null',
        domain="[('party_a_id', '=', id), ('is_public', '=', True)]")

    def _coop_put_public_doc(self, slot, name, data, file_name, signed_on=None, number=False):
        """Положить публичный документ в «Документы» организации и
        сослаться на него из карточки (решение 704). `data` — base64."""
        self.ensure_one()
        field, kind = PUBLIC_DOCS[slot]
        if isinstance(data, bytes):
            data = data.decode()
        doc = self.env['coop.document'].sudo().create({
            'name': name,
            'kind': kind,
            'is_public': True,
            'party_a_id': self.id,
            'res_model': 'res.partner',
            'res_id': self.id,
            'res_label': self.name,
            'signed_on': signed_on or fields.Date.context_today(self),
            'number': number,
            'file': data,
            'file_name': file_name,
            'state': 'signed',
        })
        self.sudo()[field] = doc
        return doc
    coop_entrance_fee = fields.Float(
        string='Вступительный взнос, ₽', digits=(16, 2),
        help='Не возвращается при выходе. Ноль — размер задан уставом.')
    coop_min_share_fee = fields.Float(
        string='Обязательный паевой взнос, ₽', digits=(16, 2),
        help='Возвращается при выходе на условиях устава. Ноль — размер '
             'задан уставом.')
    coop_join_open = fields.Boolean(
        string='Принимает заявления', default=True,
        help='Снято — путь «Стать пайщиком» виден, но заявление не подать; '
             'нечлен видит причину (решение 677).')
    coop_join_closed_note = fields.Char(
        string='Почему не принимает',
        help='Что увидит тот, кто хочет вступить: «набор закрыт до '
             'собрания в марте».')

    # Знак бывает двух видов: символ рода занятий во весь кадр или буква
    # названия с символом над ней. Оба заливают плитку целиком — поле
    # различает только рисунок, а не способ показа.
    coop_symbol_mark = fields.Boolean(
        string='Знак-символ', default=False,
        help='Установлено, если знак организации — символ рода занятий. '
             'Снято, если это буква названия.')

    # ── Состав ───────────────────────────────────────────────────────────
    coop_member_ids = fields.One2many(
        'coop.membership', 'organization_id', string='Состав')

    # Владения организации — те же полосы, что у человека на странице.
    # Через те же поля, что и у него: организация на платформе — такой
    # же участник, и заводить ей отдельные связи значило бы держать два
    # набора правил там, где хватает одного.
    # Своё, а не проектов. Потребности проектов — тоже спрос и тоже
    # лежат в каталоге ресурсов, но на карточке организации им не место:
    # то же правило, что и на странице человека. Владелец 15 сентября
    # 2026: «у пользователя только личные потребности, у проектов свои
    # потребности, которые грузятся в каталог ресурсов в спрос».
    coop_org_resource_ids = fields.One2many(
        'coop.resource', 'owner_id', string='Ресурсы организации',
        domain=[('listing_type', '=', 'offer'), ('project_id', '=', False)])
    coop_org_need_ids = fields.One2many(
        'coop.resource', 'owner_id', string='Потребности организации',
        domain=[('listing_type', '=', 'request'), ('project_id', '=', False)])
    coop_org_project_ids = fields.One2many(
        'coop.project', 'partner_id', string='Проекты организации')
    coop_org_vacancy_ids = fields.One2many(
        'coop.vacancy', 'partner_id', string='Вакансии организации')
    coop_member_count = fields.Integer(
        string='Участников', compute='_compute_coop_member_count', store=True)

    # ── Вид организации на карточке ──────────────────────────────────
    #
    # В макете под названием стоит «Кооперативная организация», а полка
    # состава подписана «Пайщики» — у коммерческой «Сотрудники», у
    # некоммерческой «Участники». Слово не украшение: пайщик вносит пай
    # и голосует, наёмный сотрудник — ни того ни другого.
    coop_card_label = fields.Char(
        string='Вид организации',
        related='coop_legal_form_group_id.card_label', readonly=True)
    coop_member_label = fields.Char(
        string='Как зовётся состав', compute='_compute_coop_member_label')

    @api.depends('coop_legal_form_group_id.member_label')
    def _compute_coop_member_label(self):
        """Запасное слово — «Участники»: у организации без указанной
        формы состав всё равно надо как-то назвать, и нейтральное слово
        здесь честнее, чем «Пайщики» наугад.
        """
        for record in self:
            record.coop_member_label = (
                record.coop_legal_form_group_id.member_label or 'Участники')

    # ── Услуги ───────────────────────────────────────────────────────
    #
    # Полка появляется, когда организация завела хоть одну услугу, —
    # владелец 15 сентября 2026: «услуги (появляется при добавлении
    # услуги)». Услуга на платформе — это предложение навыка: тот же
    # каталог, та же карточка, и заводить рядом вторую сущность незачем.
    coop_org_service_ids = fields.One2many(
        'coop.skill.offer', 'partner_id', string='Услуги организации',
        domain=[('state', '=', 'published')])

    # ── Связанные организации ────────────────────────────────────────
    coop_org_link_ids = fields.One2many(
        'coop.org.link', 'org_id', string='Связи организации')
    coop_org_backlink_ids = fields.One2many(
        'coop.org.link', 'other_id', string='Связи с этой организацией')
    coop_related_org_ids = fields.Many2many(
        'res.partner', string='Связанные организации',
        compute='_compute_coop_related_orgs')
    # Своим вычислением, а не вместе со связями.
    #
    # Оба поля считались одним методом: связи и счётчик проектов «одним
    # проходом». При чтении связей движок вычисляет только их, а
    # присваивание счётчика оказывается вне вычисления — и уходит
    # **записью** в карточку. Участнику писать в чужую организацию
    # нельзя, и карточка отвечала «нет доступа „запись“ к Контактам»:
    # человек не мог открыть ни одну организацию.
    coop_project_count = fields.Integer(
        string='Проектов', compute='_compute_coop_project_count')

    @api.depends('coop_org_link_ids.confirmed', 'coop_org_backlink_ids.confirmed')
    def _compute_coop_related_orgs(self):
        """Связи с обеих сторон и счётчик проектов — одним проходом.

        Связь двусторонняя: если «Заря» входит в союз, то у союза «Заря»
        — член. Запись при этом одна, и на карточке её надо видеть с
        любой стороны.

        Неподтверждённые не показываем: связь, объявленная одной
        стороной, — это её заявление, а не факт. Иначе кто угодно
        объявил бы себя учредителем чужого кооператива.
        """
        for record in self:
            direct = record.coop_org_link_ids.filtered('confirmed')
            reverse = record.coop_org_backlink_ids.filtered('confirmed')
            record.coop_related_org_ids = (
                direct.mapped('other_id') | reverse.mapped('org_id'))

    def _compute_coop_project_count(self):
        """Сколько проектов ведёт организация.

        Через sudo: число проектов — публичная величина, она стоит на
        карточке у всех, и права на сами проекты тут ни при чём.
        """
        Project = self.env['coop.project'].sudo()
        account = {}
        if self.ids:
            for organization, number_value in Project._read_group(
                    [('partner_id', 'in', self.ids)],
                    groupby=['partner_id'], aggregates=['__count']):
                account[organization.id] = number_value
        for record in self:
            record.coop_project_count = account.get(record.id, 0)
    coop_has_members = fields.Boolean(
        string='Форма предполагает членство',
        related='coop_legal_form_id.has_members', store=True,
        help='У фонда и АНО членства нет вовсе, у кооператива и ТСЖ есть. '
             'От этого зависит, показывать ли раздел состава.')

    @api.depends('coop_member_ids.state')
    def _compute_coop_member_count(self):
        # Через sudo намеренно. Число участников — публичная величина, она
        # есть в уставе и в выписке; закрыт поимённый состав. Без sudo
        # пересчёт у пользователя без прав на членство ронял бы чтение
        # самой карточки организации, а не только состава.
        # `_read_group` в Odoo 19 отдаёт кортежи с записями, а не словари с
        # парами «идентификатор, название»: организация приходит готовым
        # `res.partner`, и брать у неё нулевой элемент нечего.
        counts = {
            organization.id: count
            for organization, count in self.env['coop.membership'].sudo()._read_group(
                [('organization_id', 'in', self.ids), ('state', '=', 'active')],
                groupby=['organization_id'], aggregates=['__count'])
        } if self.ids else {}
        for record in self:
            record.coop_member_count = counts.get(record.id, 0)

    # ── Вступление и выход ───────────────────────────────────────────
    #
    # Модель членства описана до мелочей, а подать заявление участник не
    # мог: на карточке организации были только «Написать» и
    # «Подписаться». Состав заводился загрузчиком демо-данных и вручную
    # из администраторского списка — то есть пути к нему на платформе не
    # было вовсе.

    coop_my_membership_state = fields.Selection([
        ('none', 'Не состою'),
        ('applied', 'Заявление подано'),
        ('active', 'Состою'),
        ('leaving', 'Подано заявление о выходе'),
    ], string='Моё членство', compute='_compute_coop_my_membership')
    coop_can_join = fields.Boolean(
        string='Можно вступить', compute='_compute_coop_my_membership')
    coop_application_count = fields.Integer(
        string='Заявлений', compute='_compute_coop_my_membership')
    coop_can_manage_roster = fields.Boolean(
        string='Веду состав', compute='_compute_coop_my_membership')

    @api.depends_context('uid')
    @api.depends('coop_member_ids.state', 'coop_has_members', 'is_company')
    def _compute_coop_my_membership(self):
        """Четыре ответа одним проходом: все нужны одной шапке разом."""
        user = self.env.user
        me = user.partner_id
        Membership = self.env['coop.membership'].sudo()
        my_one = {}
        applications_count = {}
        if self.ids:
            for rec in Membership.search([
                    ('organization_id', 'in', self.ids),
                    ('partner_id', '=', me.id),
                    ('state', 'in', ('applied', 'active', 'leaving'))]):
                my_one[rec.organization_id.id] = rec.state
            for organization, number_value in Membership._read_group(
                    [('organization_id', 'in', self.ids),
                     ('state', '=', 'applied')],
                    groupby=['organization_id'], aggregates=['__count']):
                applications_count[organization.id] = number_value
        for record in self:
            state = my_one.get(record.id, 'none')
            record.coop_my_membership_state = state
            leads_to = bool(record.is_company
                         and user.coop_has_power('roster', record))
            record.coop_can_manage_roster = leads_to
            record.coop_application_count = (
                applications_count.get(record.id, 0) if leads_to else 0)
            # Вступают в организацию, основанную на членстве, и не в свою
            # собственную карточку. У фонда и АНО членства нет вовсе —
            # предлагать туда вступить значило бы обещать несуществующее.
            # По заявлению вступают пайщиком (кооператив) или участником
            # (НКО, ДАО); в КФХ и товарищество — по договору, не
            # заявлением (задача 445: наёмного в окне больше нет).
            record.coop_can_join = bool(
                record.is_company and record.coop_has_members
                and record.coop_legal_form_group_id.code in (
                    'cooperative', 'nonprofit', 'decentralized')
                and record != me and state == 'none')

    def action_coop_join(self):
        """Окно заявления о вступлении."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Вступить в %s') % self.name,
            'res_model': 'coop.org.join',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_organization_id': self.id},
        }

    def _coop_join_block(self):
        """Почему заявление о вступлении не подать: (код, пояснение).

        Пусто — подать можно. Решения 677 (путь виден всегда, с причиной)
        и 679 п. 4 (без устава заявления нет).
        """
        self.ensure_one()
        mine = self._coop_my_membership()
        if mine and mine.state == 'applied':
            return 'applied', _(
                'Заявление подано %s и ждёт решения правления.') % (
                    mine.create_date.strftime('%d.%m.%Y')
                    if mine.create_date else '')
        if mine:
            return 'member', _('Вы уже член «%s».') % self.name
        if not self.coop_join_open:
            return 'closed', _('Сейчас не принимает заявления: %s.') % (
                self.coop_join_closed_note or _('причина не указана'))
        if not self.coop_charter_doc_id:
            return 'no_charter', _(
                'Устав не выложен на платформе, без него заявление не '
                'подаём. Подпишитесь — узнаете, когда появится.')
        return False, False

    def _coop_my_membership(self):
        """Моё открытое членство в этой организации, если оно есть."""
        self.ensure_one()
        return self.env['coop.membership'].sudo().search([
            ('organization_id', '=', self.id),
            ('partner_id', '=', self.env.user.partner_id.id),
            ('state', 'in', ('applied', 'active', 'leaving')),
        ], limit=1)

    def action_coop_leave(self):
        """Подать заявление о выходе."""
        self.ensure_one()
        membership = self._coop_my_membership()
        if not membership:
            raise UserError(_('Вы не состоите в «%s».') % self.name)
        membership.action_apply_to_leave()
        return True

    def action_coop_withdraw(self):
        """Отозвать своё заявление, пока его не рассмотрели."""
        self.ensure_one()
        membership = self._coop_my_membership()
        if not membership:
            raise UserError(_('Заявления нет.'))
        # Проверка «своё» и «ещё не рассмотрено» — в самой модели, чтобы
        # она была одна и для кнопки, и для вызова со стороны.
        membership.sudo().with_user(self.env.user).action_withdraw()
        return True

    def action_coop_applications(self):
        """Заявления, ждущие решения."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Заявления о вступлении: %s') % self.name,
            'res_model': 'coop.membership',
            'view_mode': 'list,form',
            'domain': [('organization_id', '=', self.id),
                       ('state', '=', 'applied')],
            'context': {'default_organization_id': self.id},
        }

    def action_coop_members(self):
        """Открыть состав организации."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Состав: %s') % self.name,
            'res_model': 'coop.membership',
            'view_mode': 'list,form',
            # Только действующие: полка показывает их же, а список,
            # где к пяти пайщикам добавляются тридцать вышедших, — это
            # уже не «смотреть все», а другой ответ на тот же вопрос.
            'domain': [('organization_id', '=', self.id),
                       ('state', '=', 'active')],
            'context': {'default_organization_id': self.id},
        }

    # ── «Смотреть все» у полок карточки организации ──────────────────
    #
    # На странице человека такая ссылка есть у каждой полки, а здесь была
    # только у состава: остальные шесть полок обрывались на пяти плитках
    # без выхода в полный список. Владелец 21 сентября 2026: «проверь что
    # бы все эти ссылки работали корректно и открывались страницы с
    # нужными данными».
    #
    # Отбор тот же, что у самой полки: список и полка должны показывать
    # одно и то же, иначе «смотреть все» открывает не то, что обещало.
    def action_coop_org_resources(self):
        self.ensure_one()
        return self._coop_holdings_action(
            'coop_resources.action_coop_resources',
            [('owner_id', '=', self.id), ('listing_type', '=', 'offer'),
             ('project_id', '=', False)],
            _('Ресурсы — %s') % self.display_name)

    def action_coop_org_needs(self):
        self.ensure_one()
        return self._coop_holdings_action(
            'coop_resources.action_coop_resources',
            [('owner_id', '=', self.id), ('listing_type', '=', 'request'),
             ('project_id', '=', False)],
            _('Потребности — %s') % self.display_name)

    def action_coop_org_projects(self):
        self.ensure_one()
        return self._coop_holdings_action(
            'coop_projects.action_coop_projects',
            [('partner_id', '=', self.id)],
            _('Проекты — %s') % self.display_name)

    def action_coop_org_vacancies(self):
        self.ensure_one()
        return self._coop_holdings_action(
            'coop_vacancies.action_coop_vacancies',
            [('partner_id', '=', self.id)],
            _('Вакансии — %s') % self.display_name)

    def action_coop_org_services(self):
        self.ensure_one()
        return self._coop_holdings_action(
            'coop_skills.action_coop_services',
            [('partner_id', '=', self.id), ('state', '=', 'published')],
            _('Услуги — %s') % self.display_name)

    def action_coop_org_related(self):
        self.ensure_one()
        return self._coop_holdings_action(
            'coop_orgs.action_coop_orgs',
            [('id', 'in', self.coop_related_org_ids.ids)],
            _('Связанные организации — %s') % self.display_name)

    def action_coop_org_message(self):
        """Написать организации."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Написать: %s') % self.name,
            'res_model': 'discuss.channel',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_channel_partner_ids': [(4, self.id)]},
        }

    def action_coop_org_follow(self):
        """Подписаться на организацию или отписаться.

        Дружбы у организаций нет — она бывает только между людьми. Здесь
        подписка означает «следить за лентой»: за новыми ресурсами,
        вакансиями и объявлениями.
        """
        self.ensure_one()
        me = self.env.user.partner_id
        if me in self.message_partner_ids:
            self.message_unsubscribe(partner_ids=me.ids)
        else:
            self.message_subscribe(partner_ids=me.ids)
        return True

    @api.model
    def action_coop_new_org(self):
        """«Добавить организацию» каталога — страница добавления."""
        return self.env['coop.org.add'].action_new_org()

    coop_org_is_following = fields.Boolean(
        string='Я подписан на организацию', compute='_compute_org_following')

    def _compute_org_following(self):
        me = self.env.user.partner_id
        for record in self:
            record.coop_org_is_following = me in record.message_partner_ids

    # Телефон и почта организации открыты по умолчанию (решение 410,
    # п. 12): организация — не частное лицо, её телефон и так публичен.
    # Переключатели общие с человеком, а у человека умолчание — «скрыто»
    # (`coop_base`), поэтому новой организации «показывать» ставится здесь.
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_company'):
                vals.setdefault('coop_show_phone', True)
                vals.setdefault('coop_show_email', True)
        return super().create(vals_list)
