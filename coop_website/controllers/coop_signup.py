# -*- coding: utf-8 -*-
from odoo import fields, http
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.exceptions import UserError
from odoo.http import request

from ..models.ir_http import coop_entry_url

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

    def web_auth_signup(self, *args, **kw):
        """Регистрация без письма, пока почта не настроена.

        Решение владельца от 15 сентября 2026: на время испытаний
        участник заводит учётную запись и сразу входит по логину и
        паролю. Письмо о заведённой записи Odoo отправляет в том же
        запросе, и без исходящего сервера отправка падает — человек
        видит ошибку, хотя запись уже создана.

        Включается обратно одним параметром: `coop.signup_send_email`
        в значении `True`. Умолчание — не отправлять: узел без почты
        должен работать, а не выглядеть сломанным.
        """
        # Уже вошедшему форма регистрации ни к чему — туда же, куда и
        # с формы входа (см. `web_login`).
        if request.httprequest.method == 'GET' and request.session.uid:
            return request.redirect(coop_entry_url(), 303)
        if not self._coop_signup_mail_enabled():
            request.update_context(coop_skip_signup_mail=True)
        return super().web_auth_signup(*args, **kw)

    @http.route()
    def web_login(self, redirect=None, **kw):
        """Без страницы «Вы уже вошли в систему» (владелец 20.11).

        Штатно вошедший, открывший `/web/login` без `redirect`, видит
        форму входа с этой плашкой — тупик, из которого не уйти. Участника
        ведём на его страницу, прочих — на лендинг. С `redirect` движок
        сам уводит по нему, это не трогаем.
        """
        if request.httprequest.method == 'GET' and request.session.uid and not redirect:
            return request.redirect(coop_entry_url(), 303)
        return super().web_login(redirect=redirect, **kw)

    def _coop_signup_mail_enabled(self):
        value = request.env['ir.config_parameter'].sudo().get_str('coop.signup_send_email') or 'False'
        return str(value).strip().lower() in ('1', 'true', 'да')

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

    def _prepare_signup_values(self, qcontext, **kwargs):
        # `**kwargs` — движок 20.0 передаёт `validate_email=…`; без него
        # регистрация падала с 500 у всех (14.11–22.11).
        values = super()._prepare_signup_values(qcontext, **kwargs)
        installed = [code for code, _name in request.env['res.lang'].sudo().get_installed()]
        chosen = qcontext.get('lang')
        values['lang'] = chosen if chosen in installed else self._coop_default_lang()
        return values

    def do_signup(self, qcontext, do_login=True):
        """Регистрация только с согласием на обработку персональных данных.

        Галочка — отдельная строка, не отмечена заранее (ч. 1 ст. 9 152-ФЗ
        в ред. 156-ФЗ). Без неё учётная запись не заводится; с ней —
        записываются время, адрес и версия текста согласия.
        """
        if not request.params.get('pd_consent'):
            raise UserError('Чтобы зарегистрироваться, отметьте согласие на обработку персональных данных.')
        super().do_signup(qcontext, do_login=do_login)
        User = request.env['res.users'].sudo()
        user = User.search(User._get_login_domain(qcontext.get('login')),
                           order=User._get_login_order(), limit=1)
        if user:
            version = request.env['ir.config_parameter'].sudo().get_str(
                'coop_website.legal_date') or '29.09.2026'
            user.write({
                'coop_pd_consent_at': fields.Datetime.now(),
                'coop_pd_consent_ip': request.httprequest.remote_addr,
                'coop_pd_consent_version': version,
            })
            request.env.cr.commit()
