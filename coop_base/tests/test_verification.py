# -*- coding: utf-8 -*-
"""Ступень доверия — следствие фактов, а не отдельно выставляемое поле.

Проверяется именно то, о чём предупреждает комментарий в модели:
подтверждённая личность без подтверждённого телефона всё равно даёт
«личность». Правило неочевидное, и при первой же переделке вычисления
его легко потерять — снаружи разница видна только тем, что участник
вдруг не может завести проект.
"""
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import CoopCase


@tagged('post_install', '-at_install')
class TestVerificationLevel(CoopCase):

    def test_novyy_uchastnik_nichego_ne_podtverdil(self):
        person = self._make_person('Никто Непроверенный')
        self.assertEqual(person.partner_id.coop_verification_level, 'none')
        self.assertFalse(person.partner_id.coop_level_at_least('account'))

    def test_pochta_daet_pervuyu_stupen(self):
        person = self._make_person('Почтовый Участник')
        self._confirm(person.partner_id, 'email', method='self')
        self.assertEqual(person.partner_id.coop_verification_level, 'account')
        self.assertTrue(person.partner_id.coop_level_at_least('account'))
        self.assertFalse(person.partner_id.coop_level_at_least('contact'))

    def test_lichnost_bez_telefona_vsyo_ravno_lichnost(self):
        """Высшая достигнутая, а не первая пропущенная.

        Очный приём в кооперативе — обычное дело, и телефон там никто не
        подтверждает. Понижать такого участника до «не подтверждён» было
        бы нелепо, но именно это получается, если считать ступень по
        первому пропуску.
        """
        person = self._make_person('Очный Участник')
        self._confirm(person.partner_id, 'identity', method='inperson')
        self.assertEqual(person.partner_id.coop_verification_level, 'identity')
        self.assertTrue(person.partner_id.coop_level_at_least('contact'))

    def test_svedeniya_v_reestre_ravny_lichnosti(self):
        """Для организации сверка с ЕГРЮЛ — то же, что личность у человека."""
        org = self._make_org('ООО «Проверенное»')
        self._confirm(org, 'registry', method='registry')
        self.assertEqual(org.coop_verification_level, 'identity')

    def test_nepodtverzhdyonnoe_ne_schitaetsya(self):
        person = self._make_person('Ожидающий Проверки')
        self.Verification.create({
            'partner_id': person.partner_id.id,
            'kind': 'identity',
            'method': 'esia',
            'state': 'pending',
        })
        self.assertEqual(person.partner_id.coop_verification_level, 'none')

    def test_otkaz_obyasnyaet_chego_ne_hvataet(self):
        """Отказ без объяснения человек читает как поломку платформы."""
        person = self._make_person('Недобравший Ступень')
        self._confirm(person.partner_id, 'email', method='self')
        with self.assertRaises(UserError) as caught:
            person.partner_id.coop_require_level('identity', 'завести проект')
        text = str(caught.exception)
        self.assertIn('завести проект', text)
        self.assertIn('Личность', text)

    def test_dostatochnaya_stupen_propuskaet(self):
        person = self._make_person('Дотянувший Ступень')
        self._confirm(person.partner_id, 'identity')
        self.assertTrue(
            person.partner_id.coop_require_level('identity', 'завести проект'))
