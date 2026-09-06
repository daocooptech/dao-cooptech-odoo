# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


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

    def action_setup_share_rates(self):
        """Завести ставки по умолчанию.

        Труд идёт с повышающим коэффициентом не по нашей прихоти: это
        кооперативный принцип — распределение по труду, а не по капиталу.
        Проект вправе поменять ставки до первого принятого вклада; после
        менять их нельзя, иначе доли уже вошедших пересчитаются задним
        числом.
        """
        Rate = self.env['coop.project.share.rate']
        defaults = [
            ('labour', 1.5),
            ('knowledge', 1.3),
            ('resource', 1.0),
            ('material', 1.0),
            ('space', 1.0),
            ('money', 1.0),
        ]
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
        rate = self.project_id.share_rate_ids.filtered(
            lambda r: r.kind == self.kind)[:1]
        if not rate:
            self.project_id.action_setup_share_rates()
            rate = self.project_id.share_rate_ids.filtered(
                lambda r: r.kind == self.kind)[:1]
        factor = rate.factor if rate else 1.0
        self.write({
            'share_tokens': self.value * factor,
            'share_factor_used': factor,
        })
        self.project_id.message_post(body=_(
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
