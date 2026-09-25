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
    coop_poll_ids = fields.One2many(
        'coop.wall.poll', 'message_id', string='Опрос')

    # ── В браузер ───────────────────────────────────────────────────

    def _to_store_defaults(self, target):
        return super()._to_store_defaults(target) + [
            Store.Attr('coop_repost', lambda m: m._coop_repost_data()),
            Store.Attr('coop_repost_count', lambda m: m._coop_repost_count()),
            Store.Attr('coop_thanks_count', lambda m: m._coop_thanks_count()),
            Store.Attr('coop_star_count', lambda m: m._coop_star_count()),
            Store.Attr('coop_poll', lambda m: m._coop_poll_data()),
        ]

    def _coop_poll_data(self):
        """Опрос записи глазами смотрящего — или False (`coop_wall_poll.py`)."""
        self.ensure_one()
        poll = self.sudo().coop_poll_ids[:1]
        return poll.with_env(self.env)._coop_data() if poll else False

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

    def _coop_star_count(self):
        """Сколько человек сохранили запись в избранное (☆ движка).
        Владелец 24 сентября 2026: «в ленте цифру забыл к иконке
        избранного»."""
        self.ensure_one()
        if self.model not in WALL_MODELS or self.message_type != 'comment':
            return 0
        return len(self.sudo().starred_partner_ids)

    def _coop_thanks_count(self):
        """Сколько разных людей поблагодарили, и автор это подтвердил.
        Без сумм: суммы видит только автор (решение 406)."""
        self.ensure_one()
        if self.model not in WALL_MODELS or self.message_type != 'comment':
            return 0
        thanks = self.env['coop.wall.thanks'].sudo().search([
            ('post_id', '=', self.id), ('state', '=', 'confirmed')])
        return len(thanks.mapped('sender_id'))

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
        # Своё поле в публикацию не передать: движок принимает там только
        # известные ему параметры (`_raise_for_invalid_parameters`). Ссылка
        # на исходник ставится сразу после.
        message = me.sudo().message_post(
            body=comment,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            author_id=me.id,
        )
        message.sudo().coop_repost_of_id = original
        return message.id

    @api.model
    def coop_feed_store(self, message_ids):
        """Записи ленты подписок — в хранилище переписки браузера.

        Лента подписок — канбан по `mail.message`, а ряд под записью,
        карточка репоста, опрос и вложения — компоненты стены, которым
        нужна запись хранилища (реакции, звёздочка, вложения). Отдаём тем
        же путём, каким движок отдаёт сообщения ленты записи.
        """
        messages = self.browse(message_ids).exists()._filtered_access('read')
        messages = messages.filtered(lambda m: m.model in WALL_MODELS)
        return Store().add(messages).get_result()

