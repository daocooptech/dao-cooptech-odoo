# -*- coding: utf-8 -*-
"""Маршрут переписки и чек-лист подключения узла (решения 501, 502).

Переписка с участием граждан и организаций России — только узлам в России
(ч. 3 ст. 10.1 149-ФЗ); события сделок ходят как прежде.
"""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

RU_PEER = 'did:web:hub-ru.koopeh.test'
CN_PEER = 'did:web:node-cn.koopeh.test'
BY_PEER = 'did:web:node-by.koopeh.test'


@tagged('post_install', '-at_install')
class TestRoute(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.identity = cls.env['coop.fed.identity']._ensure()
        cls.identity.country_id = cls.env.ref('base.ru')
        Peer = cls.env['coop.fed.peer']
        cls.ru_peer = Peer.create({'did': RU_PEER, 'country_id': cls.env.ref('base.ru').id})
        cls.cn_peer = Peer.create({'did': CN_PEER, 'country_id': cls.env.ref('base.cn').id})
        cls.by_peer = Peer.create({'did': BY_PEER, 'country_id': cls.env.ref('base.by').id})
        Partner = cls.env['res.partner']
        cls.russian = Partner.create({'name': 'Гражданин России',
                                      'coop_citizenship_id': cls.env.ref('base.ru').id})
        cls.chinese = Partner.create({'name': 'Гражданин Китая',
                                      'coop_citizenship_id': cls.env.ref('base.cn').id})
        cls.Event = cls.env['coop.fed.event']

    def test_perepiska_s_rossiyaninom_ne_uhodit_za_rubezh(self):
        with self.assertRaisesRegex(UserError, '149-ФЗ'):
            self.Event._enqueue('message.sent', 'thread-1', {'text': 'привет'},
                                to=[CN_PEER], participants=self.russian | self.chinese)

    def test_perepiska_s_rossiyaninom_idet_rossiyskomu_hubu(self):
        event = self.Event._enqueue('message.sent', 'thread-2', {'text': 'привет'},
                                    to=[RU_PEER], participants=self.russian | self.chinese)
        self.assertEqual(event.status, 'pending')

    def test_obshchim_sobytiem_nelzya(self):
        with self.assertRaises(UserError):
            self.Event._enqueue('message.sent', 'thread-3', {'text': 'всем'},
                                participants=self.russian)

    def test_bez_rossiyan_mozhno_za_rubezh(self):
        event = self.Event._enqueue('message.sent', 'thread-4', {'text': '你好'},
                                    to=[CN_PEER], participants=self.chinese)
        self.assertEqual(event.status, 'pending')

    def test_sobytiya_sdelok_hodyat_kak_prezhde(self):
        event = self.Event._enqueue('deal.proposed', 'deal-1', {'amount': '100.00'},
                                    to=[CN_PEER])
        self.assertEqual(event.status, 'pending')

    def test_chek_list_notifikatsiya_eaes_tolko_vne_soyuza(self):
        self.assertTrue(self.cn_peer.eaeu_notice_needed)
        self.assertFalse(self.by_peer.eaeu_notice_needed)
        self.assertTrue(self.cn_peer.messages_foreign)
        self.assertFalse(self.ru_peer.messages_foreign)
        self.by_peer.check_crypto = True
        self.assertTrue(self.by_peer.checklist_done)
        self.cn_peer.check_crypto = True
        self.assertFalse(self.cn_peer.checklist_done)
        self.cn_peer.check_eaeu_notice = True
        self.assertTrue(self.cn_peer.checklist_done)
