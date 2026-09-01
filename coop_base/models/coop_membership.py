# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools
from odoo.exceptions import ValidationError


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
        ('member', 'Пайщик'),
        ('board', 'Правление'),
        ('audit', 'Ревизионная комиссия'),
        ('staff', 'Наёмный сотрудник'),
    ], string='Роль', required=True, default='member', tracking=True,
        help='Роль определяет, что участник вправе видеть и решать, '
             'а не его должность.')

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
        records = super().create(vals_list)
        records._invalidate_rule_cache()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {'partner_id', 'organization_id', 'role', 'state'} & set(vals):
            self._invalidate_rule_cache()
        return result

    def unlink(self):
        self._invalidate_rule_cache()
        return super().unlink()

    def action_admit(self):
        self.write({'state': 'active',
                    'joined_on': fields.Date.context_today(self)})

    def action_apply_to_leave(self):
        self.write({'state': 'leaving'})

    def action_terminate(self):
        self.write({'state': 'ended',
                    'left_on': fields.Date.context_today(self)})
