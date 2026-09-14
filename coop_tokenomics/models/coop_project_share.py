# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CoopProject(models.Model):
    """Проект как эмитент долей.

    Один проект — один jetton-мастер. Токен доли выпускается не при
    создании проекта и не по решению кого-то одного, а в момент, когда
    вклад **приняли**: до принятия оценка вклада — это предложение, и
    выпускать под неё нечего.

    Обязательство проекта — не отдельная запись, а сами выпущенные доли:
    сколько токенов на руках у участников, столько проект и должен. Заводить
    рядом ещё и реестр обязательств значило бы держать две правды об одном,
    которые разойдутся в первый же спорный случай.
    """
    _inherit = 'coop.project'

    share_jetton_address = fields.Char(
        string='Адрес токена долей', readonly=True, copy=False, index=True,
        help='Jetton-мастер проекта в сети TON. Пока пусто — доли ведутся '
             'только в базе.')
    share_network = fields.Selection([
        ('testnet', 'Тестовая сеть'),
        ('mainnet', 'Основная сеть'),
    ], string='Сеть', default='testnet', copy=False)

    share_rate_ids = fields.One2many(
        'coop.project.share.rate', 'project_id', string='Ставки по видам вклада')
    share_rates_frozen = fields.Boolean(
        string='Ставки заморожены', compute='_compute_share_rates_frozen',
        help='С первым принятым вкладом ставки перестают меняться: доли '
             'тех, кто вошёл раньше, пересчитались бы задним числом.')

    @api.depends('contribution_ids.state')
    def _compute_share_rates_frozen(self):
        for record in self:
            record.share_rates_frozen = bool(record.contribution_ids.filtered(
                lambda c: c.state == 'accepted'))
    share_total = fields.Float(
        string='Долей выпущено', compute='_compute_share_total', store=True,
        digits=(16, 3),
        help='Сумма долей на руках участников. Она же — обязательство '
             'проекта перед ними.')

    @api.depends('contribution_ids.share_tokens', 'contribution_ids.state')
    def _compute_share_total(self):
        for record in self:
            record.share_total = sum(record.contribution_ids.filtered(
                lambda c: c.state == 'accepted').mapped('share_tokens'))

    # Коэффициент — плата за невозвратность, а не за «ценность».
    #
    # Прежнее обоснование («труд ценнее капитала») не выдерживало первого
    # спора: если час оценён справедливо в рублях, множитель учитывает
    # труд дважды, а если ставка занижена — чинить надо ставку. Решение
    # владельца 294 от 14 сентября 2026 меняет основание.
    #
    # Вклады различаются тем, что с ними происходит при провале: деньги
    # возвращаются целиком, техника с износом, помещение занято впустую,
    # материалы израсходованы, труд не возвращается ничем и никогда. Кто
    # внёс невозвратное, на ту же рублёвую сумму несёт больший риск —
    # коэффициент и есть премия за этот риск.
    #
    # Отсюда правило порядка, которое можно оспорить по существу: чем
    # меньше возвращается при провале, тем выше коэффициент.
    DEFAULT_RATES = [
        ('labour', 1.5),      # не возвращается вовсе
        ('material', 1.3),    # израсходованы безвозвратно
        ('knowledge', 1.3),   # создано под проект
        ('space', 1.15),      # объект остаётся, но занят
        ('resource', 1.1),    # возвращается с износом
        ('money', 1.0),       # точка отсчёта
    ]

    def action_setup_share_rates(self):
        """Завести ставки по умолчанию.

        Проект вправе поменять ставки до первого принятого вклада; после
        менять их нельзя, иначе доли уже вошедших пересчитаются задним
        числом.
        """
        Rate = self.env['coop.project.share.rate']
        defaults = self.DEFAULT_RATES
        for record in self:
            if record.share_rate_ids:
                continue
            for kind, factor in defaults:
                Rate.create({
                    'project_id': record.id,
                    'kind': kind,
                    'factor': factor,
                })
        return True


class CoopProjectShareRate(models.Model):
    """Ставка выпуска долей по виду вклада.

    Доля считается не от рублей напрямую, а от рублей с коэффициентом по
    виду вклада: тысяча рублей деньгами и тысяча рублей труда — это разный
    вклад в кооперативный проект, и уравнивать их значит превращать
    кооперацию в складчину капитала.

    Коэффициент, а не отдельная шкала для каждого вида: денежная оценка
    вклада уже есть в `coop_projects` и сводит несводимое — час
    экскаваторщика и лист фанеры. Второй такой механизм рядом был бы
    лишним.
    """
    _name = 'coop.project.share.rate'
    _description = 'Ставка выпуска долей'
    _order = 'project_id, kind'

    project_id = fields.Many2one(
        'coop.project', string='Проект', required=True, index=True,
        ondelete='cascade')
    kind = fields.Selection([
        ('money', 'Деньги'),
        ('labour', 'Труд'),
        ('resource', 'Ресурс или техника'),
        ('material', 'Материалы'),
        ('space', 'Помещение'),
        ('knowledge', 'Знания и документация'),
    ], string='Вид вклада', required=True)
    factor = fields.Float(
        string='Коэффициент', required=True, default=1.0, digits=(8, 3),
        help='На сколько умножается денежная оценка вклада при выпуске '
             'долей. 1,5 у труда значит, что тысяча рублей труда даёт '
             'полторы тысячи долей.')

    _one_rate_per_kind = models.Constraint(
        'unique(project_id, kind)',
        'На один вид вклада в проекте — одна ставка.',
    )
    # Нижняя граница — не придирка. Без неё через коэффициент можно
    # наказать неугодный вид вклада, обнулив чей-то труд решением
    # инициатора. Верхняя — чтобы премия за риск не превращалась в
    # способ отдать проект одному человеку.
    def _check_not_frozen(self):
        """Ставки заморожены с первым принятым вкладом.

        Это правило было записано в пояснении к модели и нигде не
        проверялось: менять коэффициент мог кто угодно и когда угодно, а
        доли уже вошедших пересчитывались бы задним числом. Сам по себе
        текст в подсказке ничего не запрещает.

        Оговорка для наполнения: весь демонстрационный каталог порождён
        загрузчиком, и когда владелец меняет шкалу, он меняет её и в
        наполнении. Загрузчик проходит с пометкой в контексте — сюда
        она попадает только оттуда.
        """
        if self.env.context.get('coop_rescale_demo'):
            return
        for record in self:
            accepted = record.project_id.contribution_ids.filtered(
                lambda c: c.state == 'accepted')
            if accepted:
                raise UserError(_(
                    'В проекте «%(name)s» уже есть принятые вклады '
                    '(%(count)s). Менять коэффициенты нельзя: доли тех, '
                    'кто вошёл раньше, пересчитались бы задним числом.',
                    name=record.project_id.name, count=len(accepted)))

    def write(self, vals):
        self._check_not_frozen()
        return super().write(vals)

    def unlink(self):
        self._check_not_frozen()
        return super().unlink()

    @api.constrains('kind', 'factor')
    def _check_money_is_the_baseline(self):
        """Деньги — точка отсчёта, её нельзя двигать.

        Коэффициент значит «во сколько раз этот вклад невозвратнее
        денег». Сдвинуть сами деньги — всё равно что менять длину метра:
        остальные значения перестают что-либо означать.
        """
        for record in self:
            if record.kind == 'money' and round(record.factor, 3) != 1.0:
                raise ValidationError(_(
                    'Коэффициент денег — всегда ровно 1,0: от него '
                    'отсчитываются остальные. Если деньги в этом проекте '
                    'должны весить меньше труда, поднимайте коэффициент '
                    'труда, а не опускайте денежный.'))

    _factor_in_range = models.Constraint(
        'check(factor >= 1.0 and factor <= 2.0)',
        'Коэффициент — от 1,0 до 2,0. Ниже единицы он наказывает вид '
        'вклада, выше двух — отдаёт проект одному вкладчику.',
    )
    _factor_positive = models.Constraint(
        'check(factor > 0)',
        'Коэффициент должен быть больше нуля.',
    )


class CoopProjectContribution(models.Model):
    """Вклад, порождающий доли.

    Принятие вклада — это встречное движение: участник отдал труд или
    технику, проект признал это и обязался долей. Обе стороны фиксируются
    одним действием, потому что порознь они бессмысленны — доля без
    признанного вклада ничем не обеспечена, а признанный вклад без доли
    оставляет вкладчика ни с чем.
    """
    _inherit = 'coop.project.contribution'

    share_tokens = fields.Float(
        string='Долей начислено', readonly=True, digits=(16, 3), copy=False,
        help='Оценка вклада, умноженная на коэффициент вида. Считается один '
             'раз при принятии и потом не пересчитывается: доля, которая '
             'меняется задним числом, — не доля.')
    share_factor_used = fields.Float(
        string='Коэффициент при начислении', readonly=True, digits=(8, 3),
        copy=False,
        help='Сохраняется отдельно, чтобы через год было видно, по какой '
             'ставке начислялось, даже если проект её с тех пор менял.')
    share_minted = fields.Boolean(
        string='Доли выпущены в сеть', readonly=True, copy=False)
    share_mint_tx = fields.Char(string='Транзакция выпуска', readonly=True, copy=False)

    @api.depends('share_tokens', 'state', 'project_id.share_total')
    def _compute_share_percent(self):
        """Доля считается от начисленных долей, а не от рублей.

        Правд было две, и они расходились у 684 принятых вкладов из 921:
        карточка проекта показывала долю от рублей, реестр долей жил по
        начисленным долям. Спор вкладчика с проектом сводился бы к тому,
        какое из чисел настоящее, а настоящих было два.

        Настоящее — одно, по долям (решение владельца 294). Рублёвая
        сумма остаётся ответом на другой вопрос — «сколько собрано», и
        от неё по-прежнему считается готовность.

        Если коэффициентов у проекта нет (все ставки 1,0 или модуль
        токеномики не установлен), формула вырождается в прежнюю: доли
        равны рублям, и доля по долям равна доле по рублям.
        """
        with_tokens = self.filtered(lambda c: c.project_id.share_total)
        for record in with_tokens:
            if record.state == 'accepted':
                record.share_percent = round(
                    record.share_tokens / record.project_id.share_total * 100, 2)
            else:
                record.share_percent = 0
        # Проекты без выпущенных долей считает исходная формула из
        # `coop_projects`: модуль токеномики может стоять, а проект —
        # ещё не начислять.
        super(CoopProjectContribution, self - with_tokens)._compute_share_percent()

    @api.model_create_multi
    def create(self, vals_list):
        """Вклад, заведённый сразу принятым, тоже получает доли.

        Начисление висело только на кнопке «Принять». А вклад попадает в
        базу и мимо неё — переносом, загрузчиком, утверждённым откликом
        на вакансию. Такие оставались с нулём долей и пустым
        коэффициентом, и в карточке у человека выходило «×0»:
        признанный вклад без доли, то есть ровно то, чего эта модель не
        должна допускать.
        """
        records = super().create(vals_list)
        for record in records.filtered(
                lambda c: c.state == 'accepted' and not c.share_tokens):
            record._grant_shares()
        return records

    def action_accept(self):
        """Принять вклад и начислить доли тем же движением."""
        result = super().action_accept()
        for record in self.filtered(lambda c: c.state == 'accepted'):
            record._grant_shares()
        return result

    def _grant_shares(self):
        """Начислить доли по формуле вида вклада.

        Повторно не начисляет: вклад можно принять один раз, а доли —
        выпустить один раз под него. Иначе достаточно было бы нажать
        «принять» дважды.
        """
        self.ensure_one()
        if self.share_tokens:
            return
        # Начисление — следствие уже принятого вклада, а не отдельное
        # решение: право принимать проверено в `action_accept`. Прав на
        # сам проект у принявшего может не быть — ответственный за
        # потребность и представитель организации с полномочием на
        # сделки утверждают по существу, а править проект не вправе, и
        # без sudo начисление падало отказом в доступе на чтении ставок
        # и на записи в ленту.
        project = self.project_id.sudo()
        rate = project.share_rate_ids.filtered(
            lambda r: r.kind == self.kind)[:1]
        if not rate:
            project.action_setup_share_rates()
            rate = project.share_rate_ids.filtered(
                lambda r: r.kind == self.kind)[:1]
        factor = rate.factor if rate else 1.0
        self.sudo().write({
            'share_tokens': self.value * factor,
            'share_factor_used': factor,
        })
        project.message_post(body=_(
            'Вклад «%(what)s» принят: %(who)s начислено %(tokens)g долей '
            '(оценка %(value)s × %(factor)g). У проекта возникло встречное '
            'обязательство перед вкладчиком на эту долю.',
            what=self.name, who=self.partner_id.name,
            tokens=self.share_tokens, value=self.value, factor=factor,
        ))

    def action_mint_shares(self):
        """Выпустить начисленные доли в сеть.

        Отдельным действием, а не вместе с принятием: сеть может быть
        недоступна, кошелёк вкладчика — не подключён, а принятие вклада от
        этого зависеть не должно. Доли уже начислены и учтены; выпуск в
        сеть делает их переносимыми.
        """
        for record in self:
            if not record.share_tokens:
                raise UserError(_('По вкладу не начислено долей.'))
            if record.share_minted:
                raise UserError(_('Доли по этому вкладу уже выпущены.'))
            if not record.partner_id.coop_ton_address:
                raise UserError(_(
                    'У вкладчика не подключён кошелёк TON — некуда '
                    'зачислять доли.'))
            record.share_minted = True
        return True
