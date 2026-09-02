# -*- coding: utf-8 -*-
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.http import request

# Язык платформы по умолчанию. Решение владельца: если человек не выбрал
# язык при регистрации, платформа говорит с ним по-русски.
DEFAULT_LANG = 'ru_RU'


class CoopAuthSignupHome(AuthSignupHome):
    """Выбор языка платформы при регистрации.

    Штатная регистрация Odoo берёт язык из адреса страницы: на какой
    версии сайта человек оказался, на такой и заводится. Это работает,
    пока сайт один и переключателя языков нет, — а у нас человек может
    прийти по ссылке с любой страницы и получить язык, которого не
    выбирал.

    Поэтому язык спрашивается явным полем, а если поле не заполнено или
    в нём что-то неизвестное — ставится русский. Умолчание здесь не
    формальность: платформа российская, и большинство участников
    русскоязычны.
    """

    def get_auth_signup_qcontext(self):
        qcontext = super().get_auth_signup_qcontext()
        # Список для выпадающего поля. Только установленные языки: предлагать
        # то, чего на узле нет, значит обещать перевод, которого не будет.
        qcontext['coop_langs'] = request.env['res.lang'].sudo().get_installed()
        qcontext['coop_default_lang'] = self._coop_default_lang()
        # Что показать выбранным. Именно свой ключ, а не `lang`: в `lang`
        # штатная регистрация кладёт язык страницы, на которой человек
        # оказался, и предвыбранным оказался бы он — то есть язык, которого
        # человек не выбирал. По решению владельца предвыбран русский, пока
        # человек не выбрал другое.
        qcontext['coop_selected_lang'] = (
            request.params.get('lang') or qcontext['coop_default_lang'])
        return qcontext

    def _coop_default_lang(self):
        installed = [code for code, _name in request.env['res.lang'].sudo().get_installed()]
        if DEFAULT_LANG in installed:
            return DEFAULT_LANG
        return installed[0] if installed else 'en_US'

    def _prepare_signup_values(self, qcontext):
        values = super()._prepare_signup_values(qcontext)
        installed = [code for code, _name in request.env['res.lang'].sudo().get_installed()]
        chosen = qcontext.get('lang')
        values['lang'] = chosen if chosen in installed else self._coop_default_lang()
        return values
