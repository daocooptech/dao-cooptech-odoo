# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAccountSnapshot(TransactionCase):

    def test_snapshot_restores_year_once(self):
        Snapshot = self.env['coop.account.snapshot']
        user = self.env['res.users'].create({'name': 'Снимок Проверочный', 'login': 'snap-check'})
        partner = user.partner_id
        Snapshot._cron_snapshot()
        rows = Snapshot.search([('partner_id', '=', partner.id)])
        today = fields.Date.context_today(Snapshot)
        # Одиннадцать прошлых месяцев по записям и снимок на сегодня.
        self.assertEqual(len(rows.filtered('restored')), 11)
        self.assertEqual(rows.filtered(lambda r: not r.restored).date, today)
        # Повторный прогон не множит историю и не дублирует сегодняшний снимок.
        Snapshot._cron_snapshot()
        self.assertEqual(Snapshot.search_count([('partner_id', '=', partner.id)]), 12)

    def test_spark_reads_snapshots(self):
        Snapshot = self.env['coop.account.snapshot']
        user = self.env['res.users'].create({'name': 'Искра Проверочная', 'login': 'spark-check'})
        partner = user.partner_id
        y, m = partner._coop_year_months()[-2]
        Snapshot.create({'partner_id': partner.id, 'date': '%04d-%02d-10' % (y, m), 'friends': 7})
        Snapshot.create({'partner_id': partner.id, 'date': '%04d-%02d-20' % (y, m), 'friends': 9})
        label = partner.coop_spark_friends
        # Прошлый месяц — последний снимок в нём, текущий — число плитки.
        self.assertIn('ход за год — 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 9, %d' % partner.coop_friend_count,
                      label)
