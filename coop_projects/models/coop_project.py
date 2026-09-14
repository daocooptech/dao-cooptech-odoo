# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CoopProjectCategory(models.Model):
    """Тема проекта и её раздел.

    Это не специализация. Специализация отвечает, что человек умеет
    делать; тема проекта — чему проект посвящён. «Веб-дизайн» бывает
    специализацией, но не бывает темой проекта, а «Переработка отходов» —
    наоборот.

    Двухуровнево, как в макете: двенадцать тем и восемнадцать разделов
    внутри них.
    """
    _name = 'coop.project.category'
    _description = 'Тема проекта'
    _parent_store = True
    _order = 'complete_name'

    name = fields.Char(string='Название', required=True, translate=True)
    parent_id = fields.Many2one(
        'coop.project.category', string='Входит в', ondelete='cascade', index=True)
    parent_path = fields.Char(index=True, unaccent=False)
    child_ids = fields.One2many('coop.project.category', 'parent_id', string='Разделы')
    complete_name = fields.Char(
        string='Полное название', compute='_compute_complete_name',
        store=True, recursive=True)
    project_count = fields.Integer(
        string='Проектов', compute='_compute_project_count')

    _name_parent_uniq = models.Constraint(
        'unique(name, parent_id)',
        'Такая тема на этом уровне уже есть.',
    )

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for record in self:
            if record.parent_id:
                record.complete_name = '%s / %s' % (
                    record.parent_id.complete_name, record.name)
            else:
                record.complete_name = record.name

    def _compute_project_count(self):
        counts = {
            category.id: count
            for category, count in self.env['coop.project'].sudo()._read_group(
                [('category_id', 'in', self.ids)],
                groupby=['category_id'], aggregates=['__count'])
        } if self.ids else {}
        for record in self:
            record.project_count = counts.get(record.id, 0)


class CoopProject(models.Model):
    """Проект платформы — краудресурсинг.

    Название раздела дано владельцем: краудресурсинг — следующая ступень
    после краудинвестинга. Разница в том, чем скидываются. В краудфандинге
    и краудинвестинге — только деньгами; здесь — чем угодно, что имеет
    стоимость: трудом, техникой, материалами, помещением, знаниями,
    деньгами.

    Отсюда всё устройство. Доля участника не вписывается руками, а
    складывается: его вклад, делённый на сумму всех вкладов. Иначе смену
    экскаваторщика и перевод на счёт не свести в одну величину, и
    «коллективный проект» распадётся на инвесторов и наёмных.

    Готовность — тоже следствие, а не оценка: собрано против нужного.

    Управление проектом здесь не ведётся. Для этого есть штатный модуль
    Odoo, и он подключается, когда проект собран и запущен: до этого
    момента вести нечего, а после — незачем изобретать своё.
    """
    _name = 'coop.project'
    _description = 'Проект (краудресурсинг)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    # Не по готовности: собранных проектов больше семидесяти, и при
    # сортировке по готовности вся первая страница каталога — сплошь
    # стопроцентные полосы. Со стороны это выглядит так, будто полоса
    # сломана и всегда полная.
    _order = 'id desc'

    name = fields.Char(string='Название', required=True, index=True, tracking=True)
    summary = fields.Char(
        string='Коротко о проекте',
        help='Одна строка, которую видно в каталоге.')
    description = fields.Html(string='Описание')

    state = fields.Selection([
        ('draft', 'Замысел'),
        ('gathering', 'Сбор'),
        ('running', 'Запущен'),
        ('done', 'Завершён'),
        ('cancelled', 'Отменён'),
    ], string='Состояние', default='draft', required=True, index=True,
        tracking=True,
        help='Замысел — черновик, в каталоге его не видно. Сбор — проект '
             'ищет людей, ресурсы и деньги. Запущен — собранное позволяет '
             'начать, и здесь создаётся проект в модуле управления. '
             'Завершён — итоги и распределение.')

    kind = fields.Selection([
        ('cooperative', 'Кооперативный'),
        ('commercial', 'Коммерческий'),
        ('nonprofit', 'Некоммерческий'),
        ('dao', 'ДАО'),
    ], string='Вид проекта', default='cooperative', required=True, index=True,
        tracking=True,
        help='Как проект устроен внутри: кто принимает решения и как '
             'распределяется результат.')

    category_id = fields.Many2one(
        'coop.project.category', string='Тема', index=True, tracking=True,
        domain=[('parent_id', '=', False)])
    subcategory_id = fields.Many2one(
        'coop.project.category', string='Раздел', index=True,
        domain="[('parent_id', '=', category_id)]")
    city = fields.Char(string='Город', index=True)

    partner_id = fields.Many2one(
        'res.partner', string='Инициатор', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner(), tracking=True,
        help='Человек или организация, которые собирают проект.')
    author_id = fields.Many2one(
        'res.partner', string='Разместил', readonly=True, index=True,
        default=lambda self: self.env.user.partner_id,
        help='Кто из людей это разместил. У проекта частного лица '
             'совпадает с инициатором.')

    image_1920 = fields.Image(string='Изображение', max_width=1920, max_height=1920)
    image_512 = fields.Image(related='image_1920', max_width=512, max_height=512, store=True)

    # ── Ресурсы проекта ──────────────────────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        default=lambda self: self.env.company.currency_id)
    required_total = fields.Monetary(
        string='Нужно, ₽', currency_field='currency_id', tracking=True,
        help='Денежная оценка всего, что проекту нужно: деньгами, '
             'ресурсами и трудом. Готовность считается от неё.')
    contribution_ids = fields.One2many(
        'coop.project.contribution', 'project_id', string='Вклады')
    contribution_total = fields.Monetary(
        string='Собрано, ₽', currency_field='currency_id',
        compute='_compute_contribution_total', store=True,
        help='Сумма подтверждённых вкладов. От неё считается доля каждого.')
    contributor_count = fields.Integer(
        string='Участников', compute='_compute_contribution_total', store=True)
    readiness = fields.Integer(
        string='Готовность, %', compute='_compute_readiness', store=True,
        help='Собрано против нужного. Не оценка, а следствие вкладов.')

    # ── Связь с управлением проектами ────────────────────────────────────
    project_id = fields.Many2one(
        'project.project', string='Проект в управлении', readonly=True,
        copy=False,
        help='Создаётся при запуске. До запуска вести нечего, поэтому '
             'пусто — это не пропуск, а состояние дел.')

    need_ids = fields.One2many(
        'coop.resource', 'project_id', string='Потребности',
        domain=[('listing_type', '=', 'request')],
        help='Что проекту нужно: объявления спроса в каталоге ресурсов. '
             'На каждое приходят предложения, и утверждается одно.')
    need_count = fields.Integer(string='Потребностей',
                                compute='_compute_need_count')

    import_key = fields.Char(string='Ключ источника', index=True, copy=False)

    @api.depends('need_ids.state')
    def _compute_need_count(self):
        for record in self:
            record.need_count = len(record.need_ids.filtered(
                lambda need: need.state == 'published'))

    @api.depends('contribution_ids.value', 'contribution_ids.state')
    def _compute_contribution_total(self):
        for record in self:
            accepted = record.contribution_ids.filtered(
                lambda c: c.state == 'accepted')
            record.contribution_total = sum(accepted.mapped('value'))
            record.contributor_count = len(accepted.mapped('partner_id'))

    @api.depends('contribution_total', 'required_total')
    def _compute_readiness(self):
        for record in self:
            if record.required_total:
                record.readiness = min(
                    100, round(record.contribution_total / record.required_total * 100))
            else:
                record.readiness = 0

    @api.onchange('category_id')
    def _onchange_category(self):
        if self.subcategory_id.parent_id != self.category_id:
            self.subcategory_id = False

    # ── Действия ─────────────────────────────────────────────────────────

    def action_open_gathering(self):
        """Открыть сбор.

        Нужна подтверждённая личность: проект собирает чужие деньги и
        чужой труд, и знать, кто его собирает, вправе каждый вкладчик.
        """
        for record in self:
            record.partner_id.coop_require_level(
                'identity', _('открыть сбор по проекту'))
            if not record.required_total:
                raise UserError(_(
                    'У проекта «%s» не указано, сколько нужно. Без этого '
                    'готовность считать не от чего, и вкладчик не увидит, '
                    'сколько ещё собирать.') % record.name)
            record.state = 'gathering'
        return True

    def action_launch(self):
        """Запустить проект и завести его в модуле управления.

        Ровно та точка, о которой говорил владелец: до неё вести нечего,
        после неё — незачем изобретать своё. Задачи, сроки и учёт времени
        берём готовыми.
        """
        for record in self:
            if record.readiness < 100:
                raise UserError(_(
                    'Проект «%(name)s» собран на %(done)s%%. Запускать '
                    'недособранный проект значит обещать вкладчикам то, на '
                    'что не хватает.',
                    name=record.name, done=record.readiness))
            if not record.project_id:
                record.project_id = record._create_managed_project()
            record.state = 'running'
        return True

    def _create_managed_project(self):
        """Завести проект в штатном модуле управления.

        Обязательные поля туда добавляют другие модули Odoo — например,
        «Продажи и проекты» требует указать способ выставления счетов, и
        без него запись не создаётся вовсе. Перечислять их списком нельзя:
        набор зависит от того, что установлено на узле. Поэтому
        заполняются те, что действительно есть у модели, и значением по
        умолчанию самой Odoo.
        """
        self.ensure_one()
        Project = self.env['project.project'].sudo()
        values = {
            'name': self.name,
            'partner_id': self.partner_id.id,
            # Название задач у проекта — не перевод, а его собственное
            # поле, и по умолчанию оно английское. На карточке это
            # выглядит как «8 Tasks» посреди русского интерфейса, и
            # никаким обновлением языка не лечится: правится значение, а
            # не строка.
            'label_tasks': 'Задачи',
            # Видимость «по приглашению» — штатная механика Odoo, и она
            # ровно то, что нужно: проект виден подписчикам и тем, на кого
            # назначены задачи. Своих правил доступа для этого писать не
            # надо (решение владельца от 2026-09-14).
            'privacy_visibility': 'followers',
        }
        lead = self.partner_id.user_ids[:1]
        if lead:
            values['user_id'] = lead.id
        # Способ выставления счетов приходит из модуля учёта времени: поле
        # вычисляемое, но обязательное, и его расчёт значения не даёт —
        # он лишь понижает «вручную» до «без счетов». Пустым его колонка
        # не принимает, поэтому заполняем сами.
        if 'billing_type' in Project._fields:
            values['billing_type'] = 'not_billable'
        for name, field in Project._fields.items():
            if name in values or not field.store or field.type != 'selection':
                continue
            # Вычисляемое, но правимое поле тоже надо заполнить: расчёт
            # такого поля не обязан дать значение — у «способа выставления
            # счетов» он его и не даёт, а колонка при этом не допускает
            # пустоты. Полностью вычисляемые пропускаем: их считает Odoo.
            if field.compute and field.readonly:
                continue
            if not field.required:
                continue
            default = field.default
            if callable(default):
                default = default(Project)
            options = [code for code, _label in (field.selection or [])]
            values[name] = default or (options[0] if options else False)
        project = Project.create(values)
        project.message_subscribe(partner_ids=self._project_followers().ids)
        return project

    def _project_followers(self):
        """Кого проект должен видеть своими: инициатор и принятые вкладчики.

        Подписка — не украшение ленты, а доступ: при видимости «по
        приглашению» подписчик и есть тот, кто видит проект. Тот, чьё
        предложение приняли, становится подписчиком в тот же момент.
        """
        self.ensure_one()
        partners = self.partner_id
        partners |= self.contribution_ids.filtered(
            lambda c: c.state == 'accepted').mapped('partner_id')
        return partners

    @api.model
    def grant_project_access(self):
        """Право вести проекты — каждому участнику платформы.

        Решение владельца от 2026-09-14: раздел «Управление проектами»
        виден всем. Без права пользователя проектов штатный модуль
        прячет и меню, и сами записи — участник не увидел бы ни своих
        задач, ни сроков.

        Записью в XML это не сделать: `base.group_user` помечена как
        необновляемая, и правка молча пропускается — проверено, поле
        осталось прежним при нулевых ошибках в журнале.

        Роль руководителя проектов не выдаётся намеренно: она открывает
        все проекты узла целиком.
        """
        base_group = self.env.ref('base.group_user', raise_if_not_found=False)
        project_group = self.env.ref('project.group_project_user',
                                     raise_if_not_found=False)
        if not base_group or not project_group:
            return False
        if project_group in base_group.implied_ids:
            return True
        base_group.sudo().write({'implied_ids': [(4, project_group.id)]})
        _logger.info('Право вести проекты выдано всем участникам платформы')
        return True

    @api.model
    def backfill_managed_projects(self, limit=None):
        """Завести управляемый проект тем, кто запущен, но связи не имеет.

        Связь `project_id` заполняется при запуске — но запущенные
        проекты появились на платформе иначе: их завёл загрузчик
        наполнения сразу в нужном состоянии, минуя `action_launch`. В
        итоге поле объявлено, механика написана, а в базе пусто у всех
        двухсот записей: две вселенные проектов без единой точки
        касания.

        Добор идёт только по запущенным и завершённым. Замыслу и сбору
        управляемый проект не нужен: вести там пока нечего, и заводить
        его заранее значило бы засорить раздел управления пустыми
        карточками.

        Вызывается при обновлении модуля и безопасен к повторению: тем,
        у кого связь уже есть, ничего не делает.
        """
        # Заодно чиним название задач: по умолчанию оно английское, и на
        # карточке выходит «8 Tasks» посреди русского интерфейса. Это не
        # перевод, а поле проекта, и обновлением языка не лечится.
        #
        # Не трогаем то, что завела сама Odoo своими данными: у её
        # служебных проектов название не наше дело. Всё остальное на
        # платформе — наше, включая заглушки, оставшиеся от наполнения.
        Project = self.env['project.project'].sudo()
        theirs = self.env['ir.model.data'].sudo().search([
            ('model', '=', 'project.project')]).mapped('res_id')
        stale = Project.with_context(active_test=False).search([
            ('id', 'not in', theirs)])
        stale = stale.filtered(lambda p: p.label_tasks in (False, 'Tasks'))
        if stale:
            stale.write({'label_tasks': 'Задачи'})
            _logger.info('Название задач поправлено у %s проектов', len(stale))

        # Видимость и подписки у уже заведённых проектов: они создавались
        # до того, как видимость стала «по приглашению», и остались
        # открытыми всем.
        linked = self.search([('project_id', '!=', False)])
        opened = linked.filtered(
            lambda c: c.project_id.privacy_visibility != 'followers')
        for record in opened:
            record.project_id.sudo().privacy_visibility = 'followers'
        for record in linked:
            wanted = record._project_followers()
            missing = wanted - record.project_id.message_partner_ids
            if missing:
                record.project_id.sudo().message_subscribe(
                    partner_ids=missing.ids)
        if opened:
            _logger.info('Видимость «по приглашению» проставлена у %s проектов',
                         len(opened))

        records = self.search([
            ('state', 'in', ('running', 'done')),
            ('project_id', '=', False),
        ], limit=limit, order='id')
        made = 0
        for record in records:
            # Своя точка отката на каждую запись: обязательные поля
            # `project.project` приходят из чужих модулей, и падение на
            # одной записи не должно уносить весь добор.
            with self.env.cr.savepoint():
                record.project_id = record._create_managed_project()
                made += 1
        if made:
            _logger.info('Управляемых проектов заведено: %s из %s',
                         made, len(records))
        return made

    def action_finish(self):
        self.write({'state': 'done'})
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    # Состояния, в которых проект больше никого не ищет. Отмена — совсем,
    # заморозка — до поры; объявления снимаются в обоих случаях, потому
    # что снаружи разницы нет: человек откликается на потребность, которой
    # уже не существует.
    #
    # Заморозки в состояниях ещё нет — она предложена разбором экономиста
    # и ждёт решения. Когда появится, её достаточно дописать сюда.
    SILENT_STATES = ('cancelled',)

    def write(self, vals):
        """Снять объявления, когда проект перестал искать.

        Не в `action_cancel`, а в `write`: отменить проект можно и
        загрузчиком, и переносом, и правкой из списка — а объявление в
        каталоге живёт своей жизнью и само о проекте не узнает.
        """
        result = super().write(vals)
        if vals.get('state') in self.SILENT_STATES:
            self.filtered(
                lambda record: record.state in record.SILENT_STATES
            )._withdraw_listings()
        return result

    def _withdraw_listings(self):
        """Снять с публикации потребности и вакансии проекта.

        Обратно они сами не возвращаются: проект, который снова открыли,
        решает заново, что ему нужно. Возвращать всё скопом значило бы
        воскресить и то, что уже не актуально.
        """
        withdrawn = 0
        for record in self:
            needs = record.need_ids.filtered(
                lambda need: need.state == 'published')
            if needs:
                needs.sudo().write({'state': 'closed'})
                withdrawn += len(needs)
            if 'coop.vacancy' in self.env:
                vacancies = self.env['coop.vacancy'].sudo().search([
                    ('coop_project_id', '=', record.id),
                    ('state', '=', 'published'),
                ])
                if vacancies:
                    vacancies.write({'state': 'closed'})
                    withdrawn += len(vacancies)
            if withdrawn:
                record.message_post(body=_(
                    'Проект остановлен: объявления сняты с публикации, '
                    'снято всего %(count)s.', count=withdrawn))
        if withdrawn:
            _logger.info('Снято объявлений остановленных проектов: %s',
                         withdrawn)
        return withdrawn

    def action_open_project(self):
        self.ensure_one()
        if not self.project_id:
            raise UserError(_(
                'Проект ещё не запущен — в модуле управления его нет.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'project.project',
            'res_id': self.project_id.id,
            'view_mode': 'form',
        }


class CoopProjectContribution(models.Model):
    """Вклад в проект — не обязательно деньгами.

    Здесь и живёт краудресурсинг. Смена экскаваторщика, месяц аренды
    склада, пятьдесят тысяч рублей и переданный чертёж — всё это вклады, и
    свести их можно только через денежную оценку. Она и записывается.

    Оценка ставится соглашением сторон и потому требует принятия
    инициатором: вклад, оценённый в одностороннем порядке, размывал бы
    доли всех остальных.
    """
    _name = 'coop.project.contribution'
    _description = 'Вклад в проект'
    _inherit = ['mail.thread']
    _order = 'value desc, id desc'

    project_id = fields.Many2one(
        'coop.project', string='Проект', required=True, index=True,
        ondelete='cascade')
    partner_id = fields.Many2one(
        'res.partner', string='Вкладчик', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner(), tracking=True)

    kind = fields.Selection([
        ('money', 'Деньги'),
        ('labour', 'Труд'),
        ('resource', 'Ресурс или техника'),
        ('material', 'Материалы'),
        ('space', 'Помещение'),
        ('knowledge', 'Знания и документация'),
    ], string='Чем', required=True, default='money', index=True, tracking=True)

    name = fields.Char(
        string='Что именно', required=True,
        help='Смена экскаваторщика, месяц аренды склада, комплект досок.')
    value = fields.Monetary(
        string='Оценка, ₽', currency_field='currency_id', required=True,
        tracking=True,
        help='Денежная оценка вклада по соглашению сторон. Только через '
             'неё труд и деньги сводятся в одну величину.')
    currency_id = fields.Many2one(
        related='project_id.currency_id', string='Валюта', store=True)

    state = fields.Selection([
        ('offered', 'Предложен'),
        ('accepted', 'Принят'),
        ('declined', 'Отклонён'),
        ('returned', 'Возвращён'),
    ], string='Состояние', default='offered', required=True, index=True,
        tracking=True)

    share_percent = fields.Float(
        string='Доля, %', compute='_compute_share_percent', store=True,
        digits=(5, 2),
        help='Вклад, делённый на сумму принятых вкладов проекта. Меняется, '
             'когда в проект вносят что-то ещё, — так и должно быть.')

    # На какую потребность откликнулись. Пусто у вкладов, предложенных
    # проекту вообще, а не в ответ на объявленную нужду: так вносили до
    # появления потребностей, и так же вносят деньги «просто в проект».
    need_id = fields.Many2one(
        'coop.resource', string='Потребность', index=True,
        domain="[('project_id', '=', project_id), ('listing_type', '=', 'request')]",
        help='Объявление спроса, на которое это предложение.')

    offered_on = fields.Date(
        string='Предложен', default=fields.Date.context_today)
    accepted_on = fields.Date(string='Принят')

    @api.depends('value', 'state', 'project_id.contribution_total')
    def _compute_share_percent(self):
        for record in self:
            total = record.project_id.contribution_total
            if record.state == 'accepted' and total:
                record.share_percent = round(record.value / total * 100, 2)
            else:
                record.share_percent = 0

    def action_accept(self):
        """Принять вклад, а если он на потребность — утвердить предложение.

        Принимает инициатор проекта: оценка — это соглашение, и вклад,
        принятый вкладчиком самостоятельно, размывал бы доли остальных.
        У потребности может быть свой ответственный — тогда утверждает и
        он (решение владельца от 2026-09-14): на проекте в три десятка
        потребностей инициатор становится узким местом.

        Потребность закрывается одним предложением, остальные отклоняются
        сразу: держать откликнувшихся в ожидании после того, как выбор
        сделан, — неуважение к их времени.
        """
        for record in self:
            deciders = record.project_id.partner_id
            if record.need_id:
                deciders = record.need_id._need_deciders()
            allowed = (self.env.user.partner_id in deciders
                       or any(self.env.user.coop_has_power('deal', partner)
                              for partner in deciders))
            if not allowed:
                raise UserError(_(
                    'Утверждать предложения по проекту «%s» может его '
                    'инициатор, ответственный за потребность или тот, кому '
                    'организация поручила сделки.') % record.project_id.name)
            record.write({
                'state': 'accepted',
                'accepted_on': fields.Date.context_today(record),
            })
            record._close_need()
        return True

    def _close_need(self):
        """Закрыть потребность и отклонить остальные предложения по ней."""
        self.ensure_one()
        need = self.need_id
        if not need:
            return
        others = need.need_offer_ids.filtered(
            lambda offer: offer.id != self.id and offer.state == 'offered')
        if others:
            others.write({'state': 'declined'})
        need.write({'need_accepted_id': self.id, 'state': 'closed'})
        need.message_post(body=_(
            'Потребность закрыта: утверждено предложение «%(what)s» от '
            '%(who)s. Прочих предложений отклонено: %(count)s.',
            what=self.name, who=self.partner_id.name,
            count=len(others)))

    def action_decline(self):
        self.write({'state': 'declined'})
        return True
