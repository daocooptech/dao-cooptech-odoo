# -*- coding: utf-8 -*-
import base64
import re

from odoo.tests import HttpCase, tagged

# Снимок 1×1.
GIF = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')


@tagged('post_install', '-at_install')
class TestSignupPage(HttpCase):
    """Страница регистрации: один пароль, согласие, шаг «Расскажите о себе»."""

    def setUp(self):
        super().setUp()
        self.env['website'].search([]).write({'auth_signup_uninvited': 'b2c'})

    def _csrf(self, url):
        page = self.url_open(url)
        self.assertEqual(page.status_code, 200)
        return page.text, re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)

    def _signup(self, **extra):
        text, token = self._csrf('/web/signup')
        self.assertNotIn('name="confirm_password"', text)
        self.assertLess(text.index('name="lang"'), text.index('name="pd_consent"'))
        data = {'csrf_token': token, 'name': 'Проверка Регистрации', 'login': 'signup377@example.com',
                'password': 'Proverka-377-x', **extra}
        return self.url_open('/web/signup', data=data, allow_redirects=False)

    def _user(self):
        return self.env['res.users'].search([('login', '=', 'signup377@example.com')])

    def test_consent_required(self):
        response = self._signup()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self._user())

    def test_two_steps(self):
        response = self._signup(pd_consent='1')
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers['Location'].endswith('/web/signup/about'))
        user = self._user()
        self.assertTrue(user.coop_pd_consent_at)

        _text, token = self._csrf('/web/signup/about')
        bad = self.url_open('/web/signup/about', allow_redirects=False,
                            data={'csrf_token': token, 'city': 'Казань'},
                            files={'photo': ('a.png', b'<svg xmlns="http://www.w3.org/2000/svg"/>', 'image/png')})
        self.assertEqual(bad.status_code, 200)
        self.assertFalse(user.partner_id.city)

        done = self.url_open('/web/signup/about', allow_redirects=False,
                             data={'csrf_token': token, 'city': ' Казань ', 'about': 'Столяр'},
                             files={'photo': ('a.gif', GIF, 'image/gif')})
        self.assertEqual(done.status_code, 303)
        self.assertTrue(done.headers['Location'].endswith('/odoo/my-page'))
        user.invalidate_recordset()
        self.assertEqual(user.partner_id.city, 'Казань')
        self.assertEqual(user.partner_id.coop_about, 'Столяр')
        self.assertTrue(user.partner_id.image_1920)

        # Пустая форма ничего не стирает.
        self.url_open('/web/signup/about', data={'csrf_token': token}, allow_redirects=False)
        user.invalidate_recordset()
        self.assertEqual(user.partner_id.city, 'Казань')

    def test_redirect_skips_about(self):
        response = self._signup(pd_consent='1', redirect='/odoo/projects')
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers['Location'].endswith('/odoo/projects'))

    def test_about_needs_login(self):
        response = self.url_open('/web/signup/about', allow_redirects=False)
        self.assertIn('/web/login', response.headers.get('Location', ''))
