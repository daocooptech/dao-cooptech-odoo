# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CoopMembership(models.Model):
    """Членство человека в организации, основанной на членстве.

    Почему это отдельная модель, а не поле у контакта и не сотрудник.

    `res.partner` описывает, с кем мы имеем дело, но не отношения членства:
    у одного человека членство в трёх кооперативах сразу, у каждого свой
    устав, свой пай и свой порядок выхода. `hr.employee` описывает трудовые
    отношения — а пайщик не работник: он совладелец, и в кооперативе может
    вообще не работать.

    Роль здесь — не должность. Пайщик, правление, ревизионная комиссия и
    наёмный сотрудник различаются не подчинением, а тем, что человек вправе
    видеть и решать. Отсюда роль определяет права (см. `ir.rule` и группы),
    а не строчку в штатном расписании.
    """
    _name = 'coop.membership'
    _description = 'Членство в организации'
    _inherit = ['mail.thread']
    _order = 'joined_on desc, id desc'
    _rec_name = 'display_name'

    partner_id = fields.Many2one(
        'res.partner', string='Участник', required=True, index=True,
        ondelete='restrict', tracking=True,
        domain=[('is_company', '=', False)])
    organization_id = fields.Many2one(
        'res.partner', string='Организация', required=True, index=True,
        ondelete='restrict', tracking=True,
        domain=[('is_company', '=', True)])

    role = fields.Selection([
        ('founder', 'Учредитель'),
        ('member', 'Пайщик'),
        ('associate', 'Ассоциированный член'),
        ('board', 'Правление'),
        ('audit', 'Ревизионная комиссия'),
        ('staff', 'Наёмный сотрудник'),
        ('platform', 'Рабочая группа платформы'),
    ], string='Основание участия', required=True, default='member', tracking=True,
        help='Роль определяет, что участник вправе видеть и решать, '
             'а не его должность.\n\n'
             'Рабочая группа платформы — это не роль в кооперативе. '
             'Администратор платформы не пайщик и никаких прав в чужих '
             'кооперативах не получает: правила доступа ниже перечисляют '
             'пайщика, правление и ревизию, и его среди них нет.')

    power_ids = fields.Many2many(
        'coop.power', string='Полномочия', tracking=True,
        help='Что человеку позволено делать от имени организации. Роль '
             'отвечает на вопрос «на каком основании он здесь», полномочия — '
             '«что ему позволено»: у сотрудника отдела маркетинга нет доступа '
             'к бухгалтерии, у бухгалтера — к управлению страницей.')

    # Должность — не роль и не полномочие, а то, как человека называют в
    # организации. Держать её отдельно нужно затем, что «бухгалтер» и
    # «маркетолог» различаются набором полномочий, а не основанием
    # участия: у обоих оно одно — наёмный сотрудник.
    job_title = fields.Char(
        string='Должность',
        help='Как называется место человека в организации: бухгалтер, '
             'маркетолог, председатель. На права не влияет — права дают '
             'полномочия.')

    # Организация бывает не только кооперативом: рабочая группа платформы,
    # НКО, коммерческая компания. Группа формы нужна, чтобы не выдавать
    # кооперативные права там, где кооператива нет.
    org_group_id = fields.Many2one(
        related='organization_id.coop_legal_form_group_id', store=True,
        readonly=True, string='Группа форм организации')
    org_is_cooperative = fields.Boolean(
        related='organization_id.coop_is_cooperative', store=True,
        readonly=True, string='Кооперативная организация')

    state = fields.Selection([
        ('applied', 'Подано заявление'),
        ('active', 'Действующее'),
        ('leaving', 'Подано заявление о выходе'),
        ('ended', 'Прекращено'),
    ], string='Состояние', required=True, default='applied', tracking=True)

    joined_on = fields.Date(string='Принят', tracking=True)
    left_on = fields.Date(string='Выбыл', tracking=True)

    # Основание — не формальность: приём и исключение из кооператива
    # относятся к компетенции общего собрания, и запись без ссылки на
    # решение органа не имеет силы.
    admission_basis = fields.Char(
        string='Основание приёма',
        help='Решение общего собрания или правления: номер и дата протокола.')
    termination_basis = fields.Char(string='Основание прекращения')

    # Голос на собрании — свойство членства, а не размера пая: в кооперативе
    # один член — один голос, независимо от вклада. Поле оставлено явным,
    # чтобы это правило было видно в данных, а не подразумевалось.
    has_vote = fields.Boolean(
        string='Право голоса', default=True, tracking=True,
        help='Один член — один голос, независимо от размера пая. '
             'Наёмный сотрудник, не являющийся пайщиком, голоса не имеет.')

    display_name = fields.Char(compute='_compute_display_name', store=True)

    def _auto_init(self):
        """Одно незакрытое членство на пару «человек — организация».

        Ограничение частичное: прекращённая запись не мешает вступить
        заново, а вступить дважды одновременно нельзя. Сделано индексом, а
        не EXCLUDE-ограничением: EXCLUDE на равенство целых требует
        расширения btree_gist, которого в базе может не оказаться, и тогда
        модуль просто не установится.
        """
        res = super()._auto_init()
        tools.create_index(
            self.env.cr, 'coop_membership_open_uniq', self._table,
            ['partner_id', 'organization_id'], unique=True,
            where="state IN ('applied', 'active', 'leaving')")
        return res

    @api.depends('partner_id', 'organization_id', 'role')
    def _compute_display_name(self):
        labels = dict(self._fields['role'].selection)
        for record in self:
            if record.partner_id and record.organization_id:
                record.display_name = '%s — %s (%s)' % (
                    record.partner_id.name, record.organization_id.name,
                    labels.get(record.role, ''))
            else:
                record.display_name = ''

    @api.constrains('partner_id', 'organization_id')
    def _check_not_self(self):
        for record in self:
            if record.partner_id == record.organization_id:
                raise ValidationError('Организация не может состоять сама в себе.')

    @api.constrains('joined_on', 'left_on')
    def _check_dates(self):
        for record in self:
            if record.joined_on and record.left_on and record.left_on < record.joined_on:
                raise ValidationError('Дата выбытия раньше даты приёма.')

    @api.constrains('partner_id', 'organization_id', 'state')
    def _check_single_open_membership(self):
        """Понятное сообщение вместо ошибки базы.

        Индекс защищает от гонки двух одновременных записей, а эта
        проверка объясняет человеку, что произошло.
        """
        open_states = ('applied', 'active', 'leaving')
        for record in self:
            if record.state not in open_states:
                continue
            twin = self.search([
                ('id', '!=', record.id),
                ('partner_id', '=', record.partner_id.id),
                ('organization_id', '=', record.organization_id.id),
                ('state', 'in', open_states),
            ], limit=1)
            if twin:
                raise ValidationError(
                    'У %s уже есть незакрытое членство в «%s». Прекратите прежнее, '
                    'прежде чем заводить новое.'
                    % (record.partner_id.name, record.organization_id.name))

    @api.constrains('role', 'has_vote')
    def _check_platform_has_no_vote(self):
        """У рабочей группы платформы нет голоса в кооперативе.

        Платформа обслуживает сеть, а не участвует в ней. Как только
        оператор получает голос на собрании, он перестаёт быть оператором и
        становится стороной — ровно то, чего вся конструкция избегает.
        """
        for record in self:
            if record.role == 'platform' and record.has_vote:
                raise ValidationError(
                    'Рабочая группа платформы не имеет голоса в кооперативе: '
                    'платформа обслуживает сеть, а не участвует в ней.')

    # ── Полномочия ───────────────────────────────────────────────────────
    #
    # Набор по умолчанию — предложение, а не догма: его видно в форме и
    # можно поправить до сохранения. Смысл в том, чтобы принятый пайщик не
    # оказался без единого полномочия, а наёмный сотрудник не получил
    # ключей от кассы просто потому, что о полномочиях забыли.
    DEFAULT_POWERS = {
        'founder': ('publish', 'represent', 'deal', 'treasury', 'roster', 'powers', 'site'),
        'member': ('represent',),
        'associate': ('represent',),
        'board': ('publish', 'represent', 'deal', 'treasury', 'roster', 'powers', 'site'),
        'audit': ('audit',),
        'staff': ('represent',),
        'platform': ('represent',),
    }

    def _default_power_ids(self, role):
        codes = self.DEFAULT_POWERS.get(role, ())
        if not codes:
            return self.env['coop.power']
        return self.env['coop.power'].sudo().search([('code', 'in', list(codes))])

    @api.onchange('role')
    def _onchange_role_powers(self):
        for record in self:
            record.power_ids = [(6, 0, record._default_power_ids(record.role).ids)]

    @api.constrains('role', 'power_ids')
    def _check_audit_has_no_executive_powers(self):
        """Ревизия проверяет и не участвует в том, что проверяет.

        Иначе проверяющий подписывает сделку, а потом сам же её проверяет —
        и проверка перестаёт что-либо значить.
        """
        for record in self:
            if record.role != 'audit':
                continue
            executive = record.power_ids.filtered('is_executive')
            if executive:
                raise ValidationError(
                    'Ревизионной комиссии не выдаются исполнительные '
                    'полномочия: проверяющий не должен быть участником того, '
                    'что проверяет. Лишние: %s'
                    % ', '.join(executive.mapped('name')))

    @api.constrains('power_ids', 'organization_id', 'state')
    def _check_exclusive_powers(self):
        """Право подписи без доверенности — у одного человека.

        Двух единоличных исполнительных органов не бывает: сведения о том,
        кто действует без доверенности, в ЕГРЮЛ одни.
        """
        open_states = ('applied', 'active', 'leaving')
        for record in self:
            if record.state not in open_states:
                continue
            for power in record.power_ids.filtered('is_exclusive'):
                twin = self.search([
                    ('id', '!=', record.id),
                    ('organization_id', '=', record.organization_id.id),
                    ('power_ids', 'in', power.id),
                    ('state', 'in', open_states),
                ], limit=1)
                if twin:
                    raise ValidationError(
                        'Полномочие «%s» в организации «%s» уже есть у %s. '
                        'Отзовите прежнее, прежде чем выдавать новое.'
                        % (power.name, record.organization_id.name,
                           twin.partner_id.name))

    @api.constrains('state', 'admission_basis')
    def _check_admission_basis(self):
        """Действующее членство без основания — дыра в учёте.

        Приём в члены — решение органа управления, и если его нет, то нет и
        членства. Проверка ставится на переход в «действующее», а не на
        создание: заявление подаётся до решения.
        """
        for record in self:
            if record.state == 'active' and not record.admission_basis:
                raise ValidationError(
                    'Чтобы членство стало действующим, укажите основание приёма: '
                    'решение общего собрания или правления.')

    # ── Сброс кэша правил доступа ───────────────────────────────────────
    #
    # Правила уровня записи здесь опираются на состав членства: «правление
    # ведёт членство своей организации» — значит домен правила зависит от
    # того, где человек состоит. Odoo вычисляет домен один раз и кэширует по
    # пользователю, а сбрасывает кэш при изменении правил и групп — но не
    # при изменении наших записей.
    #
    # Без этого сброса принятый сегодня пайщик не увидит свой кооператив до
    # перезапуска сервера, а исключённый продолжит видеть чужие данные —
    # второе хуже первого. Поэтому любое изменение членства сбрасывает кэш.

    def _invalidate_rule_cache(self):
        self.env.registry.clear_cache()

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if not values.get('power_ids'):
                powers = self._default_power_ids(values.get('role') or 'member')
                values['power_ids'] = [(6, 0, powers.ids)]
        records = super().create(vals_list)
        records._invalidate_rule_cache()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {'partner_id', 'organization_id', 'role', 'state', 'power_ids'} & set(vals):
            self._invalidate_rule_cache()
        return result

    def unlink(self):
        self._invalidate_rule_cache()
        return super().unlink()

    @api.model
    def _fill_missing_powers(self):
        """Раздать полномочия членствам, заведённым до их появления.

        Иначе принятый вчера пайщик наутро не может ничего: полномочий у
        него нет, а правила доступа уже смотрят на них. Разовая операция,
        идемпотентная — членства с полномочиями не трогает.
        """
        empty = self.sudo().search([('power_ids', '=', False)])
        if not empty:
            return True
        _logger.info('Раздаю полномочия по умолчанию: %s членств', len(empty))
        for membership in empty:
            membership.power_ids = [
                (6, 0, membership._default_power_ids(membership.role).ids)]
        self.env.registry.clear_cache()
        return True

    # ── Кто решает и что видит вступающий ────────────────────────────

    def _roster_deciders(self):
        """Кому в организации позволено принимать и прекращать членство.

        Полномочие «Ведение состава» (`roster`). Если его нет ни у кого —
        организация только заведена, состава ещё нет, — извещаем тех, кто
        представляет её вовне: иначе заявление уходит в пустоту.
        """
        self.ensure_one()
        организация = self.organization_id
        действующие = self.sudo().search([
            ('organization_id', '=', организация.id),
            ('state', '=', 'active'),
        ])
        ведут = действующие.filtered(
            lambda m: 'roster' in m.power_ids.mapped('code'))
        if not ведут:
            ведут = действующие.filtered(
                lambda m: 'represent' in m.power_ids.mapped('code'))
        return ведут.mapped('partner_id') or организация

    @api.depends_context('uid')
    @api.depends('organization_id', 'state')
    def _compute_can_decide(self):
        """Тот же вопрос, что решает кнопку, и тот же, что решает отказ.

        Разойдись они — и человек увидел бы «Принять», отвечающую
        ошибкой прав.
        """
        user = self.env.user
        for record in self:
            record.can_decide = bool(
                record.organization_id
                and user.coop_has_power('roster', record.organization_id))

    can_decide = fields.Boolean(
        string='Могу решать', compute='_compute_can_decide',
        help='Есть полномочие вести состав этой организации.')

    def _notify_member(self, body):
        """Извещение вступающему. Без него он не знает ничего."""
        self.ensure_one()
        self.env['coop.notification']._notify(
            self.partner_id, body, record=self.organization_id, kind='org')

    def _check_can_decide(self):
        for record in self:
            if not record.can_decide:
                raise UserError(_(
                    'Принимать и прекращать членство в «%s» может тот, у '
                    'кого есть полномочие «Ведение состава».')
                    % record.organization_id.display_name)

    def action_open_admit(self):
        """Окно приёма: спросить основание, а не упереться в проверку.

        Приём в члены — решение органа управления, и без ссылки на него
        запись о членстве не имеет силы (`_check_admission_basis`).
        Кнопка без окна упиралась в эту проверку: человек нажимал
        «Принять» и получал ошибку вместо приёма.
        """
        self.ensure_one()
        self._check_can_decide()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Принять в «%s»') % self.organization_id.display_name,
            'res_model': 'coop.membership.admit',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_membership_id': self.id},
        }

    def action_admit(self):
        # Права на членство у участника — только чтение: состав ведёт
        # правление, и раздавать запись всем нельзя. Поэтому проверка
        # полномочия своя и явная, а запись — через sudo. Проверка идёт
        # первой: sudo без неё означал бы, что принять может кто угодно.
        self._check_can_decide()
        self.sudo().write({'state': 'active',
                           'joined_on': fields.Date.context_today(self)})
        for record in self:
            record._notify_member(_(
                'Вы приняты в «%(орг)s»: %(кем)s.',
                орг=record.organization_id.display_name,
                кем=dict(record._fields['role'].selection)[record.role]))
        return True

    def action_decline(self):
        """Отказать по заявлению.

        Не «прекращено»: членства не было, и запись о выбытии из него
        была бы неправдой. Заявление отклонено — и человек может подать
        новое, когда обстоятельства изменятся.
        """
        self._check_can_decide()
        for record in self:
            if record.state != 'applied':
                raise UserError(_(
                    'Отклонить можно заявление. «%s» уже в другом '
                    'состоянии.') % record.display_name)
            record._notify_member(_(
                'Заявление о вступлении в «%s» отклонено.')
                % record.organization_id.display_name)
        self.sudo().unlink()
        return True

    def action_apply_to_leave(self):
        for record in self:
            if record.partner_id != self.env.user.partner_id                     and not record.can_decide:
                raise UserError(_(
                    'Заявление о выходе подаёт сам участник.'))
        self.sudo().write({'state': 'leaving'})
        for record in self:
            record.env['coop.notification']._notify(
                record._roster_deciders(),
                _('Заявление о выходе из «%(орг)s»: %(кто)s.',
                  орг=record.organization_id.display_name,
                  кто=record.partner_id.display_name),
                record=record.organization_id, kind='org')
        return True

    def action_withdraw(self):
        """Отозвать собственное заявление, пока его не рассмотрели."""
        for record in self:
            if record.partner_id != self.env.user.partner_id:
                raise UserError(_('Отозвать можно своё заявление.'))
            if record.state != 'applied':
                raise UserError(_(
                    'Отзывают заявление. Членство уже действует — из него '
                    'выходят, а не отзывают.'))
        self.sudo().unlink()
        return True

    def action_terminate(self):
        self._check_can_decide()
        self.sudo().write({'state': 'ended',
                           'left_on': fields.Date.context_today(self)})
        for record in self:
            record._notify_member(_(
                'Членство в «%s» прекращено.')
                % record.organization_id.display_name)
        return True
