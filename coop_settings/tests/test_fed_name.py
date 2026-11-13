# -*- coding: utf-8 -*-
"""Имя автора на другом узле — только с согласия (решение 658 п. 2)."""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFedName(TransactionCase):

    def test_hidden_by_default(self):
        person = self.env['res.partner'].create({'name': 'Анна Петрова'})
        self.assertFalse(person.coop_fed_show_name)
        self.assertEqual(person._coop_fed_author_name('Кооператив «Сад»'),
                         'Участник узла Кооператив «Сад»')

    def test_shown_with_consent(self):
        person = self.env['res.partner'].create({
            'name': 'Анна Петрова', 'coop_fed_show_name': True})
        self.assertEqual(person._coop_fed_author_name('Кооператив «Сад»'),
                         'Анна Петрова')
