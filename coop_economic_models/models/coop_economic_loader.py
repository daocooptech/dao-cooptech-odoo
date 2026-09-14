# -*- coding: utf-8 -*-
"""Сборка справочника форм из карточек форм и карточек режимов.

Абстрактная модель, а не хук установки: справочник нужно перезаливать и
при обновлении модуля — закон меняется, а хук выполняется только при
первой установке. Тот же приём, что у загрузчика каталогов в
`coop_demo`.

Записи ищутся и обновляются по ключу, а не пересоздаются: на строку
справочника ссылаются проекты, и удалить её значит оборвать ссылку.
Правки в тексте доезжают до участника при следующем обновлении модуля.
"""
import logging

from odoo import api, fields, models

from ..data import legal_content, legal_rows

_logger = logging.getLogger(__name__)


class CoopEconomicLoader(models.AbstractModel):
    _name = 'coop.economic.loader'
    _description = 'Загрузчик справочника форм собственности'

    @api.model
    def load_forms(self):
        schemes = self._load_schemes()
        self._load_rows(schemes)
        return True

    def _load_schemes(self):
        Scheme = self.env['coop.economic.scheme'].sudo()
        by_key = {}
        for order, row in enumerate(legal_content.SCHEMES):
            values = dict(row)
            values['checked_on'] = legal_content.CHECKED_ON
            values.setdefault('sequence', (order + 1) * 10)
            scheme = Scheme.search([('key', '=', values['key'])], limit=1)
            if scheme:
                scheme.write(values)
            else:
                scheme = Scheme.create(values)
            by_key[values['key']] = scheme
        _logger.info('Уклады кооперативов: %s', len(by_key))
        return by_key

    def _load_rows(self, schemes):
        Form = self.env['coop.economic.model'].sudo()
        # Формы платформы ищем по коду один раз: искать внутри цикла
        # значит шестьдесят четыре лишних запроса на каждой установке.
        base_forms = {
            form.code: form.id
            for form in self.env['coop.legal.form'].sudo().search([])
        }
        created = updated = 0

        for order, (key, card_key, regime_key, name, summary) in enumerate(
                legal_rows.ROWS):
            card = legal_content.FORM_CARDS[card_key]
            regime = legal_content.REGIME_CARDS[regime_key]

            values = {
                'key': key,
                'name': name,
                'summary': summary,
                'sequence': (order + 1) * 10,
                'form_group': card['group'],
                'form_name': card['form_name'],
                'regime': regime_key,
                'checked_on': legal_content.CHECKED_ON,

                # Текст формы и текст режима не смешиваются: первый
                # отвечает за устройство, второй — за деньги. Участник
                # читает их подряд и видит, что от чего зависит.
                'management': card.get('management') or False,
                'liability': card.get('liability') or False,
                'for_investor': card.get('for_investor') or False,
                'warning': card.get('warning') or False,
                'taxes': regime.get('taxes') or False,
                'reporting': regime.get('reporting') or False,
                'limits': regime.get('limits') or False,

                'member_composition': card.get('member_composition', 'n/a'),
                'members_note': card.get('members_note') or False,
                'min_members': card.get('min_members', 0),
                'org_share_cap': card.get('org_share_cap', 0),
                'requires_charter_clause': card.get(
                    'requires_charter_clause', False),
                'org_acts_via_representative': card.get(
                    'org_acts_via_representative', False),

                # Признаки режима перекрывают признаки формы там, где
                # режим строже: у самозанятости нанимать нельзя, кем бы
                # ты ни был.
                'requires_registration': card.get(
                    'requires_registration', True),
                'can_hire': (card.get('can_hire', True)
                             and regime.get('can_hire', True)),
                'region_dependent': regime.get('region_dependent', False),
                'income_limit': regime.get('income_limit', 0),
                'employee_limit': regime.get('employee_limit', 0),
                'vat_exempt_limit': regime.get('vat_exempt_limit', 0),
                'valid_to': regime.get('valid_to') or False,
                'legal_basis': card.get('legal_basis') or False,
                'legal_form_id': base_forms.get(card.get('legal_code')) or False,
            }

            form = Form.search([('key', '=', key)], limit=1)
            if form:
                form.write(values)
                updated += 1
            else:
                form = Form.create(values)
                created += 1

            wanted = [schemes[scheme_key].id
                      for scheme_key in card.get('schemes', [])
                      if scheme_key in schemes]
            if wanted or form.scheme_ids:
                form.scheme_ids = [(6, 0, wanted)]

        _logger.info('Формы собственности: создано %s, обновлено %s',
                     created, updated)
