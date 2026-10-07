import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.http.session import finalize

_logger = logging.getLogger(__name__)


class CoopLoginAs(http.Controller):
    """Вход администратора под человеком и возврат к себе (решение 450).

    Смена пользователя — штатной `finalize` движка, той же, что завершает
    обычный вход: сессия пересоздаётся, токен считается заново, контекст
    берётся из настроек человека. Своей работы с токенами здесь нет.
    Кто вошёл под кем — в сессии (`coop_impersonator_uid`) и в журнале.
    """

    @http.route('/coop/login_as/<int:user_id>', type='http', auth='user', methods=['GET'])
    def login_as(self, user_id, ts=None, token=None, **kwargs):
        admin = request.env.user
        try:
            user = request.env['res.users']._coop_login_as_check(user_id, ts or 0, token)
        except (UserError, ValueError) as error:
            return request.make_response(str(error), status=403,
                                         headers=[('Content-Type', 'text/plain; charset=utf-8')])
        _logger.warning('Вход под другим человеком: %s (%s) -> %s (%s)',
                        admin.login, admin.id, user.login, user.id)
        # Возврат — всегда к тому, кто входил первым: «войти как» из-под
        # уже чужой учётки невозможно (там нет полномочий администратора),
        # но и цепочку на всякий случай не наращиваем.
        request.session.setdefault('coop_impersonator_uid', admin.id)
        request.session['pre_login'] = user.login
        request.session['pre_uid'] = user.id
        finalize(request.session, request.env)
        return request.redirect('/odoo')

    @http.route('/coop/login_back', type='http', auth='user', methods=['GET'])
    def login_back(self, **kwargs):
        admin_id = request.session.get('coop_impersonator_uid')
        if not admin_id:
            return request.redirect('/odoo')
        admin = request.env['res.users'].sudo().browse(admin_id).exists()
        if not admin or not admin.active:
            request.session.pop('coop_impersonator_uid', None)
            return request.redirect('/web/session/logout')
        _logger.warning('Возврат к себе: %s -> %s (%s)', request.env.user.login, admin.login, admin.id)
        request.session.pop('coop_impersonator_uid', None)
        request.session['pre_login'] = admin.login
        request.session['pre_uid'] = admin.id
        finalize(request.session, request.env)
        return request.redirect('/odoo')
