# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .ndfl import ndfl, rubles

ARTEL_KINDS = ('production', 'agri_production')
# П. 3 ст. 425 НК: 30 % в пределах единой предельной величины базы, 15,1 %
# сверх неё. База за год — постановлением правительства (на 2026 —
# 2 979 000 ₽); для лет без своей величины берётся последняя известная.
INSURANCE_RATE = 30.0
INSURANCE_RATE_OVER = 15.1
INSURANCE_BASE = {2026: 2_979_000}
# П. 2.4 ст. 427 НК: МСП из перечня — 15 % с части выплат сверх 1,5 МРОТ
# в месяц; в пределах — общий тариф. МРОТ на 2026 — 27 093 ₽ (429-ФЗ).
SME_RATE = 15.0
MROT = {2026: 27_093}


def _by_year(table, year):
    known = [y for y in table if y <= year] or [min(table)]
    return table[max(known)]


class CoopTaxLaborPayout(models.Model):
    """Выплата члену артели за личное трудовое участие (решения 514, 516).

    Строк пять: начислено, НДФЛ, страховые взносы, взносы на травматизм,
    на руки — и во что выплата обходится кооперативу.

    - Взносы: выплата «в зависимости от его трудового участия» облагается
      ими как у наёмных (письмо Минфина 18.07.2017 № 03-15-06/45648);
      иностранцу за работу за рубежом — без взносов (п. 5 ст. 420 НК).
    - Травматизм: членов артели нет в п. 1 ст. 5 125-ФЗ, и платить ли с
      их выплат, решает кооператив (решение 514).
    - Нерезидент: в РФ — с патентом или разрешением, НДФЛ 30 % (п. 3
      ст. 224); за рубежом — доход вне РФ (пп. 6 п. 3 ст. 208), агентского
      НДФЛ нет (решение 516).

    Резидентство, гражданство, тарифы кооператива копируются в строку при
    создании: выплата считается по тому, что было на её дату, и правка
    профиля или устава потом её не переписывает.
    """
    _name = 'coop.tax.labor.payout'
    _description = 'Выплата за трудовое участие'
    _order = 'date desc, id desc'

    name = fields.Char(string='Основание', required=True,
                       default=lambda self: _('Выплата за трудовое участие'))
    cooperative_id = fields.Many2one(
        'res.partner', string='Кооператив', required=True, index=True,
        ondelete='restrict',
        domain=[('coop_cooperative_kind', 'in', ARTEL_KINDS)])
    partner_id = fields.Many2one(
        'res.partner', string='Член кооператива', required=True, index=True,
        ondelete='restrict', domain=[('is_company', '=', False)])
    date = fields.Date(string='Дата выплаты', required=True,
                       default=fields.Date.context_today, index=True)
    year = fields.Integer(string='Год', compute='_compute_year', store=True, index=True)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id, required=True)
    amount = fields.Monetary(string='Начислено', currency_field='currency_id', required=True)
    state = fields.Selection([
        ('draft', 'Начислено'),
        ('paid', 'Выплачено'),
        ('cancelled', 'Отменено'),
    ], string='Состояние', default='draft', required=True, index=True)

    resident = fields.Boolean(string='Налоговый резидент РФ', default=True)
    treaty_rate = fields.Float(string='Ставка по соглашению, %', digits=(5, 2))
    foreigner = fields.Boolean(string='Иностранный гражданин')
    work_place = fields.Selection([
        ('ru', 'В России'),
        ('abroad', 'За рубежом'),
    ], string='Место работы', default='ru', required=True)
    permit = fields.Selection([
        ('patent', 'Патент'),
        ('permit', 'Разрешение на работу'),
    ], string='Документ на работу в РФ')
    sme = fields.Boolean(string='МСП из перечня')
    injury_rate = fields.Float(string='Тариф на травматизм, %', digits=(5, 2))

    ndfl_amount = fields.Monetary(
        string='НДФЛ', currency_field='currency_id', compute='_compute_amounts', store=True)
    ndfl_rate = fields.Char(string='Ставка НДФЛ', compute='_compute_amounts', store=True)
    insurance = fields.Monetary(
        string='Страховые взносы', currency_field='currency_id',
        compute='_compute_amounts', store=True)
    insurance_rate = fields.Char(string='Тариф взносов', compute='_compute_amounts', store=True)
    injury = fields.Monetary(
        string='Травматизм', currency_field='currency_id', compute='_compute_amounts', store=True)
    net_amount = fields.Monetary(
        string='На руки', currency_field='currency_id', compute='_compute_amounts', store=True)
    cost = fields.Monetary(
        string='Обходится кооперативу', currency_field='currency_id',
        compute='_compute_amounts', store=True)

    _amount_positive = models.Constraint(
        'check(amount > 0)', 'Начислено должно быть больше нуля.')

    @api.model_create_multi
    def create(self, vals_list):
        Partner = self.env['res.partner'].sudo()
        for vals in vals_list:
            person = Partner.browse(vals.get('partner_id'))
            coop = Partner.browse(vals.get('cooperative_id'))
            if person:
                vals.setdefault('resident', person.coop_tax_resident)
                vals.setdefault('treaty_rate', person.coop_tax_treaty_rate)
                vals.setdefault('foreigner', person._coop_citizenship().code not in (False, 'RU'))
            if coop:
                vals.setdefault('sme', coop.coop_tax_sme)
                vals.setdefault('injury_rate', coop.coop_injury_rate if coop.coop_injury_insurance else 0.0)
        return super().create(vals_list)

    @api.onchange('partner_id', 'cooperative_id')
    def _onchange_people(self):
        if self.partner_id:
            self.resident = self.partner_id.coop_tax_resident
            self.treaty_rate = self.partner_id.coop_tax_treaty_rate
            self.foreigner = self.partner_id._coop_citizenship().code not in (False, 'RU')
        if self.cooperative_id:
            coop = self.cooperative_id
            self.sme = coop.coop_tax_sme
            self.injury_rate = coop.coop_injury_rate if coop.coop_injury_insurance else 0.0

    @api.depends('date')
    def _compute_year(self):
        for record in self:
            record.year = record.date.year if record.date else 0

    def _earlier(self):
        """Прежние выплаты того же кооператива тому же человеку за год."""
        self.ensure_one()
        domain = [('cooperative_id', '=', self.cooperative_id.id),
                  ('partner_id', '=', self.partner_id.id),
                  ('year', '=', self.date.year), ('state', '!=', 'cancelled')]
        if isinstance(self.id, int):
            domain += ['|', ('date', '<', self.date),
                       '&', ('date', '=', self.date), ('id', '<', self.id)]
        else:
            domain += [('date', '<=', self.date)]
        return self.search(domain)

    @api.depends('amount', 'date', 'resident', 'treaty_rate', 'foreigner',
                 'work_place', 'sme', 'injury_rate', 'cooperative_id', 'partner_id')
    def _compute_amounts(self):
        for record in self:
            amount = record.amount or 0.0
            if not (amount and record.date and record.partner_id and record.cooperative_id):
                record.update({'ndfl_amount': 0, 'ndfl_rate': '', 'insurance': 0,
                               'insurance_rate': '', 'injury': 0,
                               'net_amount': amount, 'cost': amount})
                continue
            earlier = sum(record.sudo()._earlier().mapped('amount'))
            abroad = record.work_place == 'abroad'
            if abroad and not record.resident:
                tax, rate = 0.0, _('доход вне РФ')
            else:
                tax, rate = ndfl(amount, earlier, resident=record.resident,
                                 treaty_rate=record.treaty_rate)
            insurance, insurance_rate = record._insurance(amount, earlier, abroad)
            # Страхование по 125-ФЗ — работы в России; за рубежом кооператив
            # платит только начисленное (разбор бухгалтера 26.10, Р8).
            injury = rubles(amount * record.injury_rate / 100.0) \
                if record.injury_rate and not abroad else 0.0
            record.update({
                'ndfl_amount': tax, 'ndfl_rate': rate,
                'insurance': insurance, 'insurance_rate': insurance_rate,
                'injury': injury, 'net_amount': amount - tax,
                'cost': amount + insurance + injury,
            })

    def _insurance(self, amount, earlier, abroad):
        if abroad and self.foreigner:
            return 0.0, _('без взносов — иностранец за рубежом')
        if self.sme:
            floor = 1.5 * _by_year(MROT, self.date.year)
            low = min(amount, floor)
            return (rubles(low * INSURANCE_RATE / 100.0 + (amount - low) * SME_RATE / 100.0),
                    _('30 % до 1,5 МРОТ, 15 % сверх') if amount > floor else '30 %')
        limit = _by_year(INSURANCE_BASE, self.date.year)
        within = max(0.0, min(amount, limit - earlier))
        over = amount - within
        label = '30 %' if not over else (
            '15,1 %' if not within else _('30 % и 15,1 % сверх базы'))
        return rubles(within * INSURANCE_RATE / 100.0 + over * INSURANCE_RATE_OVER / 100.0), label

    @api.constrains('resident', 'work_place', 'permit')
    def _check_work_place(self):
        for record in self:
            if record.resident and record.work_place == 'abroad':
                raise ValidationError(_(
                    'Работа за рубежом отмечается у нерезидентов (решение '
                    '516). Резидент РФ платит НДФЛ со всех доходов — '
                    'отметьте «В России».'))
            if not record.resident and record.work_place == 'ru' and not record.permit:
                raise ValidationError(_(
                    'Нерезидент работает в России с патентом или разрешением '
                    'на работу (решение 516) — укажите документ.'))

    def action_pay(self):
        self.filtered(lambda r: r.state == 'draft').write({'state': 'paid'})
        return True

    def action_cancel(self):
        self.filtered(lambda r: r.state == 'draft').write({'state': 'cancelled'})
        return True
