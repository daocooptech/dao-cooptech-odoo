# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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
    _inherit = ['mail.thread', 'mail.activity.mixin']
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
                 'share_percent', 'contribution_value', 'currency_id')
    def _compute_reward_display(self):
        periods = {'month': 'в месяц', 'shift': 'за смену', 'hour': 'в час',
                   'job': 'за работу', 'lesson': 'за занятие'}
        for record in self:
            parts = []
            symbol = record.currency_id.symbol or '₽'

            if record.pay_from or record.pay_to:
                money = _format_range(record.pay_from, record.pay_to, symbol)
                period = periods.get(record.pay_period, '')
                parts.append(('%s %s' % (money, period)).strip())

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
        """Откликнуться на вакансию."""
        self.ensure_one()
        if self.state != 'published':
            raise UserError(_('Откликнуться можно только на опубликованную вакансию.'))
        me = self.env.user.partner_id
        if me == self.partner_id:
            raise UserError(_('Нельзя откликнуться на собственную вакансию.'))
        if self.application_ids.filtered(lambda a: a.partner_id == me):
            raise UserError(_('Вы уже откликнулись на эту вакансию.'))
        self.env['coop.vacancy.application'].sudo().create({
            'vacancy_id': self.id,
            'partner_id': me.id,
        })
        self.message_post(body=_('Отклик: %s') % me.display_name)
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

    _one_per_vacancy = models.Constraint(
        'unique(vacancy_id, partner_id)',
        'Вы уже откликнулись на эту вакансию.',
    )

    def action_invite(self):
        for record in self:
            record.state = 'invited'
            record.vacancy_id.message_post(body=_(
                'Приглашён: %s') % record.partner_id.display_name)
            if record.vacancy_id.hr_job_id:
                record._create_hr_applicant()
        return True

    def action_decline(self):
        self.write({'state': 'declined'})
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


class ProjectProject(models.Model):
    """Сумма вкладов проекта — то, от чего считается доля.

    Поле заводится здесь, а не в разделе проектов, потому что нужно уже
    сейчас: без него доля исполнителя в вакансии не считается ни от чего.
    Когда дойдёт очередь до раздела проектов, сумма станет вычисляемой из
    самих вкладов, а поле останется тем же.
    """
    _inherit = 'project.project'

    coop_contribution_total = fields.Monetary(
        string='Сумма вкладов, ₽', currency_field='currency_id',
        help='Денежная оценка всех вкладов в проект: деньгами, ресурсами и '
             'трудом. От неё считается доля каждого участника.')
    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        default=lambda self: self.env.company.currency_id)


def _format_range(low, high, symbol):
    """Диапазон суммы: «60 000 – 90 000 ₽» или «от 60 000 ₽»."""
    def money(value):
        return '{:,.0f}'.format(value).replace(',', ' ')

    if low and high and high != low:
        return '%s – %s %s' % (money(low), money(high), symbol)
    value = high or low
    return '%s %s' % (money(value), symbol) if value else ''
