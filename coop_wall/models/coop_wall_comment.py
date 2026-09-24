# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

# Стены — те же, что в `coop_theme/static/src/js/wall.js` (`WALL_MODELS`).
WALL_MODELS = ('res.partner', 'coop.project', 'coop.community')


class CoopWallComment(models.Model):
    """Комментарий к записи на стене.

    Владелец 24 сентября 2026: «сделать комментарии к постам на стене»
    (решение 404).

    Почему своя модель, а не ответ сообщением движка. У ответа в движке
    есть «родитель» (`parent_id`), но у большинства моделей движок
    проставляет его сам — последней записью ленты (`_mail_flat_thread`).
    По нему не отличить комментарий от новой записи. И ответы лежали бы
    в той же ленте, что записи: ленту движок грузит страницами по
    тридцать, и страница из одних комментариев показывала бы стену
    пустой. Комментарий к записи — отдельная вещь, и хранится отдельно.

    Читают комментарии все, кто видит запись. Пишут и удаляют — только
    методами ниже: они проверяют доступ к самой записи, а не к таблице.
    """
    _name = 'coop.wall.comment'
    _description = 'Комментарий к записи на стене'
    _order = 'date asc, id asc'

    post_id = fields.Many2one(
        'mail.message', string='Запись', required=True, index=True,
        ondelete='cascade')
    author_id = fields.Many2one(
        'res.partner', string='Автор', required=True, index=True,
        default=lambda self: self.env.user.partner_id, ondelete='cascade')
    body = fields.Text(string='Текст', required=True)
    date = fields.Datetime(
        string='Когда', required=True, default=fields.Datetime.now)

    # ── Доступ ────────────────────────────────────────────────────────

    def _coop_check_post(self, post):
        """Запись существует, стоит на стене и видна текущему человеку."""
        post = post.exists()
        if not post or post.model not in WALL_MODELS or post.message_type != 'comment':
            raise UserError(_("Запись не найдена."))
        post.check_access('read')
        return post

    def _coop_can_delete(self):
        self.ensure_one()
        user = self.env.user
        return self.author_id == user.partner_id or user.has_group('base.group_system')

    def _coop_to_dict(self):
        return [{
            'id': c.id,
            'post_id': c.post_id.id,
            'author_id': c.author_id.id,
            'author_name': c.author_id.name,
            'body': c.body,
            'date': fields.Datetime.to_string(c.date),
            'can_delete': c._coop_can_delete(),
        } for c in self]

    # ── Для браузера ─────────────────────────────────────────────────

    @api.model
    def coop_for_posts(self, post_ids):
        """Комментарии к нескольким записям разом: {запись: [комментарии]}.

        Одним запросом на экран, а не по запросу на запись: на стене их
        тридцать за раз.
        """
        posts = self.env['mail.message'].browse(post_ids).exists()
        posts = posts.filtered(lambda m: m.model in WALL_MODELS)
        posts = posts._filtered_access('read')
        result = {post_id: [] for post_id in posts.ids}
        comments = self.sudo().search([('post_id', 'in', posts.ids)])
        for data in comments._coop_to_dict():
            result[data['post_id']].append(data)
        return result

    @api.model
    def coop_add(self, post_id, body):
        body = (body or '').strip()
        if not body:
            raise UserError(_("Пустой комментарий."))
        post = self._coop_check_post(self.env['mail.message'].browse(post_id))
        comment = self.sudo().create({
            'post_id': post.id,
            'author_id': self.env.user.partner_id.id,
            'body': body[:4000],
        })
        return comment._coop_to_dict()[0]

    @api.model
    def coop_remove(self, comment_id):
        comment = self.sudo().browse(comment_id).exists()
        if not comment:
            return True
        if not comment.with_env(self.env)._coop_can_delete():
            raise AccessError(_("Удалить комментарий может только автор."))
        comment.unlink()
        return True
