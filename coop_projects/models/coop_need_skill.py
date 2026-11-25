# -*- coding: utf-8 -*-
"""Навыки и услуги в потребностях проекта (№ 474, решения 692, 697).

Трудовая потребность называет специализацию — и по ней находятся люди с
навыком и организации с услугой. Отклик навыком или услугой — вклад
трудом: ставка откликнувшегося, умноженная на количество в единице этой
ставки (месяцы, дни, часы, работы — владелец 25.11.2026). Инициатор
принимает или предлагает другую ставку.

Навык бывает только у человека, услуга — только у организации: это одна
модель `coop.skill.offer`, и различает их хозяин предложения.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

from .coop_resource import OPEN_FOR_NEEDS

# Сколько предложений показываем в подборе: дальше их не читают.
MATCH_LIMIT = 100

RATE_PERIODS = [
    ('month', 'в месяц'),
    ('day', 'в день'),
    ('hour', 'в час'),
    ('job', 'за работу'),
]
QTY_LABELS = {
    'month': 'месяцев', 'day': 'дней', 'hour': 'часов', 'job': 'работ'}


def money_label(amount, currency):
    text = '{:,.2f}'.format(amount or 0.0).replace(',', ' ').replace('.', ',')
    if text.endswith(',00'):
        text = text[:-3]
    return '%s %s' % (text, currency.symbol or '₽')


class CoopResourceSkill(models.Model):
    _inherit = 'coop.resource'

    need_specialization_id = fields.Many2one(
        'coop.specialization', string='Специализация', index=True,
        ondelete='set null',
        help='Кто нужен. По специализации трудовой потребности находятся '
             'люди с навыком и организации с услугой.')
    need_invited_offer_ids = fields.Many2many(
        'coop.skill.offer', 'coop_need_invited_offer_rel', 'need_id', 'offer_id',
        string='Приглашённые', copy=False)
    need_match_count = fields.Integer(
        string='Подходят', compute='_compute_need_match_count')
    need_matches_json = fields.Json(compute='_compute_need_matches_json')

    def _need_match_domain(self):
        """Чьи предложения подходят: той же специализации, в каталоге, не свои."""
        self.ensure_one()
        return [('state', '=', 'published'),
                ('coop_specialization_id', '=', self.need_specialization_id.id),
                ('partner_id', '!=', self.project_id.partner_id.id)]

    @api.depends('resource_type', 'need_specialization_id', 'project_id.partner_id')
    def _compute_need_match_count(self):
        needs = self.filtered(lambda r: r.project_id and r.resource_type == 'labour'
                              and r.need_specialization_id)
        totals, own = {}, {}
        if needs:
            for spec, partner, total in self.env['coop.skill.offer'].sudo()._read_group(
                    [('state', '=', 'published'),
                     ('coop_specialization_id', 'in', needs.need_specialization_id.ids)],
                    groupby=['coop_specialization_id', 'partner_id'],
                    aggregates=['__count']):
                totals[spec.id] = totals.get(spec.id, 0) + total
                own[spec.id, partner.id] = total
        for record in self:
            spec = record.need_specialization_id.id
            record.need_match_count = (
                totals.get(spec, 0) - own.get((spec, record.project_id.partner_id.id), 0)
                if record in needs else 0)

    @api.depends_context('uid')
    @api.depends('need_specialization_id', 'need_invited_offer_ids',
                 'need_offer_ids.state', 'state', 'project_id.state')
    def _compute_need_matches_json(self):
        """Карточки подбора. Только тому, кто ведёт потребность."""
        Offer = self.env['coop.skill.offer'].sudo()
        for record in self:
            record.need_matches_json = False
            if not (record.need_can_decide and record.need_specialization_id
                    and record.resource_type == 'labour'):
                continue
            city = (record.city or record.project_id.city or '').strip().lower()
            answered = record.sudo().need_offer_ids.partner_id
            invited = record.sudo().need_invited_offer_ids
            found = Offer.search(record._need_match_domain(), limit=MATCH_LIMIT * 3)
            # Сперва свой город, в нём — по доверию.
            found = found.sorted(lambda o: (
                not city or (o.city or '').strip().lower() != city,
                -(o.partner_trust or 0), o.id))[:MATCH_LIMIT]
            record.need_matches_json = {
                'can_invite': record._need_can_invite(),
                'offers': [{
                    'id': offer.id,
                    'name': offer.name,
                    'partner_id': offer.partner_id.id,
                    'partner': offer.partner_id.name,
                    'is_company': offer.partner_id.is_company,
                    'city': offer.city or '',
                    'rate': offer.rate_display or '',
                    'experience': offer.experience_short or '',
                    'trust': offer.partner_trust,
                    'deals': offer.partner_deals_done,
                    'status': ('answered' if offer.partner_id in answered
                               else 'invited' if offer in invited else ''),
                } for offer in found],
            }

    def _need_can_invite(self):
        self.ensure_one()
        return bool(self.need_can_decide and self.state == 'published'
                    and not self.need_accepted_id
                    and self.project_id.state in OPEN_FOR_NEEDS)

    def _need_check_decide(self):
        self.ensure_one()
        if not self.need_can_decide:
            raise UserError(_(
                'Подбирать исполнителей для проекта «%s» может его инициатор, '
                'ответственный за потребность или тот, кому организация '
                'поручила сделки.') % self.project_id.name)

    def action_open_need_matches(self):
        """Окно «Подходят» из строки трудовой потребности."""
        self.ensure_one()
        self._need_check_decide()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Подходят: %s') % self.name,
            'res_model': 'coop.resource',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('coop_projects.view_coop_need_match_form').id, 'form')],
            'target': 'new',
        }

    def action_need_set_specialization(self, specialization_id):
        """Специализацию называют и прямо в окне подбора."""
        self._need_check_decide()
        self.sudo().need_specialization_id = self.env[
            'coop.specialization'].browse(specialization_id or []).exists()
        return True

    def action_invite_offer(self, offer_id):
        """«Пригласить» — извещение хозяину навыка или услуги."""
        self.ensure_one()
        self._need_check_decide()
        if not self._need_can_invite():
            raise UserError(_(
                'Приглашать можно в открытую потребность: проект собирает '
                'или запущен, исполнитель ещё не выбран.'))
        offer = self.env['coop.skill.offer'].sudo().search(
            self._need_match_domain() + [('id', '=', offer_id)], limit=1)
        if not offer:
            raise UserError(_('Этого предложения в каталоге больше нет.'))
        if offer in self.sudo().need_invited_offer_ids:
            return True
        self.sudo().write({'need_invited_offer_ids': [(4, offer.id)]})
        self.env['coop.notification']._notify(
            offer.partner_id,
            _('Вас приглашают в проект «%(project)s»: открыта потребность '
              '«%(need)s», подошло ваше предложение «%(offer)s». Ответить '
              'можно на странице проекта кнопкой «Участвовать».',
              project=self.project_id.name, need=self.name, offer=offer.name),
            record=self.project_id, kind='project')
        return True


class CoopProjectRates(models.Model):
    _inherit = 'coop.project'

    # Столбец «Расчёт» во «Вкладах» — только где есть отклики по ставке.
    coop_has_rates = fields.Boolean(compute='_compute_coop_has_rates')

    @api.depends('contribution_ids.labour_rate')
    def _compute_coop_has_rates(self):
        for record in self:
            record.coop_has_rates = any(record.contribution_ids.mapped('labour_rate'))


class CoopProjectContributionSkill(models.Model):
    _inherit = 'coop.project.contribution'

    skill_offer_id = fields.Many2one(
        'coop.skill.offer', string='Навык или услуга', index=True,
        ondelete='set null',
        help='Предложение каталога, которым человек или организация '
             'откликнулись на трудовую потребность.')
    # Ставка снимком: предложение в каталоге потом правят и снимают, а
    # договорились по той, что стояла в отклике.
    labour_rate = fields.Monetary(
        string='Ставка', currency_field='currency_id', tracking=True)
    labour_period = fields.Selection(RATE_PERIODS, string='Единица ставки')
    labour_qty = fields.Float(string='Количество', digits=(16, 2))
    counter_rate = fields.Monetary(
        string='Ставка инициатора', currency_field='currency_id',
        tracking=True, copy=False)
    rate_note = fields.Char(string='Расчёт', compute='_compute_rate_note')
    is_mine = fields.Boolean(compute='_compute_is_mine')

    @api.depends('labour_rate', 'labour_period', 'labour_qty', 'counter_rate',
                 'currency_id')
    def _compute_rate_note(self):
        periods = dict(RATE_PERIODS)
        for record in self:
            if not (record.labour_rate and record.labour_period):
                record.rate_note = False
                continue
            text = '%s %s × %s' % (
                money_label(record.labour_rate, record.currency_id),
                periods[record.labour_period],
                ('%g' % record.labour_qty).replace('.', ','))
            if record.counter_rate:
                text = _('%(text)s · инициатор предлагает %(rate)s', text=text,
                         rate=money_label(record.counter_rate, record.currency_id))
            record.rate_note = text

    @api.depends_context('uid')
    @api.depends('partner_id')
    def _compute_is_mine(self):
        mine = self.env.user.coop_actor_partner_ids
        for record in self:
            record.is_mine = record.partner_id in mine

    def action_open_counter(self):
        self.ensure_one()
        self._check_can_decide()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Другая ставка: %s') % self.partner_id.name,
            'res_model': 'coop.contribution.counter',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_contribution_id': self.id,
                'default_rate': self.counter_rate or self.labour_rate,
            },
        }

    def _propose_rate(self, rate):
        self.ensure_one()
        self._check_can_decide()
        if self.state != 'offered' or not (self.labour_rate and self.labour_qty):
            raise UserError(_('Другую ставку предлагают по отклику, который '
                              'ещё не разобран и посчитан по ставке.'))
        if rate <= 0:
            raise UserError(_('Назовите ставку больше нуля.'))
        if not float_compare(rate, self.labour_rate, precision_digits=2):
            raise UserError(_('Это та же ставка — отклик можно просто принять.'))
        self.sudo().counter_rate = rate
        self.env['coop.notification']._notify(
            self.partner_id,
            _('По проекту «%(project)s» вам предлагают другую ставку: '
              '%(rate)s %(period)s вместо %(was)s. Ответьте на странице '
              'проекта, вкладка «Вклады».',
              project=self.project_id.name,
              rate=money_label(rate, self.currency_id),
              period=dict(RATE_PERIODS)[self.labour_period],
              was=money_label(self.labour_rate, self.currency_id)),
            record=self.project_id, kind='project')

    def _check_counter_mine(self):
        self.ensure_one()
        if not self.is_mine:
            raise UserError(_('Отвечает на ставку тот, кто откликнулся.'))
        if self.state != 'offered' or not self.counter_rate:
            raise UserError(_('Предложенной ставки уже нет.'))

    def _notify_counter(self, text):
        deciders = (self.need_id.sudo()._need_deciders() if self.need_id
                    else self.project_id.partner_id)
        self.env['coop.notification']._notify(
            deciders, text, record=self.project_id, kind='project')

    def action_counter_agree(self):
        """Согласился — отклик пересчитан; принять его решает инициатор."""
        for record in self:
            record._check_counter_mine()
            rate = record.counter_rate
            record.sudo().write({
                'labour_rate': rate, 'counter_rate': 0.0,
                'value': rate * record.labour_qty})
            record._notify_counter(_(
                'Отклик по проекту «%(project)s»: %(who)s принимает вашу '
                'ставку %(rate)s. Отклик можно утвердить.',
                who=record.partner_id.name,
                rate=money_label(rate, record.currency_id),
                project=record.project_id.name))
        return True

    def action_counter_refuse(self):
        """Остался при своей ставке — отклик не отозван."""
        for record in self:
            record._check_counter_mine()
            rate = record.counter_rate
            record.sudo().counter_rate = 0.0
            record._notify_counter(_(
                'Отклик по проекту «%(project)s»: %(who)s остаётся при своей '
                'ставке %(own)s, ваша — %(rate)s — не подошла.',
                who=record.partner_id.name,
                rate=money_label(rate, record.currency_id),
                project=record.project_id.name,
                own=money_label(record.labour_rate, record.currency_id)))
        return True


class CoopContributionCounter(models.TransientModel):
    _name = 'coop.contribution.counter'
    _description = 'Другая ставка по отклику'

    contribution_id = fields.Many2one(
        'coop.project.contribution', required=True, readonly=True)
    currency_id = fields.Many2one(related='contribution_id.currency_id')
    own_note = fields.Char(related='contribution_id.rate_note', string='Ставка отклика')
    labour_period = fields.Selection(related='contribution_id.labour_period')
    labour_qty = fields.Float(related='contribution_id.labour_qty')
    rate = fields.Monetary(
        string='Ваша ставка', currency_field='currency_id', required=True)
    total = fields.Monetary(
        string='Вклад составит', currency_field='currency_id',
        compute='_compute_total')

    @api.depends('rate', 'contribution_id')
    def _compute_total(self):
        for wizard in self:
            wizard.total = wizard.rate * wizard.labour_qty

    def action_propose(self):
        self.ensure_one()
        self.contribution_id._propose_rate(self.rate)
        return {'type': 'ir.actions.act_window_close'}


class CoopSkillOfferRate(models.Model):
    _inherit = 'coop.skill.offer'

    @api.depends('name', 'rate_display')
    @api.depends_context('coop_with_rate')
    def _compute_display_name(self):
        """В окне «Участие» — со ставкой: у одного мастера несколько
        предложений с одним названием, и различает их цена."""
        super()._compute_display_name()
        if not self.env.context.get('coop_with_rate'):
            return
        for record in self:
            if record.rate_display:
                record.display_name = '%s — %s' % (record.name, record.rate_display)


class CoopContributeSkill(models.TransientModel):
    """Окно «Участие»: свой навык или услуга вместо описания словами."""
    _inherit = 'coop.project.contribute'

    skill_offer_id = fields.Many2one(
        'coop.skill.offer', string='Мой навык или услуга',
        help='Ставка — из вашего предложения, вклад — ставка на количество.')
    my_skill_ids = fields.Many2many(
        'coop.skill.offer', compute='_compute_my_skills')
    labour_rate = fields.Monetary(string='Ставка', currency_field='currency_id')
    labour_period = fields.Selection(RATE_PERIODS, string='Единица ставки')
    labour_qty = fields.Float(string='Сколько', default=1.0, digits=(16, 2))
    labour_unit = fields.Char(compute='_compute_labour_unit')

    @api.depends('kind', 'need_id')
    @api.depends_context('uid')
    def _compute_my_skills(self):
        me = self.env.user._coop_acting_partner()
        mine = self.env['coop.skill.offer'].search(
            [('partner_id', '=', me.id), ('state', '=', 'published')], limit=200)
        for wizard in self:
            spec = wizard.need_id._origin.need_specialization_id
            # Та же специализация — если такие предложения есть; нет их —
            # откликнуться можно и соседним умением.
            same = mine.filtered(lambda o: spec and o.coop_specialization_id == spec)
            wizard.my_skill_ids = same or mine

    @api.depends('labour_period')
    def _compute_labour_unit(self):
        for wizard in self:
            wizard.labour_unit = QTY_LABELS.get(wizard.labour_period, '')

    def _coop_offer_rate(self, offer):
        """Ставка предложения в валюте проекта."""
        self.ensure_one()
        rate = offer.rate or 0.0
        source, target = offer.currency_id, self.currency_id
        if rate and source and target and source != target:
            rate = source._convert(
                rate, target, self.env.company, fields.Date.context_today(self))
        return rate

    @api.onchange('skill_offer_id')
    def _onchange_skill_offer_id(self):
        for wizard in self:
            offer = wizard.skill_offer_id
            # Сдельно или без цены — сумму человек называет сам.
            priced = offer and offer.rate and offer.rate_kind != 'piece'
            wizard.labour_rate = wizard._coop_offer_rate(offer) if priced else 0.0
            wizard.labour_period = (offer.rate_period or 'job') if priced else False
            if offer:
                wizard.name = offer.name
                wizard.resource_id = False

    @api.onchange('labour_rate', 'labour_qty', 'labour_period')
    def _onchange_labour_value(self):
        for wizard in self:
            if wizard.kind == 'labour' and wizard.skill_offer_id and wizard.labour_period:
                wizard.value = wizard.labour_rate * wizard.labour_qty

    @api.onchange('kind')
    def _onchange_kind_skill(self):
        for wizard in self:
            if wizard.kind != 'labour' and wizard.skill_offer_id:
                wizard.skill_offer_id = False
                wizard.labour_rate = 0.0
                wizard.labour_period = False

    def _coop_offer_values(self):
        values = super()._coop_offer_values()
        offer = self.skill_offer_id
        if self.kind != 'labour' or not offer:
            return values
        me = self.env.user._coop_acting_partner()
        if offer.partner_id != me or offer.state != 'published':
            raise UserError(_('Откликнуться можно своим опубликованным '
                              'навыком или услугой.'))
        values['skill_offer_id'] = offer.id
        if offer.rate and offer.rate_kind != 'piece':
            # Ставка — из предложения, не из окна: её откликнувшийся
            # назвал всем, а значение окна можно подменить.
            if self.labour_qty <= 0:
                raise UserError(_('Укажите, сколько работы берёте.'))
            rate = self._coop_offer_rate(offer)
            values.update(
                labour_rate=rate, labour_period=offer.rate_period or 'job',
                labour_qty=self.labour_qty, value=rate * self.labour_qty)
        return values
