# -*- coding: utf-8 -*-
"""Корень сайта для того, кто уже вошёл.

Лендинг объясняет платформу тому, кто о ней впервые слышит. Участнику,
который уже вошёл, объяснять нечего — ему нужна своя страница. А
получалось наоборот: человек заходил на адрес платформы и упирался в
рассказ о ней, причём попасть оттуда к себе было нечем — в верхнем меню
сайта «Моей страницы» нет.

Владелец 15 сентября 2026: «почему меня вообще после входа перекидывает
на эту страницу, должен быть автопереход на мою страницу».

Лендинг при этом никуда не девается: он нужен и владельцу — смотреть, как
платформа выглядит со стороны. Поэтому у перехода есть отмена: `/?site=1`
показывает лендинг как есть.

Внутри фрейма перехода нет: сайтостроитель открывает корень сайта во
фрейме, а веб-клиент во фрейм не пускается — браузер подставлял страницу
ошибки, и конструктор падал на `onIframeLoad … reading 'body'` (обход
меню 07.10.2026, «Сайт», «Редактор меню», «SEO»).
"""

from odoo import http
from odoo.http import request
from odoo.addons.website.controllers.main import Website


class CoopHome(Website):

    @http.route('/', auth='public', website=True, sitemap=True)
    def index(self, **kw):
        # `site=1` — осознанный просмотр лендинга вошедшим: владельцу
        # нужно видеть, что показывают постороннему.
        in_frame = request.httprequest.headers.get('Sec-Fetch-Dest') == 'iframe'
        if not kw.get('site') and not in_frame:
            user = request.env.user
            if user and not user._is_public() \
                    and user._is_internal():
                return request.redirect('/odoo/my-page')
        return super().index(**kw)

    # Посадочные лендинга — та же страница с другим первым экраном и
    # ролью по умолчанию (макет: Masters, Projects, Orgs). Входа не
    # требуют и вошедшего никуда не уводят: ссылку на посадочную дают
    # тому, кто о платформе ещё не слышал.
    LANDINGS = {'masters': (1, 0), 'projects': (2, 1), 'orgs': (3, 2)}

    @http.route(['/for/%s' % who for who in LANDINGS],
                auth='public', website=True, sitemap=True)
    def coop_landing_for(self, **kw):
        who = request.httprequest.path.rstrip('/').rsplit('/', 1)[-1]
        variant, role = self.LANDINGS[who]
        return request.render('coop_website.coop_landing',
                              {'variant': variant, 'role': role})
