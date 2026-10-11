# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDealSpec(TransactionCase):
    """Без спецификации сделку не согласовать (владелец 11.10.2026)."""

    def test_agree_requires_spec(self):
        user = self.env['res.users'].create({
            'name': 'Сторона пробы спецификации', 'login': 'deal-spec-side',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        deal = self.env['coop.deal'].create({
            'name': 'Поставка досок',
            'party_a_id': user.partner_id.id,
            'party_b_id': self.env['res.partner'].create({'name': 'Вторая сторона'}).id,
        })
        level = patch.object(type(self.env['res.partner']), 'coop_require_level',
                             return_value=True)
        with level, self.assertRaises(UserError):
            deal.with_user(user).action_agree()
        deal.line_ids = [(0, 0, {'name': 'Доска обрезная', 'quantity': 2.0,
                                 'price_unit': 700.0})]
        with level:
            deal.with_user(user).action_agree()
        self.assertEqual(deal.state, 'agreed')
