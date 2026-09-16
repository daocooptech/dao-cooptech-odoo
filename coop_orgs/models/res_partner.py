# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo import _, api, fields, models


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
    coop_okved_code = fields.Char(
        string='Код ОКВЭД', size=8,
        help='Полный код, как он написан в выписке: 01.13.1. Хранится '
             'строкой — разбирать классификатор до шестого знака ради '
             'каталога незачем, а для сверки с реестром код нужен целиком.')

    coop_charter_url = fields.Char(
        string='Устав',
        help='Ссылка на действующую редакцию устава. Для кооператива это '
             'не формальность: правила приёма, голосования и распределения '
             'записаны там, а не на платформе.')

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
            прямые = record.coop_org_link_ids.filtered('confirmed')
            обратные = record.coop_org_backlink_ids.filtered('confirmed')
            record.coop_related_org_ids = (
                прямые.mapped('other_id') | обратные.mapped('org_id'))

    def _compute_coop_project_count(self):
        """Сколько проектов ведёт организация.

        Через sudo: число проектов — публичная величина, она стоит на
        карточке у всех, и права на сами проекты тут ни при чём.
        """
        Project = self.env['coop.project'].sudo()
        счёт = {}
        if self.ids:
            for организация, число in Project._read_group(
                    [('partner_id', 'in', self.ids)],
                    groupby=['partner_id'], aggregates=['__count']):
                счёт[организация.id] = число
        for record in self:
            record.coop_project_count = счёт.get(record.id, 0)
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
        я = user.partner_id
        Membership = self.env['coop.membership'].sudo()
        моё = {}
        заявлений = {}
        if self.ids:
            for запись in Membership.search([
                    ('organization_id', 'in', self.ids),
                    ('partner_id', '=', я.id),
                    ('state', 'in', ('applied', 'active', 'leaving'))]):
                моё[запись.organization_id.id] = запись.state
            for организация, число in Membership._read_group(
                    [('organization_id', 'in', self.ids),
                     ('state', '=', 'applied')],
                    groupby=['organization_id'], aggregates=['__count']):
                заявлений[организация.id] = число
        for record in self:
            состояние = моё.get(record.id, 'none')
            record.coop_my_membership_state = состояние
            ведёт = bool(record.is_company
                         and user.coop_has_power('roster', record))
            record.coop_can_manage_roster = ведёт
            record.coop_application_count = (
                заявлений.get(record.id, 0) if ведёт else 0)
            # Вступают в организацию, основанную на членстве, и не в свою
            # собственную карточку. У фонда и АНО членства нет вовсе —
            # предлагать туда вступить значило бы обещать несуществующее.
            record.coop_can_join = bool(
                record.is_company and record.coop_has_members
                and record != я and состояние == 'none')

    def action_coop_join(self):
        """Окно заявления о вступлении."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Вступить в «%s»') % self.name,
            'res_model': 'coop.org.join',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_organization_id': self.id},
        }

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
        членство = self._coop_my_membership()
        if not членство:
            raise UserError(_('Вы не состоите в «%s».') % self.name)
        членство.action_apply_to_leave()
        return True

    def action_coop_withdraw(self):
        """Отозвать своё заявление, пока его не рассмотрели."""
        self.ensure_one()
        членство = self._coop_my_membership()
        if not членство:
            raise UserError(_('Заявления нет.'))
        # Проверка «своё» и «ещё не рассмотрено» — в самой модели, чтобы
        # она была одна и для кнопки, и для вызова со стороны.
        членство.sudo().with_user(self.env.user).action_withdraw()
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
            'domain': [('organization_id', '=', self.id)],
            'context': {'default_organization_id': self.id},
        }

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

    coop_org_is_following = fields.Boolean(
        string='Я подписан на организацию', compute='_compute_org_following')

    def _compute_org_following(self):
        me = self.env.user.partner_id
        for record in self:
            record.coop_org_is_following = me in record.message_partner_ids
