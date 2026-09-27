# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Как оформляется и чем оплачивается труд.
#
# Решение 416, п. 2 (26.09.2026): «ООО — рубли, кооператив — пай, ДАО —
# токены». Поправка 424: кооператив платит и паем, и деньгами, деньгами — с
# налогом. Решение 425 (27.09.2026, по заключению юриста — Матчасть,
# «Вознаграждение за труд в кооперативе — рубли, ГПХ, пай»): «в пай» как
# форма зарплаты, назначенная работодателем, незаконна в любом кооперативе
# (ст. 131 ТК). Поэтому у вакансии два поля. Договор — трудовой, подряд или
# услуги, трудовое участие члена артели (только производственный
# кооператив). Способ выплаты — деньгами; деньгами, а остаток после налога
# пайщик по своему заявлению вносит в пай (кооператив, договор подряда);
# долей дохода по трудовому участию (артель); токенами (ДАО).
CONTRACTS = [
    ('labour', 'Трудовой договор'),
    ('civil', 'Договор подряда или услуг'),
    ('artel', 'Трудовое участие в артели'),
]
PAY_METHODS = [
    ('rub', 'Деньгами'),
    ('rub_share', 'Деньгами, остаток — в пай по желанию пайщика'),
    ('artel', 'Доля дохода по трудовому участию'),
    ('tokens', 'Токенами'),
]
# Форма ДАО в справочнике помечена кооперативной, поэтому проверяется
# первой: иначе вакансии ДАО получали кооперативный способ выплаты.
TOKEN_FORMS = ('dao', 'platform')
# Трудовое участие без трудового договора — только у производственного
# кооператива (ст. 106.1 ГК, 41-ФЗ, ст. 40 193-ФЗ).
PRODUCTION_FORMS = ('pk', 'spk', 'artel')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _coop_employer_kind(self):
        """Кто нанимает: dao, production, coop или other."""
        self.ensure_one()
        form = self.coop_legal_form_id
        if form.code in TOKEN_FORMS:
            return 'dao'
        if form.code in PRODUCTION_FORMS:
            return 'production'
        if form.is_cooperative:
            return 'coop'
        return 'other'

    def _coop_contracts_allowed(self):
        """Какие договоры открыты работодателю.

        ДАО платит токенами — только по договору подряда: зарплата по
        трудовому договору выплачивается рублями (ст. 131 ТК).
        """
        kind = self._coop_employer_kind()
        if kind == 'dao':
            return ('civil',)
        if kind == 'production':
            return ('labour', 'civil', 'artel')
        return ('labour', 'civil')

    def _coop_pay_methods_allowed(self, contract):
        kind = self._coop_employer_kind()
        if kind == 'dao':
            return ('tokens',)
        if contract == 'artel':
            return ('artel',)
        if contract == 'civil' and kind in ('coop', 'production'):
            return ('rub', 'rub_share')
        return ('rub',)


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
    # Решение 425: договор и способ выплаты выбирает работодатель, соискатель
    # видит их до отклика. По умолчанию — от вида занятости и того, кто ищет.
    contract_kind = fields.Selection(
        CONTRACTS, string='Договор', compute='_compute_contract_kind',
        store=True, readonly=False, index=True,
        help='Постоянная должность — трудовой договор, разовая работа с '
             'результатом — подряд или услуги. Трудовое участие без трудового '
             'договора — только для членов производственного кооператива '
             '(артели).')
    pay_method = fields.Selection(
        PAY_METHODS, string='Как выплачивается', compute='_compute_pay_method',
        store=True, readonly=False, index=True,
        help='Зарплата по трудовому договору — только деньгами. По договору '
             'подряда с кооперативом пайщик может своим заявлением внести '
             'сумму после налога в дополнительный паевой взнос. Артель платит '
             'долю дохода по трудовому участию, ДАО — токенами.')
    employer_kind = fields.Selection([
        ('dao', 'ДАО'),
        ('production', 'Производственный кооператив'),
        ('coop', 'Кооператив'),
        ('other', 'Прочие'),
    ], string='Кто нанимает', compute='_compute_employer_kind')
    pay_explain = fields.Char(
        string='Что это значит', compute='_compute_pay_explain',
        help='Пояснение для соискателя: что даёт этот договор и что с налогом.')

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

    def _pay_applies(self):
        """Договор и выплата есть у работы за вознаграждение, не у волонтёрства."""
        self.ensure_one()
        return self.reward_kind in ('money', 'share') and self.employment != 'volunteer'

    @api.depends('partner_id.coop_legal_form_id', 'employment', 'reward_kind')
    def _compute_contract_kind(self):
        # Выбор работодателя не сбрасывается, пока он допустим.
        for record in self:
            if not record.partner_id or not record._pay_applies():
                record.contract_kind = False
                continue
            allowed = record.partner_id._coop_contracts_allowed()
            if record.contract_kind in allowed:
                continue
            if 'labour' in allowed and record.employment in ('full', 'part'):
                record.contract_kind = 'labour'
            else:
                record.contract_kind = 'civil'

    @api.depends('contract_kind', 'partner_id.coop_legal_form_id')
    def _compute_pay_method(self):
        for record in self:
            if not record.contract_kind:
                record.pay_method = False
                continue
            allowed = record.partner_id._coop_pay_methods_allowed(record.contract_kind)
            if record.pay_method not in allowed:
                record.pay_method = allowed[0]

    @api.depends('partner_id.coop_legal_form_id')
    def _compute_employer_kind(self):
        for record in self:
            record.employer_kind = (record.partner_id._coop_employer_kind()
                                    if record.partner_id else 'other')

    @api.depends('contract_kind', 'pay_method', 'partner_id.coop_legal_form_id')
    def _compute_pay_explain(self):
        # Формулировки — из заключения юриста 27.09, разд. 4.2.
        for record in self:
            contract, pay = record.contract_kind, record.pay_method
            text = False
            if contract == 'labour':
                text = _('Оформление по Трудовому кодексу: стаж, отпуск, больничный. '
                         'НДФЛ удерживается из зарплаты, страховые взносы работодатель '
                         'платит сверх неё.')
            elif contract == 'artel':
                text = _('Работа членом артели: доход — доля прибыли по трудовому '
                         'участию, заранее не гарантирован. Нужно вступить: паевой '
                         'взнос и решение собрания. С выплат удерживается НДФЛ, '
                         'кооператив платит страховые взносы.')
                if record.partner_id.coop_legal_form_id.code == 'spk':
                    text += ' ' + _('В сельхозартели условия не хуже Трудового кодекса.')
            elif pay == 'tokens':
                text = _('Не трудовой договор: работа по заданию, оплата токенами '
                         'после приёмки.')
            elif contract == 'civil':
                text = _('Не трудовой договор: без отпуска, работа по заданию, оплата '
                         'после приёмки. Физлицу — за вычетом НДФЛ, самозанятому и ИП — '
                         'полной суммой, налог они платят сами.')
                if pay == 'rub_share':
                    text += ' ' + _('Пайщик по своему заявлению может внести сумму '
                                    'после налога в дополнительный паевой взнос — '
                                    'она вернётся при выходе из кооператива, по уставу.')
            record.pay_explain = text

    @api.constrains('contract_kind', 'pay_method', 'partner_id')
    def _check_contract_and_pay(self):
        contracts, methods = dict(CONTRACTS), dict(PAY_METHODS)
        for record in self:
            partner = record.partner_id
            if not partner:
                continue
            if record.contract_kind:
                allowed = partner._coop_contracts_allowed()
                if record.contract_kind not in allowed:
                    raise UserError(_(
                        '«%(who)s» не может нанимать так: %(what)s. Допустимо: %(ok)s.',
                        who=partner.display_name,
                        what=contracts[record.contract_kind].lower(),
                        ok=', '.join(contracts[a].lower() for a in allowed)))
            if record.pay_method:
                allowed = partner._coop_pay_methods_allowed(record.contract_kind)
                if record.pay_method not in allowed:
                    raise UserError(_(
                        'По этому договору «%(who)s» не может платить так: %(how)s. '
                        'Допустимо: %(ok)s.',
                        who=partner.display_name,
                        how=methods[record.pay_method].lower(),
                        ok=', '.join(methods[a].lower() for a in allowed)))

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
                 'share_percent', 'contribution_value', 'currency_id',
                 'contract_kind', 'pay_method')
    def _compute_reward_display(self):
        periods = {'month': 'в месяц', 'shift': 'за смену', 'hour': 'в час',
                   'job': 'за работу', 'lesson': 'за занятие'}
        for record in self:
            parts = []
            symbol = record.currency_id.symbol or '₽'

            if record.pay_from or record.pay_to:
                money = _format_range(record.pay_from, record.pay_to, symbol)
                period = periods.get(record.pay_period, '')
                line = ('%s %s' % (money, period)).strip()
                # Договор и способ выплаты — прямо в строке каталога
                # (решение 425, формулировки юриста): соискатель видит их
                # до отклика.
                contract, pay = record.contract_kind, record.pay_method
                if contract == 'labour':
                    line = '%s до вычета НДФЛ · трудовой договор' % line
                elif contract == 'artel':
                    line = 'трудовое участие в артели, ориентир %s' % line
                elif pay == 'tokens':
                    line = '%s токенами · договор подряда' % line
                elif pay == 'rub_share':
                    line = '%s · договор подряда, остаток — в пай по желанию' % line
                elif contract == 'civil':
                    line = '%s · договор подряда' % line
                parts.append(line)

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
