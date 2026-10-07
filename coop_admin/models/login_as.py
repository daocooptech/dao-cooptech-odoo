import time

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools.misc import consteq, hmac

# Решение 450, вариант 1 (владелец 07.10.2026: «1 вариант»): администратор
# входит под любым человеком кнопкой «Войти как», без паролей. Паролей
# демо-людей не знает никто, и посторонний за чужого не войдёт: кнопка и
# адрес работают только у администратора с включёнными полномочиями.
LOGIN_AS_SCOPE = 'coop-login-as'
LOGIN_AS_TTL = 120  # секунд: ссылка одноразовая по смыслу, а не навсегда


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def action_coop_login_as(self):
        """Ссылка входа под человеком — с подписью и сроком.

        Подпись нужна затем, что вход идёт обычным переходом по адресу:
        без неё чужая страница могла бы подсунуть администратору ссылку и
        пересадить его под другого человека.
        """
        self.ensure_one()
        user = self.env['res.users']._coop_login_as_target(self.user_ids[:1].id)
        stamp = int(time.time())
        token = hmac(self.env(su=True), LOGIN_AS_SCOPE, (self.env.uid, user.id, stamp))
        return {
            'type': 'ir.actions.act_url',
            'url': '/coop/login_as/%s?ts=%s&token=%s' % (user.id, stamp, token),
            'target': 'self',
        }


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _coop_login_as_target(self, user_id):
        """Кого можно: живого внутреннего пользователя, не администратора.

        Вход под другим администратором — это не «посмотреть глазами
        участника», а передача всевластия по кругу; его нет.
        """
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Входить под другими людьми может только администратор платформы '
                              'с включёнными полномочиями.'))
        user = self.sudo().browse(user_id).exists()
        if not user or not user.active or user.share:
            raise UserError(_('У этого человека нет учётной записи на площадке.'))
        if user == self.env.user:
            raise UserError(_('Это вы.'))
        if user.has_group('base.group_system'):
            raise UserError(_('Под другим администратором войти нельзя.'))
        return user

    @api.model
    def _coop_login_as_check(self, user_id, stamp, token):
        user = self._coop_login_as_target(user_id)
        expected = hmac(self.env(su=True), LOGIN_AS_SCOPE, (self.env.uid, user.id, int(stamp)))
        if not token or not consteq(expected, token) or time.time() - int(stamp) > LOGIN_AS_TTL:
            raise UserError(_('Ссылка входа устарела. Нажмите «Войти как» ещё раз.'))
        return user


class CoopShell(models.AbstractModel):
    _inherit = 'coop.shell'

    @api.model
    def boot(self):
        data = super().boot()
        impersonator = request and request.session.get('coop_impersonator_uid')
        if impersonator:
            data['login_as'] = {
                'name': self.env.user.name,
                'back': self.env['res.users'].sudo().browse(impersonator).name,
            }
        return data
