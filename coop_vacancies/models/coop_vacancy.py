# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Чем вознаграждается труд — по виду организации (решение 416, п. 2,
# владелец 26.09.2026): «ООО — рубли, кооператив — пай, ДАО — токены, DEX —
# криптовалюты и токены. Самозанятые относятся к коммерческим
# организациям». НКО владелец не называл — у них зарплата, рубли.
# Поправка 27.09.2026 (решение 424): «кооператив — может платить как
# зачислением в пай так и просто деньгами, но тогда у него возникает налог,
# потому что это наемный сотрудник по трудовому договору» — у кооператива
# выбор из двух, и рубли означают трудовой договор.
LABOUR_PAY = [
    ('rub', 'Рублями'),
    ('share', 'Зачислением в пай'),
    ('tokens', 'Токенами'),
]
LABOUR_PAY_SUFFIX = {'share': 'в пай', 'tokens': 'токенами'}
TOKEN_FORMS = ('dao', 'platform')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_labour_pay = fields.Selection(
        LABOUR_PAY, string='Чем вознаграждает труд',
        compute='_compute_coop_labour_pay', store=True, index=True,
        help='Что ставится в новую вакансию по умолчанию (решения 416, 424): '
             'кооператив — зачисление в пай (может выбрать и рубли), ДАО — '
             'токены, коммерческие организации, самозанятые и частные лица — '
             'рубли.')

    @api.depends('is_company', 'coop_legal_form_id.is_cooperative', 'coop_legal_form_id.code')
    def _compute_coop_labour_pay(self):
        for partner in self:
            form = partner.coop_legal_form_id
            if form.is_cooperative:
                partner.coop_labour_pay = 'share'
            elif form.code in TOKEN_FORMS:
                partner.coop_labour_pay = 'tokens'
            else:
                partner.coop_labour_pay = 'rub'

    def _coop_labour_pay_allowed(self):
        """Какие формы вознаграждения открыты этому участнику.

        Кооператив платит и зачислением в пай, и деньгами (решение 424),
        ДАО — токенами, остальные — рублями.
        """
        self.ensure_one()
        if self.coop_legal_form_id.is_cooperative:
            return ('share', 'rub')
        return (self.coop_labour_pay or 'rub',)


class CoopVacancy(models.Model):
    """Вакансия — предложение работы от участника платформы.

    Обратная сторона предложения навыка: там человек говорит, что готов
    делать, здесь — кому нужна работа. Стороны разные, и смешивать их в
    одном списке нельзя.

    Вознаграждение бывает не только деньгами, и это не украшение
    кооперативной риторики: в макете семнадцать вакансий из ста
    предлагают долю в проекте, девять — обмен услугами, пять —
    волонтёрство. Причём доля и деньги часто идут вместе: «доля 4% плюс
    60 000 ₽». Модель обязана это выдержать, иначе треть каталога
    придётся описывать текстом в примечании.
    """
    _name = 'coop.vacancy'
    _description = 'Вакансия'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'coop.page.mixin']
    _coop_page_view = 'coop_vacancies.view_coop_vacancy_form'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Кто нужен', required=True, tracking=True)
    description = fields.Html(
        string='Что делать',
        help='Задача и условия. По этому тексту человек решает, откликаться '
             'ли, поэтому обязанности лучше писать конкретнее, чем «работа '
             'в дружном коллективе».')
    image_1920 = fields.Image(string='Фотография', max_width=1920, max_height=1920)
    image_512 = fields.Image(related='image_1920', max_width=512, max_height=512, store=True)

    # ── Кто ищет ─────────────────────────────────────────────────────────
    partner_id = fields.Many2one(
        'res.partner', string='Кто ищет', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner(), tracking=True,
        help='Человек или организация. Вакансию может разместить и частное '
             'лицо: в макете таких двенадцать из ста.')
    author_id = fields.Many2one(
        'res.partner', string='Опубликовал', readonly=True, index=True,
        default=lambda self: self.env.user.partner_id,
        help='Кто разместил вакансию от лица организации. У вакансии '
             'частного лица совпадает с ним самим.')
    project_id = fields.Many2one(
        'project.project', string='Проект',
        help='Если работа нужна проекту, а не организации. Отсюда же '
             'берётся сумма вкладов, от которой считается доля.')

    coop_specialization_id = fields.Many2one(
        'coop.specialization', string='Специализация', index=True,
        ondelete='restrict')
    coop_specialization_category_id = fields.Many2one(
        'coop.specialization.category', string='Сфера деятельности',
        related='coop_specialization_id.category_id', store=True, index=True)
    skill_ids = fields.Many2many(
        'hr.skill', 'coop_vacancy_skill_rel', 'vacancy_id', 'skill_id',
        string='Что потребуется')

    city = fields.Char(string='Город', index=True)

    employment = fields.Selection([
        ('full', 'Полная занятость'),
        ('part', 'Частичная занятость'),
        ('project', 'Проектная работа'),
        ('volunteer', 'Волонтёрство'),
    ], string='Занятость', required=True, default='full', index=True)

    experience_level = fields.Selection([
        ('none', 'Без опыта'),
        ('junior', 'От года'),
        ('senior', 'От трёх лет'),
    ], string='Требуемый опыт', required=True, default='junior', index=True)

    # ── Вознаграждение ───────────────────────────────────────────────────
    reward_kind = fields.Selection([
        ('money', 'Деньги'),
        ('share', 'Доля в проекте'),
        ('barter', 'Обмен услугами'),
        ('volunteer', 'Волонтёрство'),
    ], string='Чем вознаграждают', required=True, default='money',
        index=True, tracking=True)

    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        default=lambda self: self.env.company.currency_id)
    pay_from = fields.Monetary(string='Оплата от', currency_field='currency_id')
    pay_to = fields.Monetary(string='Оплата до', currency_field='currency_id')
    pay_period = fields.Selection([
        ('month', 'в месяц'),
        ('shift', 'за смену'),
        ('hour', 'в час'),
        ('job', 'за работу'),
        ('lesson', 'за занятие'),
    ], string='Период оплаты', default='month')

    # Доля не вписывается процентом, а считается: вклад участника делится
    # на сумму всех вкладов проекта (решение владельца от 2026-09-01).
    # Поэтому здесь хранится денежная оценка вклада, а процент выводится.
    # Вписанный руками процент разошёлся бы с расчётом на второй же неделе
    # жизни проекта, когда в него внесут что-то ещё.
    contribution_value = fields.Monetary(
        string='Оценка вклада', currency_field='currency_id',
        help='Во сколько оценивается работа исполнителя как вклад в проект. '
             'От неё считается доля: вклад к сумме всех вкладов проекта.')
    share_percent = fields.Float(
        string='Доля, %', compute='_compute_share_percent', store=True,
        digits=(5, 2),
        help='Считается от оценки вклада к сумме вкладов проекта. Пока '
             'сумма вкладов не заполнена, доля неизвестна — и показывать '
             'вместо неё ноль было бы неправдой.')

    reward_display = fields.Char(
        string='Вознаграждение строкой', compute='_compute_reward_display',
        store=True)
    reward_note = fields.Char(
        string='Уточнение к вознаграждению',
        help='Всё, что не укладывается в поля: «оплата после испытательного», '
             '«доля обсуждается», «плюс жильё».')
    labour_pay = fields.Selection(
        LABOUR_PAY, string='Чем платят', compute='_compute_labour_pay',
        store=True, readonly=False, index=True, tracking=True,
        help='Зависит от того, кто ищет (решения 416, 424): кооператив '
             'выбирает — зачисление в пай или рубли, ДАО платит токенами, '
             'коммерческие организации, самозанятые и частные лица — рублями.')
    labour_pay_choice = fields.Boolean(
        string='Форму можно выбрать', compute='_compute_labour_pay_choice',
        help='Выбор есть только у кооператива: пай или рубли.')
    labour_pay_note = fields.Char(
        string='Что это значит', compute='_compute_labour_pay_choice',
        help='Кооператив, платящий рублями, берёт человека наёмным '
             'сотрудником по трудовому договору — и с выплаты возникает налог '
             '(решение 424).')

    # ── Состояние ────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Черновик'),
        ('published', 'Опубликована'),
        ('closed', 'Закрыта'),
    ], string='Состояние', default='draft', required=True,
        tracking=True, index=True)

    application_ids = fields.One2many(
        'coop.vacancy.application', 'vacancy_id', string='Отклики')
    application_count = fields.Integer(
        string='Откликов', compute='_compute_application_count')
    my_application_state = fields.Selection([
        ('none', 'Отклика нет'),
        ('applied', 'Вы откликнулись'),
        ('invited', 'Вас пригласили'),
        ('declined', 'Отклик отклонён'),
    ], string='Мой отклик', compute='_compute_my_application')
    is_mine = fields.Boolean(string='Моя вакансия', compute='_compute_my_application')

    # Связь со штатным наймом Odoo: организация, оформляющая человека по трудовому
    # договору, ведёт кандидатов там, где для этого всё есть.
    hr_job_id = fields.Many2one(
        'hr.job', string='Позиция в наборе', readonly=True, copy=False,
        help='Создаётся при переносе вакансии в модуль «Найм». Отклики '
             'платформы после переноса попадают туда кандидатами.')

    import_key = fields.Char(string='Ключ источника', index=True, copy=False)

    @api.depends('partner_id.coop_labour_pay', 'partner_id.coop_legal_form_id.is_cooperative')
    def _compute_labour_pay(self):
        # Выбор, уже сделанный кооперативом, не сбрасывается, пока он
        # допустим для того, кто ищет; иначе — форма по умолчанию.
        for record in self:
            partner = record.partner_id
            if not partner:
                record.labour_pay = 'rub'
            elif record.labour_pay not in partner._coop_labour_pay_allowed():
                record.labour_pay = partner.coop_labour_pay or 'rub'

    @api.depends('partner_id.coop_legal_form_id.is_cooperative')
    @api.depends('labour_pay')
    def _compute_labour_pay_choice(self):
        for record in self:
            choice = bool(record.partner_id.coop_legal_form_id.is_cooperative)
            record.labour_pay_choice = choice
            record.labour_pay_note = (
                _('Наёмный сотрудник по трудовому договору: с выплаты возникает налог.')
                if choice and record.labour_pay == 'rub' else False)

    @api.constrains('labour_pay', 'partner_id')
    def _check_labour_pay(self):
        names = dict(LABOUR_PAY)
        for record in self:
            if not record.partner_id or not record.labour_pay:
                continue
            allowed = record.partner_id._coop_labour_pay_allowed()
            if record.labour_pay not in allowed:
                raise UserError(_(
                    '«%(who)s» не может платить так: %(how)s. Допустимо: %(ok)s.',
                    who=record.partner_id.display_name,
                    how=names[record.labour_pay].lower(),
                    ok=', '.join(names[a].lower() for a in allowed)))

    @api.depends('contribution_value', 'project_id.coop_contribution_total')
    def _compute_share_percent(self):
        for record in self:
            total = record.project_id.coop_contribution_total if record.project_id else 0
            if record.contribution_value and total:
                record.share_percent = round(
                    record.contribution_value / total * 100, 2)
            else:
                record.share_percent = 0

    @api.depends('reward_kind', 'pay_from', 'pay_to', 'pay_period',
                 'share_percent', 'contribution_value', 'currency_id', 'labour_pay',
                 'partner_id.coop_legal_form_id.is_cooperative')
    def _compute_reward_display(self):
        periods = {'month': 'в месяц', 'shift': 'за смену', 'hour': 'в час',
                   'job': 'за работу', 'lesson': 'за занятие'}
        for record in self:
            parts = []
            symbol = record.currency_id.symbol or '₽'

            if record.pay_from or record.pay_to:
                money = _format_range(record.pay_from, record.pay_to, symbol)
                period = periods.get(record.pay_period, '')
                # Кооператив платит зачислением в пай, ДАО — токенами
                # (решение 416): сумма та же, форма другая, и видно её
                # должно быть прямо в строке каталога.
                how = LABOUR_PAY_SUFFIX.get(record.labour_pay, '')
                # Рубли у кооператива — это трудовой договор с налогом
                # (решение 424), и соискатель должен видеть это сразу.
                if (record.labour_pay == 'rub'
                        and record.partner_id.coop_legal_form_id.is_cooperative):
                    how = 'по трудовому договору'
                line = ('%s %s' % (money, period)).strip()
                parts.append('%s, %s' % (line, how) if how else line)

            if record.reward_kind == 'share':
                if record.share_percent:
                    parts.insert(0, 'доля в проекте %g%%' % record.share_percent)
                elif record.contribution_value:
                    # Сумма вкладов проекта неизвестна — показываем оценку
                    # вклада, а не выдуманный процент.
                    parts.insert(0, 'доля от вклада %s' % _format_range(
                        record.contribution_value, 0, symbol))
                else:
                    parts.insert(0, 'доля в проекте')
            elif record.reward_kind == 'barter':
                parts.append('обмен услугами')
            elif record.reward_kind == 'volunteer':
                parts.append('волонтёрство')

            record.reward_display = ' + '.join(p for p in parts if p) or 'по договорённости'

    @api.depends('application_ids')
    def _compute_application_count(self):
        for record in self:
            record.application_count = len(record.application_ids)

    def _compute_my_application(self):
        me = self.env.user.partner_id
        for record in self:
            record.is_mine = record.partner_id == me
            application = record.application_ids.filtered(
                lambda a: a.partner_id == me)[:1]
            record.my_application_state = application.state if application else 'none'

    # ── Действия ─────────────────────────────────────────────────────────

    def action_publish(self):
        """Опубликовать вакансию.

        Только с подтверждённой личностью (решение владельца от
        2026-09-01). Это отсекает пустые объявления: человек, готовый
        подтвердить, кто он, реже размещает вакансию просто так.

        Организации проверяются наравне с людьми. Раньше они пропускались
        целиком — «и не организация» в условии, — и вакансию от лица
        непроверенного юрлица можно было опубликовать беспрепятственно.
        Организация подтверждается своим способом: ИНН и ОГРН сверены с
        реестром.
        """
        for record in self:
            record.partner_id.coop_require_level(
                'identity', _('разместить вакансию'))
            record.state = 'published'
        return True

    def action_close(self):
        self.write({'state': 'closed'})
        return True

    def action_apply(self):
        """Открыть окно отклика.

        Отклик спрашивает пару слов о себе — решение владельца от
        15 сентября 2026. Раньше нажатие отправляло пустую запись, и у
        нанимателя в списке рядом с «Возьмусь: бухгалтер на первичку по
        проекту» стояли строки без единого слова: выбирать между ними
        было не по чему. Поле необязательное — отклик без письма
        по-прежнему уходит, но теперь это выбор человека, а не устройство
        кнопки.
        """
        self.ensure_one()
        self._check_can_apply()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Отклик на «%s»') % self.name,
            'res_model': 'coop.vacancy.apply',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_vacancy_id': self.id},
        }

    def _check_can_apply(self):
        """Условия отклика — до окна, а не после.

        Проверять их при отправке значило бы дать человеку написать
        письмо и отказать ему уже с текстом на руках.
        """
        self.ensure_one()
        if self.state != 'published':
            raise UserError(_('Откликнуться можно только на опубликованную вакансию.'))
        me = self.env.user.partner_id
        if me == self.partner_id:
            raise UserError(_('Нельзя откликнуться на собственную вакансию.'))
        if self.application_ids.filtered(lambda a: a.partner_id == me):
            raise UserError(_('Вы уже откликнулись на эту вакансию.'))

    def _do_apply(self, message=None):
        """Завести отклик. Вызывается из окна отклика."""
        self.ensure_one()
        self._check_can_apply()
        me = self.env.user.partner_id
        self.env['coop.vacancy.application'].sudo().create({
            'vacancy_id': self.id,
            'partner_id': me.id,
            'message': message or False,
        })
        # Через sudo, как и в приглашении: запись в ленту — след уже
        # состоявшегося отклика, а не правка вакансии. Вакансия чужая,
        # права писать в неё у откликающегося нет, и без sudo весь отклик
        # падал отказом «Тип документа: Message, Операция: create» —
        # кнопка «Откликнуться» не работала ни на одной вакансии.
        self.sudo().message_post(body=_('Отклик: %s') % me.display_name)
        # Наниматель узнаёт об отклике сам, а не заглянув в вакансию.
        # У вакансии проекта решает не только её автор, поэтому извещаем
        # тех же, кто вправе утвердить.
        self.env['coop.notification']._notify(
            self.partner_id | self._need_deciders(),
            _('Отклик на вашу вакансию «%(lot)s» — %(who)s.',
              lot=self.name, who=me.display_name),
            record=self, kind='vacancy')
        return True

    def action_open_applications(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Отклики: %s') % self.name,
            'res_model': 'coop.vacancy.application',
            'view_mode': 'list,form',
            'domain': [('vacancy_id', '=', self.id)],
            'context': {'default_vacancy_id': self.id},
        }

    def action_to_recruitment(self):
        """Перенести вакансию в штатный модуль «Найм».

        Нужно там, где организация оформляет человека по трудовому
        договору: в «Найме» есть этапы отбора, собеседования и переход в
        сотрудника — всё то, что на платформе воспроизводить незачем.

        Вакансия при этом остаётся в каталоге: платформа показывает
        предложение, а кадровый процесс идёт своим чередом.
        """
        self.ensure_one()
        if self.hr_job_id:
            return self._open_hr_job()
        job = self.env['hr.job'].create({
            'name': self.name,
            'description': self.description,
            'no_of_recruitment': 1,
        })
        self.hr_job_id = job.id
        # Уже поданные отклики переносятся кандидатами: иначе организация
        # начинает набор с пустого списка, хотя люди уже откликнулись.
        for application in self.application_ids.filtered(
                lambda a: a.state in ('applied', 'invited')):
            application._create_hr_applicant()
        self.message_post(body=_('Вакансия перенесена в набор персонала.'))
        return self._open_hr_job()

    def _open_hr_job(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.job',
            'res_id': self.hr_job_id.id,
            'view_mode': 'form',
        }


class CoopVacancyApplication(models.Model):
    """Отклик на вакансию.

    Отдельной записью, а не перепиской: у отклика есть состояние и дата,
    и по отклонённым видно, кому уже отказали. Без этого тот, кто ищет,
    каждый раз выбирает вслепую, а откликнувшийся не понимает, ждать ему
    или нет.
    """
    _name = 'coop.vacancy.application'
    _description = 'Отклик на вакансию'
    _order = 'create_date desc'

    vacancy_id = fields.Many2one(
        'coop.vacancy', string='Вакансия', required=True,
        ondelete='cascade', index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Кто откликнулся', required=True,
        ondelete='cascade', index=True)
    message = fields.Text(string='Сопроводительное письмо')
    state = fields.Selection([
        ('applied', 'Подан'),
        ('invited', 'Приглашён'),
        ('declined', 'Отклонён'),
    ], string='Состояние', default='applied', required=True, index=True)
    hr_applicant_id = fields.Many2one(
        'hr.applicant', string='Кандидат в наборе', readonly=True, copy=False)

    can_decide = fields.Boolean(
        string='Решать мне', compute='_compute_can_decide',
        help='Наниматель по этой вакансии: ему видны «Пригласить» и '
             '«Отклонить», откликнувшемуся — нет.')

    _one_per_vacancy = models.Constraint(
        'unique(vacancy_id, partner_id)',
        'Вы уже откликнулись на эту вакансию.',
    )

    @api.depends('vacancy_id.partner_id', 'vacancy_id.need_manager_id')
    def _compute_can_decide(self):
        """Кто решает по отклику.

        Те же двое, что и в правиле доступа: автор вакансии и
        ответственный за потребность проекта. Список держится в одном
        месте с правилом намеренно — разойдись они, и человек увидел бы
        кнопку, которая отвечает отказом в доступе.
        """
        mine = self.env.user.coop_actor_partner_ids
        for record in self:
            vacancy = record.vacancy_id
            record.can_decide = bool(
                vacancy.partner_id in mine
                or vacancy.need_manager_id in mine)

    @api.depends('vacancy_id.name', 'partner_id.display_name')
    def _compute_display_name(self):
        """Отклик читается как «вакансия — кто», а не как номер.

        Без этого модель без своего названия показывалась номером записи,
        и список откликов выглядел столбцом из 861, 865, 573 — по нему
        нельзя было понять даже, на что откликался.
        """
        for record in self:
            record.display_name = '%s — %s' % (
                record.vacancy_id.name or _('Вакансия'),
                record.partner_id.display_name or '')

    def action_invite(self):
        for record in self:
            record.state = 'invited'
            # Запись в ленту — след уже сделанного приглашения, а не
            # правка вакансии. Права на саму вакансию у приглашающего
            # может не быть: у вакансии проекта отклики утверждает
            # ответственный за потребность, а вакансия принадлежит
            # проекту, и без sudo приглашение падало отказом в доступе.
            record.vacancy_id.sudo().message_post(body=_(
                'Приглашён: %s') % record.partner_id.display_name)
            # Приглашение без извещения — это приглашение, о котором
            # приглашённый не знает: состояние отклика он увидел бы,
            # только зайдя в «Мои отклики» по своей воле.
            self.env['coop.notification']._notify(
                record.partner_id,
                _('Вас пригласили по вакансии «%s».') % record.vacancy_id.name,
                record=record.vacancy_id, kind='vacancy')
            if record.vacancy_id.hr_job_id:
                record._create_hr_applicant()
        return True

    def action_decline(self):
        self.write({'state': 'declined'})
        for record in self:
            # Отказ извещают так же, как приглашение: не зная об отказе,
            # человек ждёт ответа и не ищет другую работу.
            self.env['coop.notification']._notify(
                record.partner_id,
                _('По вакансии «%s» выбрали другого исполнителя.')
                % record.vacancy_id.name,
                record=record.vacancy_id, kind='vacancy')
        return True

    def _create_hr_applicant(self):
        """Завести кандидата в штатном наборе."""
        self.ensure_one()
        if self.hr_applicant_id or not self.vacancy_id.hr_job_id:
            return
        self.hr_applicant_id = self.env['hr.applicant'].create({
            'partner_name': self.partner_id.display_name,
            'partner_id': self.partner_id.id,
            'job_id': self.vacancy_id.hr_job_id.id,
            'email_from': self.partner_id.email,
            'description': self.message,
        }).id


def _format_range(low, high, symbol):
    """Диапазон суммы: «60 000 – 90 000 ₽» или «от 60 000 ₽»."""
    def money(value):
        return '{:,.0f}'.format(value).replace(',', ' ')

    if low and high and high != low:
        return '%s – %s %s' % (money(low), money(high), symbol)
    value = high or low
    return '%s %s' % (money(value), symbol) if value else ''
