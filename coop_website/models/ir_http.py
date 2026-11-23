# -*- coding: utf-8 -*-
import werkzeug.exceptions

from odoo import models
from odoo.addons.web.controllers.utils import is_user_internal
from odoo.http import request

# Куда уводить. Участник — на свою страницу, все прочие — на лендинг.
COOP_HOME = '/odoo/my-page'
COOP_LANDING = '/'

# Что под `/my` оставить открытым: акт сверки открывается из кабинета
# по ссылке мастера (`l10n_ru_act_rev`), он не портальная оболочка.
COOP_MY_KEEP = ('/my/act_revise',)


def coop_entry_url():
    """Куда отправить вошедшего: участника — домой, остальных — на лендинг."""
    uid = request.session.uid
    if uid and is_user_internal(uid):
        return COOP_HOME
    return COOP_LANDING


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _authenticate(cls, endpoint):
        """Портальной оболочки `/my` на платформе нет (владелец 20.11).

        Штатный Odoo уводит туда всякого невнутреннего: после входа
        (`_login_redirect`), из `/odoo/…` (`web_client`, отсюда адрес
        `/my?subpath=my-page`) и с главной. Человек видел «Мою учётную
        запись» с чужими пунктами меню, и все кнопки вели обратно на неё.

        Закрываем все адреса `/my`, `/my/…` разом, а не по одному
        маршруту: модули добавляют свои (`/my/orders`, `/my/invoices`…),
        и каждый новый снова открыл бы дыру. Ссылки с `access_token` —
        документ, отправленный контрагенту, а не оболочка: их не трогаем.

        Именно на проверке входа, а не позже: маршруты `/my` требуют
        входа, и гостя движок увёл бы на форму входа раньше, чем дошло бы
        до нас, — а гостю место на лендинге.
        """
        path = request.httprequest.path
        if (path == '/my' or path.startswith('/my/')) \
                and not path.startswith(COOP_MY_KEEP) \
                and 'access_token' not in request.httprequest.args:
            # `request.params` здесь ещё не собран — токен берём из адреса.
            werkzeug.exceptions.abort(request.redirect(coop_entry_url(), 303))
        return super()._authenticate(endpoint)
