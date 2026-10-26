# -*- coding: utf-8 -*-
"""НДФЛ при выплате и возврате пая (решение 513), пример бухгалтера 26.10:
внесено 100 000, начислено 30 000, при выходе ещё 5 000 — 135 000."""
from odoo.tests import tagged

from odoo.addons.coop_base.tests.common import CoopCase
from odoo.addons.coop_tax.models.ndfl import ndfl, scale_tax


@tagged('post_install', '-at_install')
class TestShareNdfl(CoopCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.coop = cls._make_org('Кооператив пробы НДФЛ')
        cls.person = cls._make_person('Пайщик пробы НДФЛ').partner_id

    def _account(self, resident=True, treaty=0.0, base='full'):
        self.coop.coop_ndfl_share_base = base
        self.person.write({'coop_tax_resident': resident, 'coop_tax_treaty_rate': treaty})
        wallet = self.env['coop.wallet'].search([('partner_id', '=', self.person.id)], limit=1) \
            or self.env['coop.wallet'].create({'partner_id': self.person.id})
        account = self.env['coop.share.account'].create(
            {'wallet_id': wallet.id, 'cooperative_id': self.coop.id})
        Move = self.env['coop.share.move']
        for date, kind, amount in (('2026-02-01', 'share', 100000),
                                   ('2026-03-01', 'accrual', 30000),
                                   ('2026-04-01', 'accrual', 5000)):
            Move.create({'account_id': account.id, 'date': date, 'name': kind,
                         'kind': kind, 'amount': amount, 'basis': 'Протокол № 1'})
        return account

    def _return(self, account, amount=-135000, state='confirmed', kind='return'):
        return self.env['coop.share.move'].create({
            'account_id': account.id, 'date': '2026-05-01', 'name': 'Возврат',
            'kind': kind, 'amount': amount, 'basis': 'Заявление', 'state': state})

    def test_shkala(self):
        self.assertEqual(scale_tax(2_400_000), 312_000)
        self.assertEqual(scale_tax(5_000_000), 702_000)
        self.assertEqual(scale_tax(20_000_000), 3_402_000)
        self.assertEqual(scale_tax(50_000_000), 9_402_000)
        tax, rate = ndfl(200_000, earlier_base=2_300_000)
        self.assertEqual(tax, 13_000 + 15_000)
        self.assertEqual(rate, '13–15 %')

    def test_so_vsei_summy(self):
        account = self._account()
        self.assertEqual(account.return_ndfl, 17550)
        move = self._return(account)
        self.assertEqual((move.ndfl_amount, move.net_amount), (17550, 117450))
        self.assertEqual(account.ndfl_withheld, 17550)
        self.assertEqual(account.paid_net, 117450)

    def test_sverh_vnesennogo(self):
        account = self._account(base='excess')
        self.assertEqual(account.return_ndfl, 4550)
        move = self._return(account)
        self.assertEqual((move.ndfl_base, move.ndfl_amount), (35000, 4550))

    def test_vyplata_snachala_iz_nachislennogo(self):
        account = self._account(base='excess')
        payout = self._return(account, amount=-20000, kind='payout')
        self.assertEqual(payout.ndfl_base, 20000)
        rest = self._return(account, amount=-115000)
        self.assertEqual(rest.ndfl_base, 15000)

    def test_nerezident(self):
        self.assertEqual(self._account(resident=False).return_ndfl, 40500)

    def test_po_soglasheniyu(self):
        account = self._account(resident=False, treaty=10)
        self.assertEqual(account.return_ndfl, 13500)

    def test_provedennoe_zastyvaet(self):
        account = self._account()
        move = self._return(account)
        self.coop.coop_ndfl_share_base = 'excess'
        move.date = '2026-05-02'
        self.assertEqual(move.ndfl_amount, 17550)

    def test_zayavlenie_schitaetsya_i_pri_provedenii(self):
        account = self._account(base='excess')
        move = self._return(account, state='requested')
        self.assertEqual(move.ndfl_amount, 4550)
        self.coop.coop_ndfl_share_base = 'full'
        move.action_confirm()
        self.assertEqual(move.ndfl_amount, 17550)
