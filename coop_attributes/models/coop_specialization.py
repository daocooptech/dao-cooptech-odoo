# -*- coding: utf-8 -*-
from odoo import api, fields, models

_DEPENDS = (
    'sequence', 'attribute_id', 'option_ids',
    'attribute_id.name', 'attribute_id.code', 'attribute_id.active',
    'attribute_id.value_type', 'attribute_id.unit',
    'attribute_id.show_on_card', 'attribute_id.option_ids',
    'attribute_id.option_ids.name', 'attribute_id.option_ids.code',
    'attribute_id.option_ids.sequence', 'attribute_id.option_ids.active',
)


class CoopSpecializationCategory(models.Model):
    _inherit = 'coop.specialization.category'

    attribute_assignment_ids = fields.One2many(
        'coop.attribute.assignment', 'specialization_category_id',
        string='Характеристики сферы')


class CoopSpecialization(models.Model):
    """Специализация знает, какие поля у вакансии и навыка по ней (№ 483)."""

    _inherit = 'coop.specialization'

    attribute_assignment_ids = fields.One2many(
        'coop.attribute.assignment', 'specialization_id',
        string='Характеристики специализации')
    attribute_definition = fields.PropertiesDefinition(
        string='Описание характеристик',
        compute='_compute_attribute_definition', store=True)

    @api.depends('category_id',
                 *['attribute_assignment_ids.%s' % d for d in _DEPENDS],
                 *['category_id.attribute_assignment_ids.%s' % d
                   for d in _DEPENDS])
    def _compute_attribute_definition(self):
        for record in self:
            # По коду: повешенное и на сферу, и на специализацию движок
            # отверг бы целиком; побеждает более частное.
            definition = {}
            sudo = record.sudo()
            for assignment in (
                    list(sudo.category_id.attribute_assignment_ids.sorted(
                        lambda a: (a.sequence, a.id)))
                    + list(sudo.attribute_assignment_ids.sorted(
                        lambda a: (a.sequence, a.id)))):
                if assignment.attribute_id.active:
                    definition[assignment.attribute_id.code] = \
                        assignment._definition_item()
            record.attribute_definition = list(definition.values())
