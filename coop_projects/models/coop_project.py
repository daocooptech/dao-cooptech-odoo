# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

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


# Состояния проекта. Списком наверху, потому что их два поля: само
# состояние и то, куда вернуть проект после разморозки.
STATES = [
    ('draft', 'Идея'),
    ('gathering', 'Сбор'),
    ('running', 'Запущен'),
    ('frozen', 'Заморожен'),
    ('failed', 'Сбор не удался'),
    ('done', 'Завершён'),
    ('cancelled', 'Отменён'),
]

# Правовое основание денежного вклада. Решение владельца 294: разрешены
# все четыре. Это не оформление — от основания зависит, обязан ли проект
# вернуть деньги и в какой срок.
#
# Пожертвование: вернуть не обязан, но и потратить на другое не вправе.
# Предоплата: вернуть обязан, десять дней, полпроцента в день просрочки.
# Паевой взнос: возврат только при выходе из кооператива, по уставу.
# Инвестирование: заём, доля, ЦФА — требует статуса оператора
# инвестиционной платформы. До получения статуса закрыто настройкой узла.
# Состояния вклада. Четырёх не хватало: израсходованный материал нельзя
# перевести в «возвращён» — его нет, — а отклонение человеком и
# истечение срока это разные вещи, и складывать их в одну корзину значит
# портить репутацию тем, кого никто не отклонял.
CONTRIBUTION_STATES = [
    ('offered', 'Предложен'),
    ('accepted', 'Принят'),
    ('declined', 'Отклонён'),
    ('expired', 'Срок вышел'),
    ('withdrawn', 'Отозван'),
    ('consumed', 'Израсходован'),
    ('returned', 'Возвращён'),
    ('compensated', 'Возмещён деньгами'),
    ('released', 'Обязательство снято'),
    ('waived', 'Оставлен проекту'),
]

# Сколько дней у вкладчика на то, чтобы передумать. По закону период
# отзыва не обязателен — это продуктовое решение владельца 294.
WITHDRAW_DAYS = 7

# Границы срока сбора. Меньше двух недель никто не успеет узнать о
# проекте, больше полугода — это уже не срок, а его отсутствие.
MIN_DAYS = 14
MAX_DAYS = 180
DEFAULT_DAYS = 60

CONTRIBUTION_BASIS = [
    ('donation', 'Пожертвование или целевой взнос'),
    ('prepay', 'Предоплата за вознаграждение'),
    ('share', 'Паевой взнос пайщика'),
    ('investment', 'Инвестирование'),
]

# Кто держит деньги на время сбора. Счёта самой платформы здесь нет и не
# будет: деньги вкладчиков на нём — это сразу либо спецсчёт с ККТ и
# учётом в Росфинмониторинге, либо требование банковской лицензии.
PAYMENT_ROUTES = [
    ('nominal', 'Номинальный счёт в банке'),
    ('escrow', 'Эскроу-счёт'),
    ('contract', 'Смарт-контракт'),
    ('direct', 'Прямой платёж инициатору'),
]


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

    state = fields.Selection(STATES, string='Состояние', default='draft',
        required=True, index=True, tracking=True,
        help='Идея — черновик, в каталоге её не видно. Сбор — проект '
             'ищет людей, ресурсы и деньги. Запущен — собранное позволяет '
             'начать, и здесь создаётся проект в модуле управления. '
             'Завершён — итоги и распределение. Заморожен — приостановлен '
             'до поры, объявления сняты, но проект жив и его можно '
             'возобновить. Отменён — закрыт совсем.')

    # Куда вернётся проект при разморозке. Хранится, потому что снаружи
    # «заморожен» одинаков, а внутри разница есть: сбор продолжают
    # собирать, запущенный — вести. Спрашивать об этом при разморозке
    # значило бы перекладывать на человека то, что система знает сама.
    resume_state = fields.Selection(
        STATES, string='Вернуться в', readonly=True, copy=False)

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
    # Этап ведения показываем на карточке сбора, но правится он там, где
    # им и занимаются, — в управлении проектами. Две разные вещи рядом:
    # состояние сбора говорит, собрали ли; этап — где идут работы.
    project_stage_id = fields.Many2one(
        related='project_id.stage_id', string='Этап ведения', readonly=True,
        help='Столбец канбана в управлении проектами. Кооператив правит '
             'набор этапов сам: у стройки они одни, у разработки другие. '
             'Состояние сбора от них не зависит.')

    # Ход проекта — штатный отчёт Odoo, а не своя лента.
    #
    # «Новости проекта» из макета — это и есть отчёт о ходе: заголовок,
    # состояние, процент, дата, автор, описание, и он уходит подписчикам.
    # Своей моделью это писать нельзя: рядом с чаттером и стеной вышла бы
    # четвёртая сущность о том же самом. Пункт 14 разбора архитектора.
    #
    # На сборе показываем только последнее состояние — точкой в каталоге
    # и подписью на карточке. Сами отчёты живут у проекта в управлении,
    # там их и пишут.
    last_update_status = fields.Selection(
        related='project_id.last_update_status', string='Ход проекта',
        readonly=True,
        help='Последний отчёт о ходе. Пишется в управлении проектами: '
             'состояние сбора и состояние работ — разные вещи.')
    last_update_id = fields.Many2one(
        related='project_id.last_update_id', string='Последний отчёт',
        readonly=True)
    update_count = fields.Integer(
        string='Отчётов о ходе', compute='_compute_update_count')

    need_ids = fields.One2many(
        'coop.resource', 'project_id', string='Потребности',
        domain=[('listing_type', '=', 'request')],
        help='Что проекту нужно: объявления спроса в каталоге ресурсов. '
             'На каждое приходят предложения, и утверждается одно.')
    need_count = fields.Integer(string='Потребностей',
                                compute='_compute_need_count')

    # ── Срок сбора и правило закрытия ────────────────────────────────────
    #
    # Решение владельца 294. До него у проекта не было ни одной даты, и
    # сбор не кончался никогда: нельзя было ни показать «осталось
    # двенадцать дней», ни закрыть сбор, ни отличить заброшенный проект
    # от идущего.
    date_start = fields.Date(
        string='Сбор начат', readonly=True, copy=False,
        help='Ставится при открытии сбора.')
    date_deadline = fields.Date(
        string='Собираем до', tracking=True,
        help='Обязателен для открытия сбора: от него считается, сколько '
             'осталось, и по нему сбор закрывается сам.')
    days_left = fields.Integer(
        string='Осталось дней', compute='_compute_days_left')

    funding_rule = fields.Selection([
        ('all_or_nothing', 'Только полный сбор'),
        ('threshold', 'От порога'),
        ('keep_all', 'Оставляем собранное'),
    ], string='Правило закрытия', default='threshold', required=True,
        tracking=True,
        help='Что происходит, когда срок вышел. Полный сбор — не собрали '
             'сто процентов, сбор не удался. От порога — собрали больше '
             'порога, запускаемся на собранное. Оставляем собранное — '
             'запуск при любом сборе, но каждого вкладчика придётся '
             'спросить, вернуть ему деньги или оставить проекту.')
    funding_threshold = fields.Integer(
        string='Порог, %', default=70, tracking=True,
        help='При какой готовности проект считается собранным. Готовность '
             'у нас — сумма оценок разнородных вкладов, согласованных на '
             'глаз; требовать от неё точных ста процентов — ложная '
             'точность.')
    fallback_plan = fields.Text(
        string='Что сделаем, если соберём не всё',
        help='Обязательно, когда проект может запуститься на неполном '
             'сборе. Вкладчик должен читать не «порог 70 %», а что именно '
             'он получит при семидесяти процентах.')
    deadline_extensions = fields.Integer(
        string='Продлений срока', readonly=True, default=0, copy=False)

    # ── Правовой каркас ──────────────────────────────────────────────────
    contribution_basis = fields.Selection(
        CONTRIBUTION_BASIS, string='Основание денежного вклада',
        default='donation', tracking=True,
        help='От основания зависит, обязан ли проект вернуть деньги и в '
             'какой срок. Неденежных вкладов не касается.')
    payment_route = fields.Selection(
        PAYMENT_ROUTES, string='Кто держит деньги', default='nominal',
        tracking=True,
        help='Платформа получателем денег не бывает ни в каком варианте.')

    import_key = fields.Char(string='Ключ источника', index=True, copy=False)

    @api.depends('date_deadline', 'state')
    def _compute_days_left(self):
        today = fields.Date.context_today(self)
        for record in self:
            if record.state == 'gathering' and record.date_deadline:
                record.days_left = (record.date_deadline - today).days
            else:
                record.days_left = 0

    @api.constrains('funding_threshold')
    def _check_funding_threshold(self):
        for record in self:
            if not 50 <= record.funding_threshold <= 100:
                raise ValidationError(_(
                    'Порог сбора — от 50 до 100 процентов. Ниже половины '
                    'это уже другой проект, а не недособранный тот же.'))

    @api.constrains('state', 'fallback_plan', 'funding_rule',
                    'funding_threshold')
    def _check_fallback_plan(self):
        """Обещал запуститься на неполном сборе — скажи, что сделаешь."""
        for record in self:
            if record.state not in ('gathering', 'running'):
                continue
            partial = (record.funding_rule == 'keep_all'
                       or (record.funding_rule == 'threshold'
                           and record.funding_threshold < 100))
            if partial and not (record.fallback_plan or '').strip():
                raise ValidationError(_(
                    'Проект «%s» может запуститься на неполном сборе. '
                    'Напишите, что именно будет сделано в этом случае: '
                    'вкладчик читает не «порог 70 %%», а что он получит '
                    'при семидесяти процентах.') % record.name)

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
        """Готовность как есть, без потолка в сто процентов.

        Обрезка прятала перебор: проект, собравший втрое больше нужного,
        показывал ровно сто — и вкладчик не видел ни того, что деньги
        уже не нужны, ни того, что проект собрал вдвое. Ограничивать
        надо ширину полосы в вёрстке, а не само число: полоса и процент
        отвечают на разные вопросы.
        """
        for record in self:
            if record.required_total:
                record.readiness = round(
                    record.contribution_total / record.required_total * 100)
            else:
                record.readiness = 0

    @api.onchange('category_id')
    def _onchange_category(self):
        if self.subcategory_id.parent_id != self.category_id:
            self.subcategory_id = False

    # ── Действия ─────────────────────────────────────────────────────────

    # ── Этапы ведения ────────────────────────────────────────────────────
    #
    # Соответствие штатных этапов Odoo нашим. Нужно один раз — при
    # переходе; дальше проекты заводятся сразу на нашем наборе.
    STAGE_MAP = {
        'project.project_project_stage_0': 'coop_projects.project_stage_preparation',
        'project.project_project_stage_1': 'coop_projects.project_stage_work',
        'project.project_project_stage_2': 'coop_projects.project_stage_settlement',
        'project.project_project_stage_3': 'coop_projects.project_stage_stopped',
    }

    @api.model
    def adopt_project_stages(self):
        """Перевести ведение проектов на кооперативные этапы.

        Штатные этапы Odoo общие для любой конторы: «К выполнению»,
        «В процессе», «Готово», «Отменено». Кооперативный проект после
        запуска идёт иначе — подготовка, закупки, работы, приёмка,
        распределение, — и приёмка там не формальность: результат
        принимают те, кто вкладывался.

        Прежние этапы уводятся в архив, а не удаляются: они объявлены в
        чужом модуле с защитой от обновления, и удалённое вернулось бы
        при первой переустановке. Проекты, стоявшие на них,
        переставляются по соответствию — иначе сотня управляемых
        проектов осталась бы без этапа вовсе.

        Вызов идемпотентный: нечего переставлять — ничего не делает.
        """
        Stage = self.env['project.project.stage'].sudo()
        Project = self.env['project.project'].sudo()
        moved = archived = 0
        for old_xmlid, new_xmlid in self.STAGE_MAP.items():
            old = self.env.ref(old_xmlid, raise_if_not_found=False)
            new = self.env.ref(new_xmlid, raise_if_not_found=False)
            if not old or not new:
                continue
            on_old = Project.with_context(active_test=False).search(
                [('stage_id', '=', old.id)])
            if on_old:
                on_old.write({'stage_id': new.id})
                moved += len(on_old)
            if old.active:
                old.active = False
                archived += 1
        # Этап есть не у всех: проект, заведённый до появления набора,
        # мог остаться вовсе без него.
        first = self.env.ref('coop_projects.project_stage_preparation',
                             raise_if_not_found=False)
        if first:
            homeless = Project.with_context(active_test=False).search(
                [('stage_id', '=', False)])
            if homeless:
                homeless.write({'stage_id': first.id})
                moved += len(homeless)
        if moved or archived:
            _logger.info('Этапы ведения: переставлено проектов %s, '
                         'убрано в архив прежних этапов %s', moved, archived)
        return moved

    @api.model
    def recompute_readiness(self):
        """Пересчитать готовность там, где она осталась обрезанной.

        Поле хранимое, и от правки формулы само не пересчитывается: Odoo
        трогает вычисляемое поле, только когда меняется то, от чего оно
        зависит. Здесь не изменилось ни «собрано», ни «нужно» — изменился
        код, а обновление модуля об этом не знает.

        Ищем признак обрезки: собрано больше нужного, а готовность ровно
        сто. Ничего не нашли — выходим, поэтому вызывать можно при каждом
        обновлении.
        """
        capped = self.search([
            ('readiness', '=', 100),
            ('required_total', '>', 0),
        ]).filtered(
            lambda p: p.contribution_total > p.required_total)
        if not capped:
            return 0
        self.env.add_to_compute(self._fields['readiness'], capped)
        capped.flush_recordset(['readiness'])
        _logger.info('Готовность пересчитана без потолка: %s проектов',
                     len(capped))
        return len(capped)

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
            record._check_investment_allowed()
            today = fields.Date.context_today(record)
            if not record.date_deadline:
                record.date_deadline = today + timedelta(days=DEFAULT_DAYS)
            days = (record.date_deadline - today).days
            if not MIN_DAYS <= days <= MAX_DAYS:
                raise UserError(_(
                    'Срок сбора — от %(min)s до %(max)s дней. У проекта '
                    '«%(name)s» выходит %(days)s. Меньше двух недель никто '
                    'не успеет узнать о проекте, больше полугода — это уже '
                    'не срок, а его отсутствие.',
                    min=MIN_DAYS, max=MAX_DAYS, name=record.name, days=days))
            record.date_start = today
            record.state = 'gathering'
        return True

    def _check_investment_allowed(self):
        """Инвестиционный сбор — только со статусом оператора.

        Решение владельца 294: разрешены все четыре основания, включая
        инвестирование. Но заём, доля и ЦФА через платформу требуют
        статуса оператора инвестиционной платформы — ООО, собственные
        средства от пяти миллионов, реестр Банка России. Пока статуса
        нет, поле в схеме есть, а сбор по нему не открывается: иначе
        первый же заём через платформу — нарушение.
        """
        self.ensure_one()
        if self.contribution_basis != 'investment':
            return
        allowed = self.env['ir.config_parameter'].sudo().get_param(
            'coop.investment_operator')
        if allowed not in ('True', 'true', '1'):
            raise UserError(_(
                'Сбор по основанию «Инвестирование» на этом узле закрыт: '
                'заём, доля и цифровые права требуют статуса оператора '
                'инвестиционной платформы и записи в реестре Банка '
                'России. Пока статуса нет, выберите другое основание: '
                'пожертвование, предоплату за вознаграждение или паевой '
                'взнос.'))

    def _required_readiness(self):
        """При какой готовности проект считается собранным."""
        self.ensure_one()
        if self.funding_rule == 'all_or_nothing':
            return 100
        if self.funding_rule == 'threshold':
            return self.funding_threshold
        return 0

    def action_launch(self):
        """Запустить проект и завести его в модуле управления.

        Ровно та точка, о которой говорил владелец: до неё вести нечего,
        после неё — незачем изобретать своё. Задачи, сроки и учёт времени
        берём готовыми.
        """
        for record in self:
            need = record._required_readiness()
            if record.readiness < need:
                raise UserError(_(
                    'Проект «%(name)s» собран на %(done)s%%, а по его '
                    'правилу закрытия нужно %(need)s%%. Запускать '
                    'недособранный проект значит обещать вкладчикам то, на '
                    'что не хватает.',
                    name=record.name, done=record.readiness, need=need))
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
        # Первый этап ведения ставим сами. Odoo подставила бы свой
        # первый по порядку, а наш набор кооперативный: проект начинается
        # с подготовки, а не с «К выполнению».
        stage = self.env.ref('coop_projects.project_stage_preparation',
                             raise_if_not_found=False)
        if stage:
            values['stage_id'] = stage.id
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
        # Право видеть и менять этапы ведения — оттуда же. Без него
        # штатный модуль прячет столбцы канбана целиком: этапы заведены,
        # проекты по ним разложены, а участник видит один общий список.
        stages_group = self.env.ref('project.group_project_stages',
                                    raise_if_not_found=False)
        wanted = project_group
        if stages_group:
            wanted |= stages_group
        missing = wanted - base_group.implied_ids
        if not missing:
            return True
        base_group.sudo().write({
            'implied_ids': [(4, group.id) for group in missing]})
        _logger.info('Права на ведение проектов выданы всем участникам: %s',
                     ', '.join(missing.mapped('name')))
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

        Добор идёт только по запущенным и завершённым. Идее и сбору
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

    def action_freeze(self):
        """Заморозить проект: приостановить, не закрывая.

        Между «идёт» и «отменён» есть промежуток, и он занимает месяцы:
        инициатор уехал, поставщик сорвался, ждут разрешения. Отменять
        такой проект нечестно — вклады остаются, участники остаются, —
        а оставлять его в сборе нечестно вдвойне: он продолжает звать
        людей, которых сейчас некому встретить.
        """
        for record in self:
            if record.state not in ('gathering', 'running'):
                raise UserError(_(
                    'Заморозить можно проект в сборе или запущенный. '
                    'Проект «%(name)s» сейчас в состоянии «%(state)s».',
                    name=record.name,
                    state=dict(STATES).get(record.state, record.state)))
            record.write({'resume_state': record.state, 'state': 'frozen'})
            record.message_post(body=_(
                'Проект заморожен. Объявления сняты с публикации; вклады '
                'и участники сохранены. При возобновлении проект вернётся '
                'в состояние «%s».') % dict(STATES)[record.resume_state])
        return True

    def action_resume(self):
        """Разморозить проект и вернуть его туда, откуда заморозили.

        Объявления обратно не поднимаются намеренно: пока проект стоял,
        часть потребностей закрылась сама, часть устарела. Возвращать их
        скопом значило бы позвать людей на работу, которой уже нет.
        """
        for record in self:
            if record.state != 'frozen':
                raise UserError(_(
                    'Возобновлять нечего: проект «%s» не заморожен.')
                    % record.name)
            back = record.resume_state or 'gathering'
            record.write({'state': back, 'resume_state': False})
            record.message_post(body=_(
                'Проект возобновлён, состояние — «%(state)s». Объявления '
                'нужно опубликовать заново: пока проект стоял, часть '
                'потребностей могла отпасть.',
                state=dict(STATES)[back]))
        return True

    def action_fail(self):
        """Признать сбор несостоявшимся.

        Отдельно от отмены, и это не косметика. Отмена — волевое действие
        человека, за неё отвечает инициатор; несостоявшийся сбор —
        обстоятельство, вины ничьей нет. От разницы зависит доверие: если
        склеить их в одно состояние, честные сборы перестанут открывать.
        """
        for record in self:
            if record.state != 'gathering':
                raise UserError(_(
                    'Признать сбор несостоявшимся можно только пока он '
                    'идёт. Проект «%s» сейчас не в сборе.') % record.name)
            record.state = 'failed'
            record.message_post(body=_(
                'Сбор не удался: к сроку собрано %(done)s%% при нужных '
                '%(need)s%%. Объявления сняты. Денежные вклады подлежат '
                'возврату, обещанное трудом и вещами — снятию.',
                done=record.readiness, need=record._required_readiness()))
        return True

    @api.model
    def close_expired_gatherings(self):
        """Закрыть сборы, у которых вышел срок.

        Раз в сутки. Без этого прохода срок — просто число на карточке:
        проект, у которого он давно вышел, продолжает стоять в каталоге и
        собирать.
        """
        today = fields.Date.context_today(self)
        expired = self.sudo().search([
            ('state', '=', 'gathering'),
            ('date_deadline', '!=', False),
            ('date_deadline', '<', today),
        ])
        launched = failed = 0
        for project in expired:
            need = project._required_readiness()
            if project.readiness >= need:
                # Запускаем тем же кодом, что и кнопка: иначе крон
                # создавал бы состояние, которого платформа сама достичь
                # не умеет.
                with self.env.cr.savepoint():
                    project.action_launch()
                    launched += 1
            else:
                with self.env.cr.savepoint():
                    project.action_fail()
                    failed += 1
        if launched or failed:
            _logger.info('Сроки сбора: запущено %s, не удалось %s',
                         launched, failed)
        return launched + failed

    # Состояния, в которых проект больше никого не ищет. Отмена — совсем,
    # заморозка — до поры, несостоявшийся сбор — по сроку; объявления
    # снимаются во всех трёх случаях, потому что снаружи разницы нет:
    # человек откликается на потребность, которой уже не существует.
    SILENT_STATES = ('cancelled', 'frozen', 'failed')

    def write(self, vals):
        """Снять объявления, когда проект перестал искать.

        Не в `action_cancel`, а в `write`: отменить проект можно и
        загрузчиком, и переносом, и правкой из списка — а объявление в
        каталоге живёт своей жизнью и само о проекте не узнает.
        """
        result = super().write(vals)
        if vals.get('state') in self.SILENT_STATES:
            stopped = self.filtered(
                lambda record: record.state in record.SILENT_STATES)
            stopped._withdraw_listings()
            # Расчёт с вкладчиками — тоже здесь, а не в кнопке: сбор
            # закрывает крон, отменить проект можно из списка, и человек,
            # отдавший деньги, не должен зависеть от того, каким путём
            # проект остановили.
            stopped.filtered(
                lambda record: record.state == 'failed'
            )._settle_contributions()
        return result

    recovery_share = fields.Integer(
        string='Доля остатка на покрытие невозвратного, %', default=50,
        help='Покрыть труд целиком — денежный вкладчик оплатил чужой труд '
             'и ушёл ни с чем. Не покрывать вовсе — человек отдал месяц '
             'жизни, а деньги соседу вернулись. Половина остатка — '
             'осознанный компромисс между двумя этими провалами.')

    def _settle_contributions(self):
        """Рассчитаться с вкладчиками остановленного проекта.

        Запускается само при переходе в «Сбор не удался» и «Отменён»
        (решение владельца 294): молчаливый инициатор иначе оставляет
        людей без денег и без ответа.

        Провал сбора: проект ничего не начинал, физической передачи по
        правилу не было — деньги возвращаются целиком, обещанное трудом и
        вещами снимается.

        Отмена запущенного: часть потрачена, часть сделана. Здесь считать
        по очередям, и это отдельное действие — распределение чужих денег
        должно быть видно до нажатия, а не случиться молча.
        """
        settled = 0
        for project in self:
            live = project.contribution_ids.filtered(
                lambda c: c.state in ('offered', 'accepted'))
            if not live:
                continue
            # Непринятые просто истекают: проект на них не рассчитывал, и
            # отклонением это назвать нельзя — никто их не отклонял.
            pending = live.filtered(lambda c: c.state == 'offered')
            if pending:
                pending.sudo().write({'state': 'expired'})

            accepted = live.filtered(lambda c: c.state == 'accepted')
            if project.state == 'failed':
                money = accepted.filtered(lambda c: c.kind == 'money')
                if money:
                    money.sudo().write({
                        'state': 'returned',
                        'refund_amount': 0,
                    })
                    for record in money:
                        record.sudo().refund_amount = record.value
                rest = accepted - money
                if rest:
                    rest.sudo().write({'state': 'released'})
                settled += len(accepted)
            project.message_post(body=_(
                'Расчёт с вкладчиками: истёкших предложений %(pending)s, '
                'закрыто принятых вкладов %(accepted)s.',
                pending=len(pending), accepted=len(accepted)))
        if settled:
            _logger.info('Рассчитано вкладов остановленных проектов: %s',
                         settled)
        return settled

    def _withdraw_listings(self):
        """Снять с публикации потребности и вакансии проекта.

        Обратно они сами не возвращаются: проект, который снова открыли,
        решает заново, что ему нужно. Возвращать всё скопом значило бы
        воскресить и то, что уже не актуально.
        """
        withdrawn = 0
        for record in self:
            # Счётчик на запись, а не общий: при отмене пачкой проектов
            # общий счётчик писал в ленту каждого проекта итог всей пачки.
            here = 0
            needs = record.need_ids.filtered(
                lambda need: need.state == 'published')
            if needs:
                needs.sudo().write({'state': 'closed'})
                here += len(needs)
            if 'coop.vacancy' in self.env:
                vacancies = self.env['coop.vacancy'].sudo().search([
                    ('coop_project_id', '=', record.id),
                    ('state', '=', 'published'),
                ])
                if vacancies:
                    vacancies.write({'state': 'closed'})
                    here += len(vacancies)
            if here:
                record.message_post(body=_(
                    'Объявления сняты с публикации, снято всего '
                    '%(count)s.', count=here))
            withdrawn += here
        if withdrawn:
            _logger.info('Снято объявлений остановленных проектов: %s',
                         withdrawn)
        return withdrawn

    @api.depends('project_id')
    def _compute_update_count(self):
        # Считаем одним запросом на всю выборку: у каталога карточек
        # двести, и по запросу на каждую он встанет.
        по_проектам = {}
        проекты = self.mapped('project_id')
        if проекты:
            группы = self.env['project.update'].sudo()._read_group(
                [('project_id', 'in', проекты.ids)], ['project_id'],
                ['__count'])
            по_проектам = {проект.id: сколько for проект, сколько in группы}
        for record in self:
            record.update_count = по_проектам.get(record.project_id.id, 0)

    def action_open_updates(self):
        """Отчёты о ходе проекта — штатные, Odoo.

        Своей ленты новостей у нас нет намеренно: отчёт о ходе это
        документ, а не сообщение, и он уже есть в движке вместе с
        рассылкой подписчикам и показом в канбане управления.
        """
        self.ensure_one()
        if not self.project_id:
            raise UserError(
                'Проект ещё не запущен: вести пока нечего. Отчёт о ходе '
                'пишется тогда, когда работы начались.')
        action = self.env['ir.actions.actions']._for_xml_id(
            'project.project_update_all_action')
        # Заголовок свой: у штатного действия он «Dashboard», и на
        # русской платформе это выглядит как чужая страница.
        action['name'] = 'Ход проекта: %s' % self.name
        action['domain'] = [('project_id', '=', self.project_id.id)]
        action['context'] = {
            'default_project_id': self.project_id.id,
            'active_id': self.project_id.id,
        }
        return action

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

    state = fields.Selection(CONTRIBUTION_STATES,
        string='Состояние', default='offered', required=True, index=True,
        tracking=True)

    # ── Возврат ──────────────────────────────────────────────────────────
    #
    # Решение владельца 294. Два принципа, из которых выводится всё
    # остальное: возвращается то, что ещё не потрачено; и участник не
    # может оказаться должен проекту — максимум, чем он рискует, это его
    # вклад. За этой границей кооперация превращается в кабалу.
    delivered_on = fields.Date(
        string='Передано по акту', readonly=True, copy=False,
        help='Пока проект не запущен, передавать нечего: при провале '
             'сбора по определению ничего не передано, и «вернуть смену '
             'экскаваторщика» не возникает как задача.')
    withdraw_until = fields.Date(
        string='Отозвать можно до', compute='_compute_withdraw_until',
        store=True,
        help='Семь дней с принятия, но не позже закрытия сбора и не '
             'после передачи по акту. Окно открывается заново, если '
             'проект существенно изменился.')
    can_withdraw = fields.Boolean(
        string='Можно отозвать', compute='_compute_can_withdraw')
    refund_amount = fields.Monetary(
        string='Возвращено', currency_field='currency_id', readonly=True,
        copy=False)
    unrecovered_amount = fields.Monetary(
        string='Не возмещено', currency_field='currency_id', readonly=True,
        copy=False,
        help='Невозмещённая часть невозвратного вклада. Это не долг '
             'проекта, а признанная потеря участника: она видна в его '
             'профиле и идёт в минус доверию инициатора.')
    return_mode = fields.Selection([
        ('money_back', 'Вернуть деньгами'),
        ('in_kind', 'Вернуть вещь'),
        ('compensation', 'Возместить оценку деньгами'),
        ('irrevocable', 'Безвозвратный'),
    ], string='Как возвращается', compute='_compute_return_mode',
        store=True, readonly=False,
        help='Выводится из вида вклада и основания сбора, но правится: '
             'труд физически не вернуть, а пай возвращается не деньгами '
             'по требованию, а через выход из кооператива.')

    # Форма трудового вклада. Решение владельца 294: требовать выбор там,
    # где этого требует закон страны; где не требует — поле есть, но
    # необязательное, со своим вариантом и отправкой на модерацию.
    # Механика «своего варианта» — открытый вопрос, пока перечень закрыт.
    labour_form = fields.Selection([
        ('member', 'Трудовое участие члена кооператива'),
        ('contract', 'Договор подряда или услуг'),
        ('selfemployed', 'Самозанятый'),
        ('employment', 'Трудовой договор'),
    ], string='Как оформлен труд',
        help='Неустранимые сомнения толкуются в пользу трудовых '
             'отношений. Без выбора инициатор рискует штрафом и '
             'доначислением взносов.')

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

    @api.constrains('state', 'kind', 'partner_id', 'project_id')
    def _check_member_for_share_basis(self):
        """Паевой взнос вносит только пайщик.

        Условие из заключения юриста, и оно жёсткое: как только в сборе
        паевых взносов участвует человек, который не член кооператива, —
        это уже не пай, а привлечение средств от постороннего, со всем
        259-ФЗ следом. Решение владельца 294: проверять членство.

        Проверяется только денежный вклад: труд и техника в предмет
        закона об инвестиционных платформах не попадают, а вносить их
        может кто угодно.
        """
        Membership = self.env['coop.membership'].sudo()
        for record in self:
            project = record.project_id
            if (record.state != 'accepted' or record.kind != 'money'
                    or project.contribution_basis != 'share'):
                continue
            org = project.partner_id
            if not org.is_company:
                # Инициатор-человек кооперативом не бывает, и паевого
                # фонда у него нет. Основание выбрано ошибочно.
                raise ValidationError(_(
                    'Проект «%s» собирает паевые взносы, но его инициатор '
                    'не организация. Пай вносят в паевой фонд '
                    'кооператива — выберите другое основание сбора.')
                    % project.name)
            member = Membership.search([
                ('partner_id', '=', record.partner_id.id),
                ('organization_id', '=', org.id),
                ('state', '=', 'active'),
            ], limit=1)
            if not member:
                raise ValidationError(_(
                    '%(who)s не состоит в «%(org)s», а проект собирает '
                    'паевые взносы. Пай вносит пайщик: вступите в '
                    'кооператив или внесите вклад иначе — трудом, '
                    'техникой, материалами.',
                    who=record.partner_id.display_name, org=org.name))

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
        # Дальше — последствия уже принятого решения, а не новое
        # решение: право утверждать проверено выше по существу. Права на
        # сами записи у утвердившего может не быть — у представителя
        # организации полномочие на сделки есть, а на публикации нет, и
        # закрыть объявление он без этого не может.
        others = need.need_offer_ids.filtered(
            lambda offer: offer.id != self.id and offer.state == 'offered')
        if others:
            others.sudo().write({'state': 'declined'})
        need.sudo().write({'need_accepted_id': self.id, 'state': 'closed'})
        need.sudo().message_post(body=_(
            'Потребность закрыта: утверждено предложение «%(what)s» от '
            '%(who)s. Прочих предложений отклонено: %(count)s.',
            what=self.name, who=self.partner_id.name,
            count=len(others)))

    def action_decline(self):
        self.write({'state': 'declined'})
        return True

    # ── Вычисления возврата ──────────────────────────────────────────────

    @api.depends('kind', 'project_id.contribution_basis')
    def _compute_return_mode(self):
        for record in self:
            if record.kind == 'labour':
                # Смену экскаваторщика не вернуть. Закон этого и не
                # требует — он требует другого: вернуть деньгами по
                # согласованной оценке, если работа уже сделана.
                record.return_mode = 'compensation'
            elif record.kind == 'money':
                basis = record.project_id.contribution_basis
                # Пай по требованию не возвращают: только при выходе из
                # кооператива и в сроки устава. Исключение — несостоявшийся
                # сбор: основание отпало, проекта не будет (решение 294).
                record.return_mode = ('money_back' if basis != 'share'
                                      else 'money_back')
            elif record.kind in ('material', 'knowledge'):
                record.return_mode = 'compensation'
            else:
                record.return_mode = 'in_kind'

    # Два вычисления, а не одно на оба поля. Одно хранимое, другое нет, и
    # Odoo на общий метод ругается: обращение к нехранимому пересчитывает
    # и перезаписывает хранимое. Предупреждение в журнале при каждой
    # загрузке реестра — верный способ перестать его замечать.
    @api.depends('state', 'accepted_on', 'delivered_on',
                 'project_id.date_deadline')
    def _compute_withdraw_until(self):
        for record in self:
            record.withdraw_until = False
            if record.state != 'accepted' or not record.accepted_on:
                continue
            if record.delivered_on:
                # Переданное назад не отзывают.
                continue
            until = record.accepted_on + timedelta(days=WITHDRAW_DAYS)
            deadline = record.project_id.date_deadline
            if deadline and deadline < until:
                until = deadline
            record.withdraw_until = until

    @api.depends('state', 'withdraw_until', 'delivered_on',
                 'project_id.state')
    def _compute_can_withdraw(self):
        today = fields.Date.context_today(self)
        for record in self:
            gathering = record.project_id.state == 'gathering'
            if record.state == 'offered':
                # Непринятый вклад отзывается свободно: проект на него
                # ещё не рассчитывал.
                record.can_withdraw = gathering
            elif record.state == 'accepted' and record.withdraw_until:
                record.can_withdraw = (gathering
                                       and not record.delivered_on
                                       and today <= record.withdraw_until)
            else:
                record.can_withdraw = False

    # ── Действия возврата ────────────────────────────────────────────────

    def action_withdraw(self):
        """Отозвать свой вклад.

        Непринятый — свободно: проект на него ещё не рассчитывал.
        Принятый — в период отзыва; дальше только с согласия инициатора,
        потому что готовность проекта уже посчитана с этим вкладом, и
        другие вкладывались, глядя на неё.
        """
        for record in self:
            if self.env.user.partner_id != record.partner_id:
                raise UserError(_(
                    'Отозвать вклад может только тот, кто его внёс.'))
            if not record.can_withdraw:
                raise UserError(_(
                    'Вклад «%(name)s» отозвать уже нельзя: срок отзыва '
                    'вышел %(until)s либо вклад передан по акту. '
                    'Договаривайтесь с инициатором проекта.',
                    name=record.name, until=record.withdraw_until or '—'))
            record.write({'state': 'withdrawn'})
            record.project_id.sudo().message_post(body=_(
                'Вклад «%(what)s» отозван вкладчиком %(who)s.',
                what=record.name, who=record.partner_id.display_name))
        return True

    def action_mark_delivered(self):
        """Отметить передачу по акту.

        До запуска проекта передавать нечего — и это не формальность.
        Пока передачи нет, при провале сбора нечего возвращать натурой, и
        весь расчёт сводится к деньгам.
        """
        for record in self:
            if record.project_id.state != 'running':
                raise UserError(_(
                    'Передавать вклад можно только в запущенном проекте. '
                    'Проект «%s» ещё не запущен: пока сбор не закрыт, '
                    'передача не нужна и лишь мешает вернуть вклад, если '
                    'сбор не удастся.') % record.project_id.name)
            if record.state != 'accepted':
                raise UserError(_(
                    'Передавать можно принятый вклад.'))
            record.delivered_on = fields.Date.context_today(record)
        return True

    def action_consume(self):
        """Отметить вклад израсходованным — точка невозврата."""
        for record in self:
            if record.state != 'accepted':
                raise UserError(_('Израсходовать можно принятый вклад.'))
            record.state = 'consumed'
        return True

    def action_release(self):
        """Снять обязательство по неденежному вкладу.

        Возвращать нечего: смена экскаваторщика не передавалась, а была
        обещана. Снимается именно обещание.
        """
        for record in self:
            if record.kind == 'money':
                raise UserError(_(
                    'Денежный вклад так не закрывают: его возвращают.'))
            record.state = 'released'
        return True

    def action_return(self, amount=None):
        """Вернуть денежный вклад."""
        for record in self:
            if record.kind != 'money':
                raise UserError(_(
                    'Вернуть деньгами можно денежный вклад. Для '
                    'остальных — «Возместить» или «Снять обязательство».'))
            record.write({
                'state': 'returned',
                'refund_amount': record.value if amount is None else amount,
            })
        return True

    def action_compensate(self, amount=None):
        """Возместить деньгами то, что нельзя вернуть в натуре."""
        for record in self:
            paid = record.value if amount is None else amount
            record.write({
                'state': 'compensated',
                'refund_amount': paid,
                'unrecovered_amount': max(record.value - paid, 0),
            })
        return True

    def action_waive(self):
        """Оставить вклад проекту.

        Отдельным действием вкладчика, а не умолчанием: молчание
        согласием не считается.
        """
        for record in self:
            if self.env.user.partner_id != record.partner_id:
                raise UserError(_(
                    'Оставить вклад проекту может только тот, кто его '
                    'внёс. Решить это за него нельзя.'))
            record.state = 'waived'
        return True
