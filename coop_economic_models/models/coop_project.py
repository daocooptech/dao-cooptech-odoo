# -*- coding: utf-8 -*-
"""Форма собственности у проекта и пояснения под ней.

Поле выбора само по себе бесполезно: «ООО на УСН доходы» ничего не
говорит ни тому, кто затевает проект впервые, ни тому, кто думает в него
вложиться. Поэтому под выбранной строкой разворачивается разбор —
управление, налоги, отчётность, ответственность, ограничения, — и
отдельно то, что важно знать вкладывающемуся.

Пояснения не копируются в проект, а берутся из справочника связанными
полями. Копия зажила бы своей жизнью: закон меняется каждый год, и через
две зимы у сотни проектов висели бы сто разных редакций одного и того же
текста, каждая устаревшая по-своему.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Формы, внутри которых уклад имеет смысл. У общества с ограниченной
# ответственностью «распределения по Чартаеву» не бывает: там доля в
# уставном капитале, и порядок задан законом, а не уставом.
COOPERATIVE_GROUPS = ('prodcoop', 'consumercoop')


class CoopProject(models.Model):
    _inherit = 'coop.project'

    economic_model_id = fields.Many2one(
        'coop.economic.model', string='Форма собственности', index=True,
        tracking=True,
        help='Правовая форма и налоговый режим проекта. От них зависит, '
             'кто принимает решения, сколько уходит в бюджет и чем '
             'отвечают участники.')
    economic_scheme_id = fields.Many2one(
        'coop.economic.scheme', string='Уклад', tracking=True,
        help='Как внутри кооператива распределяется результат. '
             'У некооперативных форм не заполняется.')

    legal_group = fields.Selection(
        related='economic_model_id.form_group', string='Группа формы')
    economic_scheme_applicable = fields.Boolean(
        string='Уклад применим', compute='_compute_scheme_applicable')

    # Пояснения показываются связанными полями, а не копией: закон
    # меняется, а копия остаётся.
    legal_summary = fields.Char(
        related='economic_model_id.summary', string='Коротко')
    legal_management = fields.Html(
        related='economic_model_id.management', string='Управление')
    legal_taxes = fields.Html(
        related='economic_model_id.taxes', string='Налоги и взносы')
    legal_reporting = fields.Html(
        related='economic_model_id.reporting', string='Отчётность')
    legal_liability = fields.Html(
        related='economic_model_id.liability', string='Ответственность')
    legal_limits = fields.Html(
        related='economic_model_id.limits', string='Ограничения')
    legal_for_investor = fields.Html(
        related='economic_model_id.for_investor',
        string='Что важно вкладывающемуся')
    legal_warning = fields.Html(
        related='economic_model_id.warning', string='Предупреждение')
    legal_basis = fields.Char(
        related='economic_model_id.legal_basis', string='Основание')
    legal_members_note = fields.Char(
        related='economic_model_id.members_note', string='Состав участников')
    legal_checked_on = fields.Date(
        related='economic_model_id.checked_on', string='Числа сверены')

    scheme_distribution = fields.Html(
        related='economic_scheme_id.distribution', string='Как делится результат')
    scheme_charter_notes = fields.Html(
        related='economic_scheme_id.charter_notes', string='Что закрепить уставом')
    scheme_for_investor = fields.Html(
        related='economic_scheme_id.for_investor',
        string='Что важно вкладывающемуся по укладу')

    @api.depends('economic_model_id.form_group')
    def _compute_scheme_applicable(self):
        for record in self:
            record.economic_scheme_applicable = (
                record.economic_model_id.form_group in COOPERATIVE_GROUPS)

    @api.onchange('economic_model_id')
    def _onchange_legal_form(self):
        """Уклад снимается, если форма перестала быть кооперативной.

        Иначе у общества с ограниченной ответственностью остаётся
        «распределение по Чартаеву», выбранное до смены формы, и никто
        этого не замечает: поле спрятано.
        """
        for record in self:
            group = record.economic_model_id.form_group
            if group not in COOPERATIVE_GROUPS:
                record.economic_scheme_id = False
            elif record.economic_scheme_id and record.economic_model_id:
                allowed = record.economic_model_id.scheme_ids
                if allowed and record.economic_scheme_id not in allowed:
                    record.economic_scheme_id = False

    @api.constrains('economic_model_id', 'economic_scheme_id')
    def _check_scheme(self):
        for record in self:
            if not record.economic_scheme_id:
                continue
            if record.economic_model_id.form_group not in COOPERATIVE_GROUPS:
                raise ValidationError(_(
                    'Уклад «%(scheme)s» бывает только у кооперативов, а у '
                    'проекта выбрана форма «%(form)s».',
                    scheme=record.economic_scheme_id.name,
                    form=record.economic_model_id.name or 'не выбрана'))
            allowed = record.economic_model_id.scheme_ids
            if allowed and record.economic_scheme_id not in allowed:
                raise ValidationError(_(
                    'Уклад «%(scheme)s» не применяется к форме «%(form)s».',
                    scheme=record.economic_scheme_id.name,
                    form=record.economic_model_id.name))
