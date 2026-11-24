# -*- coding: utf-8 -*-
from odoo import fields, http
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.web.controllers.utils import is_user_internal
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools.binary import BinaryBytes
from odoo.tools.mimetypes import guess_mimetype

from ..models.ir_http import COOP_HOME, coop_entry_url

# Язык платформы по умолчанию. Решение владельца: если человек не выбрал
# язык при регистрации, платформа говорит с ним по-русски.
DEFAULT_LANG = 'ru_RU'

# Второй шаг регистрации — «Расскажите о себе» (№ 377, `SignupPage`).
ABOUT_URL = '/web/signup/about'
ABOUT_LIMIT = 280
PHOTO_LIMIT = 8 * 1024 * 1024
PHOTO_TYPES = ('image/jpeg', 'image/png', 'image/webp', 'image/gif')

# «Что вам интересно»: с какого раздела начать. Не хранится — только
# подсказка на этой странице.
INTERESTS = [
    ('resources', 'Вещи и сырьё', 'Ресурсы', '/odoo/resources'),
    ('skills', 'Навыки и услуги', 'Навыки', '/odoo/skills'),
    ('vacancies', 'Работа', 'Вакансии', '/odoo/vacancies'),
    ('projects', 'Проекты', 'Проекты', '/odoo/projects'),
    ('orgs', 'Организации', 'Организации', '/odoo/orgs'),
    ('people', 'Знакомства', 'Люди', '/odoo/people'),
    ('communities', 'Сообщества', 'Сообщества', '/odoo/communities'),
]


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
        # На странице один пароль с показом (эталон `SignupPage`), движок
        # ждёт два. Форма сброса пароля своё второе поле сохраняет.
        if request.httprequest.method == 'POST':
            request.params.setdefault('confirm_password', request.params.get('password'))
        response = super().web_auth_signup(*args, **kw)
        # Шаг 2 — только новому участнику и только если он не шёл по
        # ссылке на конкретную страницу.
        if (request.httprequest.method == 'POST' and not request.params.get('redirect')
                and response.status_code in (302, 303)
                and request.session.uid and is_user_internal(request.session.uid)):
            return request.redirect(ABOUT_URL, 303)
        return response

    @http.route(ABOUT_URL, type='http', auth='user', website=True, sitemap=False, methods=['GET', 'POST'])
    def coop_signup_about(self, **post):
        if not is_user_internal(request.session.uid):
            return request.redirect(coop_entry_url(), 303)
        partner = request.env.user.partner_id
        qcontext = {
            'partner': partner,
            'city': partner.city or '',
            'about': partner.coop_about or '',
            'about_limit': ABOUT_LIMIT,
            'cities': request.env['res.partner'].coop_city_suggestions(),
            'interests': INTERESTS,
            'home_url': COOP_HOME,
        }
        if request.httprequest.method == 'POST':
            qcontext['city'] = (post.get('city') or '').strip()
            qcontext['about'] = (post.get('about') or '').strip()
            try:
                vals = self._coop_about_values(qcontext, post.get('photo'))
            except UserError as error:
                qcontext['error'] = error.args[0]
            else:
                # Пустое поле ничего не стирает: шаг можно пропустить.
                # `sudo` — запись только в свою карточку и только этих полей.
                if vals:
                    partner.sudo().write(vals)
                return request.redirect(COOP_HOME, 303)
        return request.render('coop_website.signup_about', qcontext)

    def _coop_about_values(self, qcontext, photo):
        if len(qcontext['about']) > ABOUT_LIMIT:
            raise UserError('«Чем занимаетесь» — не длиннее %d знаков.' % ABOUT_LIMIT)
        vals = {}
        if qcontext['city']:
            vals['city'] = qcontext['city'][:100]
        if qcontext['about']:
            vals['coop_about'] = qcontext['about']
        if photo:
            data = photo.read(PHOTO_LIMIT + 1)
            if len(data) > PHOTO_LIMIT:
                raise UserError('Фото больше 8 МБ — выберите файл поменьше.')
            # SVG под `sudo` движок пропустил бы как есть — берём только снимки.
            if data:
                if guess_mimetype(data) not in PHOTO_TYPES:
                    raise UserError('Фото — только JPEG, PNG, WebP или GIF.')
                vals['image_1920'] = BinaryBytes(data)
        return vals

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
