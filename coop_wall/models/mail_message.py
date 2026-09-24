# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.mail.tools.discuss import Store

from .coop_wall_comment import WALL_MODELS


class MailMessage(models.Model):
    """Репост: запись со стены — у себя на странице.

    Владелец 24 сентября 2026 (решение 404): «сделать репост». Репост —
    новая запись на стене того, кто делится, с его словами (можно без
    них) и исходной записью карточкой внутри. Исходная запись — всегда
    первоисточник: репост репоста ссылается на исходник, а не на
    промежуточное звено, иначе карточки вкладывались бы друг в друга.
    """
    _inherit = 'mail.message'

    coop_repost_of_id = fields.Many2one(
        'mail.message', string='Репост записи', index=True,
        ondelete='set null')

    # ── В браузер ───────────────────────────────────────────────────

    def _to_store_defaults(self, target):
        return super()._to_store_defaults(target) + [
            Store.Attr('coop_repost', lambda m: m._coop_repost_data()),
            Store.Attr('coop_repost_count', lambda m: m._coop_repost_count()),
        ]

    def _coop_repost_data(self):
        """Карточка исходной записи — или False, если это не репост."""
        self.ensure_one()
        original = self.coop_repost_of_id
        if not original:
            return False
        # Исходник может быть закрыт от смотрящего (или удалён) — тогда
        # вместо карточки честное «недоступна».
        # Проверка — от имени смотрящего: данные для браузера движок часто
        # собирает в режиме суперпользователя, и там доступно всё.
        if not original.exists() or not original.sudo(False)._filtered_access('read'):
            return {'id': False}
        original = original.sudo()
        return {
            'id': original.id,
            'author_id': original.author_id.id,
            'author_name': original.author_id.name or '',
            'date': fields.Datetime.to_string(original.date),
            'body': str(original.body or ''),
            'attachment_count': len(original.attachment_ids),
            'page_model': original.model,
            'page_id': original.res_id,
        }

    def _coop_repost_count(self):
        self.ensure_one()
        if self.model not in WALL_MODELS or self.message_type != 'comment':
            return 0
        return self.sudo().search_count([('coop_repost_of_id', '=', self.id)])

    # ── Для браузера ─────────────────────────────────────────────────

    @api.model
    def coop_repost(self, post_id, comment=''):
        """Поделиться записью у себя на стене. Возвращает номер репоста."""
        original = self.browse(post_id).exists()
        if (not original or original.model not in WALL_MODELS
                or original.message_type != 'comment'):
            raise UserError(_("Запись не найдена."))
        original.check_access('read')
        original = original.coop_repost_of_id or original
        me = self.env.user.partner_id
        if self.sudo().search_count([
                ('coop_repost_of_id', '=', original.id),
                ('model', '=', 'res.partner'), ('res_id', '=', me.id)], limit=1):
            raise UserError(_("Эта запись уже есть на вашей странице."))
        comment = (comment or '').strip()[:4000]
        message = me.sudo().message_post(
            body=comment,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            author_id=me.id,
            coop_repost_of_id=original.id,
        )
        return message.id

