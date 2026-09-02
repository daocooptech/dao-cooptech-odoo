# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


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

    _sql_constraints = [
        ('name_parent_uniq', 'unique(name, parent_id)',
         'Такая тема на этом уровне уже есть.'),
    ]

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
    _order = 'readiness desc, id desc'

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

    import_key = fields.Char(string='Ключ источника', index=True, copy=False)

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
        values = {'name': self.name, 'partner_id': self.partner_id.id}
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
        return Project.create(values)

    def action_finish(self):
        self.write({'state': 'done'})
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

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
        """Принять вклад.

        Принимает инициатор проекта: оценка — это соглашение, и вклад,
        принятый вкладчиком самостоятельно, размывал бы доли остальных.
        """
        for record in self:
            if not self.env.user.coop_has_power('deal', record.project_id.partner_id) \
                    and record.project_id.partner_id != self.env.user.partner_id:
                raise UserError(_(
                    'Принимать вклады в проект «%s» может его инициатор или '
                    'тот, кому организация поручила сделки.') % record.project_id.name)
            record.write({
                'state': 'accepted',
                'accepted_on': fields.Date.context_today(record),
            })
        return True

    def action_decline(self):
        self.write({'state': 'declined'})
        return True
