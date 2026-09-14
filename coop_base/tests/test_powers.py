# -*- coding: utf-8 -*-
"""Полномочия в организации: три списка вместо одного.

Пока список был один, бухгалтер получал доступ к публикациям, а
специалист по маркетингу — к счетам. Разъехаться заново это может от
любой правки вычисления, и снаружи расхождение не видно: человек просто
получает лишнее и молчит об этом.
"""
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import CoopCase


@tagged('post_install', '-at_install')
class TestPowers(CoopCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.org = cls._make_org('ПК «Полномочный»')
        cls.publisher = cls._make_person('Издающий Участник')
        cls.treasurer = cls._make_person('Казначейский Участник')
        cls.outsider = cls._make_person('Посторонний Участник')
        cls._join(cls.publisher, cls.org, powers=('publish',))
        cls._join(cls.treasurer, cls.org, powers=('treasury',))

    def test_sam_sebe_vsegda_da(self):
        """У себя человек вправе всё, членство для этого не нужно."""
        self.assertTrue(self.outsider.coop_has_power(
            'treasury', self.outsider.partner_id))

    def test_polnomochie_ne_rasprostranyaetsya_na_sosednee(self):
        self.assertTrue(self.publisher.coop_has_power('publish', self.org))
        self.assertFalse(self.publisher.coop_has_power('treasury', self.org))
        self.assertTrue(self.treasurer.coop_has_power('treasury', self.org))
        self.assertFalse(self.treasurer.coop_has_power('publish', self.org))

    def test_u_postoronnego_net_nichego(self):
        self.assertFalse(self.outsider.coop_has_power('publish', self.org))

    def test_spiski_raznye(self):
        """Издатель в списке издателей, но не в списке распорядителей."""
        self.assertIn(self.org, self.publisher.coop_publisher_partner_ids)
        self.assertNotIn(self.org, self.publisher.coop_treasury_partner_ids)
        self.assertIn(self.org, self.treasurer.coop_treasury_partner_ids)
        self.assertNotIn(self.org, self.treasurer.coop_publisher_partner_ids)

    def test_svoy_profil_vsegda_v_spiskah(self):
        for field in ('coop_actor_partner_ids', 'coop_publisher_partner_ids',
                      'coop_treasury_partner_ids'):
            self.assertIn(self.outsider.partner_id, self.outsider[field],
                          '%s не содержит собственный профиль' % field)

    def test_perepiska_ne_delaet_predstavitelem(self):
        """«Переписка» — не исполнительное полномочие.

        Писать от имени организации можно, не владея ни одной её
        записью; в список «от чьего имени можно действовать» такое
        членство попадать не должно.
        """
        writer = self._make_person('Пишущий Участник')
        self._join(writer, self.org, powers=('represent',))
        self.assertNotIn(self.org, writer.coop_actor_partner_ids)

    def test_prekrashchennoe_chlenstvo_ne_dayot_prav(self):
        leaver = self._make_person('Выбывший Участник')
        membership = self._join(leaver, self.org, powers=('publish',))
        self.assertIn(self.org, leaver.coop_publisher_partner_ids)
        membership.state = 'ended'
        leaver.invalidate_recordset()
        self.assertNotIn(self.org, leaver.coop_publisher_partner_ids)
        self.assertFalse(leaver.coop_has_power('publish', self.org))

    def test_zayavlenie_eshchyo_ne_chlenstvo(self):
        applicant = self._make_person('Подавший Заявление')
        self._join(applicant, self.org, powers=('publish',), state='applied')
        self.assertNotIn(self.org, applicant.coop_publisher_partner_ids)

    def test_deystvovat_ot_chuzhogo_imeni_nelzya(self):
        with self.assertRaises(ValidationError):
            self.outsider.coop_acting_as_id = self.org

    def test_deystvuyushchiy_partnyor_po_umolchaniyu_sam(self):
        self.assertEqual(self.publisher._coop_acting_partner(),
                         self.publisher.partner_id)
        self.publisher.coop_acting_as_id = self.org
        self.assertEqual(self.publisher._coop_acting_partner(), self.org)
