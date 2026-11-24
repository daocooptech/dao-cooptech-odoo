# -*- coding: utf-8 -*-
"""«Кто делает и из чего» — только выгрузка из ERP владельца (№ 484).

Владелец 24.11.2026: «это выгрузка из ERP-системы пользователя; если этих
данных нет, то мы их не указываем в карточках». Учёт производства есть у
организации и на её собственные изделия, поэтому состав остаётся только
у предложений организаций в трёх разделах и не на подержанное; у спроса,
недвижимости, услуг и частных лиц его быть не может.
"""
import logging

_logger = logging.getLogger(__name__)

ERP_SECTIONS = (
    'Продовольствие и сельхозпродукция',
    'Оборудование и станки',
    'Сырьё и материалы',
)

MAKING_FIELDS = ('manufacturer_ids', 'material_ids', 'equipment_ids',
                 'material_word_ids', 'equipment_word_ids')


def erp_category_ids(env):
    Category = env['coop.resource.category'].sudo()
    roots = Category.search([('parent_id', '=', False),
                             ('name', 'in', ERP_SECTIONS)])
    return set(Category.search([('id', 'child_of', roots.ids)]).ids)


def from_erp(item, category_ids):
    """Мог ли состав этого объявления прийти из ERP владельца."""
    return (item.listing_type == 'offer'
            and item.resource_type == 'material'
            and item.condition != 'used'
            and item.owner_id.is_company
            and item.category_id.id in category_ids)


def load_484(env):
    Resource = env['coop.resource'].sudo().with_context(active_test=False)
    allowed = erp_category_ids(env)
    domain = ['|'] * (len(MAKING_FIELDS) - 1) + [
        (name, '!=', False) for name in MAKING_FIELDS]
    cleared = trimmed = 0
    for item in Resource.search(domain):
        if not from_erp(item, allowed):
            item.write({name: [(5, 0, 0)] for name in MAKING_FIELDS
                        if item[name]})
            cleared += 1
        elif item.manufacturer_ids - item.owner_id:
            # Второй производитель выбирался жребием — оставляем владельца.
            item.manufacturer_ids = [(6, 0, item.owner_id.ids)]
            trimmed += 1
    _logger.info('Состав не из ERP снят у %s, чужой производитель — у %s',
                 cleared, trimmed)
    return cleared, trimmed
