# -*- coding: utf-8 -*-
"""Картинки записей — в кэш браузера.

Измерено 15 сентября 2026 на боевой установке: страница участника
доходит до готовности за 6,0 с, из восьмидесяти запросов тридцать девять
— это `/web/image/…`. Передают они 10 КБ на всех: каждый ответ приходит
с кодом 304, «не изменилось». То есть браузер не берёт ни байта, но на
каждую картинку тратит полный поход до сервера и обратно.

Почему так. Odoo даёт долгий срок хранения только адресам с меткой
версии — `?unique=…`, см. `web/controllers/binary.py`, ветка `if unique`.
Без метки срок не задаётся вовсе, и Werkzeug пишет `no-cache`: браузер
обязан переспрашивать. Метки нет ни у одного из тридцати пяти наших
адресов, и поставить её негде — в карточке каталога аватар берётся по
ссылке на партнёра, а даты его изменения в карточке нет.

Метка и не нужна: ответ и так несёт ETag, а в нём — отпечаток
содержимого. Сменится картинка — сменится ETag. Значит, достаточно
разрешить браузеру не спрашивать какое-то время.

Своя карточка — исключение. Человек, сменивший себе фотографию, должен
увидеть её сразу, иначе решит, что не загрузилось. Чужие аватары
обновятся в течение часа, и этого никто не заметит.

Срок хранения — `coop.image_cache_seconds`, чтобы менять его без выкатки.
Хранилище всегда частное (`private`): картинки записей закрыты правами
доступа, и общим кэшам их отдавать нельзя.
"""

from odoo import http
from odoo.addons.web.controllers.binary import Binary

# Десять минут, а не час. Час проверен на себе в тот же день: после
# перезаливки демо-данных снимки вакансий обновились в базе, а на экране
# ещё держались прежние заглушки — браузеру было велено не спрашивать.
# Десяти минут хватает, чтобы убрать переспрашивание внутри одного
# сеанса работы (ради него всё и делалось), и мало, чтобы застой успел
# кого-то запутать.
DEFAULT_DEADLINE = 600


class CoopBinary(Binary):

    @http.route()
    def content_image(self, *args, **kwargs):
        answer = super().content_image(*args, **kwargs)
        if kwargs.get('unique') or kwargs.get('nocache'):
            # Об этих Odoo уже позаботилась: первым выдан вечный срок,
            # вторым он снят намеренно.
            return answer
        if answer.status_code not in (200, 304):
            return answer
        deadline = self._coop_image_max_age(kwargs)
        if not deadline:
            return answer
        answer.cache_control.pop('no-cache', None)
        answer.cache_control.pop('public', None)
        answer.cache_control.private = True
        answer.cache_control.max_age = deadline
        return answer

    def _coop_image_max_age(self, kwargs):
        """Сколько браузеру можно не переспрашивать про эту картинку."""
        env = http.request.env
        param = env['ir.config_parameter'].sudo().get_param(
            'coop.image_cache_seconds', DEFAULT_DEADLINE)
        try:
            deadline = int(param)
        except (TypeError, ValueError):
            deadline = DEFAULT_DEADLINE
        if deadline <= 0:
            return 0
        if self._coop_is_my_own(kwargs):
            return 0
        return deadline

    def _coop_is_my_own(self, kwargs):
        """Это моя собственная карточка?

        Своя фотография должна меняться на глазах. Чужая — может
        подождать час.
        """
        if kwargs.get('model') != 'res.partner':
            return False
        try:
            who = int(kwargs.get('id') or 0)
        except (TypeError, ValueError):
            return False
        if not who:
            return False
        user = http.request.env.user
        mine = user.partner_id.ids
        # Действие от имени организации: её карточка тоже «своя».
        if 'coop_actor_partner_ids' in user._fields:
            mine = mine + user.coop_actor_partner_ids.ids
        return who in mine
