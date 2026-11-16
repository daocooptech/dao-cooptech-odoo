# -*- coding: utf-8 -*-
"""Лента новостей проекта — стена участников (владелец 14.11.2026, № 446).

Писать могут только участники (команда проекта), адресатов «Кому» нет,
писем нет: первая запись в «Общественной библиотеке» висела с ошибкой
доставки — чаттер подставил в адресаты инициатора-организацию.
"""
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import CoopProjectCase


@tagged('post_install', '-at_install')
class TestProjectWall(CoopProjectCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.giver = cls._make_person('Вкладчик Стены')
        cls.stranger = cls._make_person('Читатель Стены')
        cls.project = cls._make_project(name='Стена участников', state='gathering')
        cls._make_offer(cls.project, cls.giver, value=10000).with_user(
            cls.initiator).action_accept()

    def _post(self, user, **kw):
        return self.project.with_user(user).message_post(
            body='Новость', message_type='comment',
            subtype_xmlid='mail.mt_comment', **kw)

    def test_uchastniki_pishut(self):
        self._post(self.initiator)
        self._post(self.giver)

    def test_chuzhoy_ne_pishet(self):
        with self.assertRaises(AccessError):
            self._post(self.stranger)

    def test_chuzhoy_ne_pishet_i_cherez_sudo(self):
        # Поле ленты публикует через `sudo()` (`/mail/message/post`).
        with self.assertRaises(AccessError):
            self.project.with_user(self.stranger).sudo().message_post(
                body='Мимо поля', message_type='comment',
                subtype_xmlid='mail.mt_comment')

    def test_izvescheniya_kak_prezhde(self):
        self.project.with_user(self.stranger).sudo().message_post(
            body='Служебное извещение')

    def test_net_adresatov_i_pisem(self):
        self.assertEqual(self.project._message_get_suggested_recipients(), [])
        org = self.env['res.partner'].create({'name': 'АНО без учётной записи'})
        message = self._post(self.initiator, partner_ids=org.ids)
        self.assertFalse(message.notification_ids)

    def test_otmechennomu_vo_vhodyashchie(self):
        message = self._post(self.initiator, partner_ids=self.stranger.partner_id.ids)
        self.assertEqual(message.notification_ids.res_partner_id, self.stranger.partner_id)
        self.assertEqual(message.notification_ids.notification_type, 'inbox')
