# -*- coding: utf-8 -*-
"""Приём заявки «Написать нам» с лендинга (решение 438, п. 11).

Форма публичная, поэтому три защиты: токен CSRF (штатный у Odoo),
скрытое поле-ловушка для ботов и предел длины каждого поля. Заявка
заводится от имени системы — у гостя прав на модель нет и не должно быть.
"""
from odoo import http
from odoo.http import request

from ..models.coop_contact import TOPICS

LIMITS = {'name': 120, 'email': 160, 'organization': 200, 'message': 4000}


class CoopContact(http.Controller):

    @http.route('/coop/contact', type='http', auth='public', methods=['POST'],
                website=True, csrf=True, sitemap=False)
    def coop_contact(self, **post):
        # Ловушка: живой человек это поле не видит и не заполняет.
        if post.get('company_site'):
            return request.redirect('/?site=1&sent=1#contact')
        values = {key: (post.get(key) or '').strip()[:limit] for key, limit in LIMITS.items()}
        topic = post.get('topic')
        values['topic'] = topic if topic in dict(TOPICS) else 'other'
        if not (values['name'] and values['email'] and values['message']):
            return request.redirect('/?site=1&sent=0#contact')
        request.env['coop.contact.request'].sudo().create(values)
        return request.redirect('/?site=1&sent=1#contact')


class CoopLegal(http.Controller):
    """Политика, Согласие и Правила сети (решение 438, п. 8) — публичные
    страницы, ссылки на них в подвале и на форме регистрации."""

    @http.route('/privacy', type='http', auth='public', website=True, sitemap=True)
    def coop_privacy(self, **kw):
        return request.render('coop_website.coop_privacy')

    @http.route('/consent', type='http', auth='public', website=True, sitemap=True)
    def coop_consent(self, **kw):
        return request.render('coop_website.coop_consent')

    @http.route('/network-rules', type='http', auth='public', website=True, sitemap=True)
    def coop_network_rules(self, **kw):
        return request.render('coop_website.coop_network_rules')
