# -*- coding: utf-8 -*-
import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .coop_wall_comment import WALL_MODELS

# Сколько вариантов у опроса: меньше двух — не выбор, больше десяти —
# уже анкета.
MIN_OPTIONS = 2
MAX_OPTIONS = 10


def canonical(obj):
    """Каноническая запись тела события — та же, что в протоколе обмена
    (`federation/ref/canonical.py` дизайн-макета): UTF-8, ключи по кодовым
    точкам, без пробелов. Дробных чисел в теле нет — только строки и целые.
    """
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


class CoopWallPoll(models.Model):
    """Опрос — вид записи на стене.

    Владелец 24 сентября 2026 (решение 404): «голосование … в лентах».
    Ответы на вопросы того же вечера (решение 410):

    - кто за что голосовал — выбирает автор, по умолчанию анонимно;
    - выбор один, **голос отозвать нельзя**: «записываться будет всё в
      децентрализованную БД»;
    - срок по желанию, автор может закрыть опрос сам; итог виден
      проголосовавшему, автору и всем после окончания;
    - опрос можно отложить, как любую запись.

    Опрос держится за запись ленты (`message_id`). Отложенный опрос — за
    отложенное сообщение движка (`scheduled_message_id`), а к записи
    привязывается в момент её выхода (`mail.scheduled.message`,
    `_message_created_hook`).
    """
    _name = 'coop.wall.poll'
    _description = 'Опрос на стене'
    _order = 'id desc'

    message_id = fields.Many2one(
        'mail.message', string='Запись', index=True, ondelete='cascade')
    scheduled_message_id = fields.Many2one(
        'mail.scheduled.message', string='Отложенная запись', index=True,
        ondelete='cascade')
    author_id = fields.Many2one(
        'res.partner', string='Автор', required=True, index=True,
        default=lambda self: self.env.user.partner_id, ondelete='cascade')
    question = fields.Char(string='Вопрос', required=True)
    option_ids = fields.One2many(
        'coop.wall.poll.option', 'poll_id', string='Варианты')
    vote_ids = fields.One2many(
        'coop.wall.poll.vote', 'poll_id', string='Голоса')
    is_public = fields.Boolean(
        string='Открытое голосование',
        help='Видно, кто за какой вариант голосовал. Без отметки — только '
             'числа.')
    close_at = fields.Datetime(string='Окончание')
    closed_manually = fields.Boolean(string='Завершён автором')
    vote_count = fields.Integer(
        string='Голосов', compute='_compute_vote_count')

    def _compute_vote_count(self):
        counts = dict(self.env['coop.wall.poll.vote'].sudo()._read_group(
            [('poll_id', 'in', self.ids)], ['poll_id'], ['__count']))
        for poll in self:
            poll.vote_count = counts.get(poll, 0)

    def _coop_is_closed(self):
        self.ensure_one()
        return bool(self.closed_manually
                    or (self.close_at and self.close_at <= fields.Datetime.now()))

    # ── Для браузера ─────────────────────────────────────────────────

    def _coop_data(self):
        """Опрос глазами смотрящего: что показать и что можно сделать.

        Числа по вариантам отдаются только тому, кому итог уже можно
        видеть: проголосовавшему, автору и всем после окончания. Иначе
        браузер получил бы их, даже если бы не рисовал.
        """
        self.ensure_one()
        poll = self.sudo()
        me = self.env.user.partner_id
        mine = poll.vote_ids.filtered(lambda v: v.partner_id == me)[:1]
        closed = poll._coop_is_closed()
        is_author = poll.author_id == me
        see = bool(mine) or is_author or closed
        total = len(poll.vote_ids)
        options = []
        for option in poll.option_ids:
            votes = poll.vote_ids.filtered(lambda v: v.option_id == option)
            data = {'id': option.id, 'name': option.name}
            if see:
                data['count'] = len(votes)
                # Целые проценты: сумма может дать 99 или 101, и это
                # честнее дробей, которые подписи всё равно округлят.
                data['percent'] = round(100 * len(votes) / total) if total else 0
                if poll.is_public:
                    data['voters'] = [{'id': v.partner_id.id, 'name': v.partner_id.name}
                                      for v in votes[:12]]
            options.append(data)
        return {
            'id': poll.id,
            'question': poll.question,
            'is_public': poll.is_public,
            'close_at': fields.Datetime.to_string(poll.close_at) if poll.close_at else False,
            'closed': closed,
            'total': total,
            'see': see,
            'mine': mine.option_id.id or False,
            'is_author': is_author,
            'can_vote': not mine and not closed and bool(poll.message_id),
            'options': options,
        }

    @api.model
    def coop_create(self, model, res_id, question, options, is_public=False,
                    close_at=False, scheduled_at=False):
        """Опубликовать опрос на стене — сразу или к сроку.

        Публикация — от имени человека и с его правами: писать на чужой
        стене он может ровно там, где может писать запись.
        """
        if model not in WALL_MODELS:
            raise UserError(_("Опрос можно поставить только на стену."))
        question = (question or '').strip()[:300]
        options = [o.strip()[:200] for o in options or [] if o and o.strip()]
        if not question:
            raise UserError(_("Напишите вопрос."))
        if len(options) < MIN_OPTIONS:
            raise UserError(_("Нужно хотя бы два варианта ответа."))
        if len(options) > MAX_OPTIONS:
            raise UserError(_("Вариантов не больше десяти."))
        if len(set(o.lower() for o in options)) != len(options):
            raise UserError(_("Варианты повторяются."))
        now = fields.Datetime.now()
        close_at = fields.Datetime.to_datetime(close_at) if close_at else False
        scheduled_at = fields.Datetime.to_datetime(scheduled_at) if scheduled_at else False
        if close_at and close_at <= (scheduled_at or now):
            raise UserError(_("Опрос должен заканчиваться после публикации."))

        record = self.env[model].browse(res_id).exists()
        if not record:
            raise UserError(_("Страница не найдена."))
        vals = {
            'author_id': self.env.user.partner_id.id,
            'question': question,
            'is_public': bool(is_public),
            'close_at': close_at,
            'option_ids': [(0, 0, {'name': name, 'sequence': i})
                           for i, name in enumerate(options)],
        }
        if scheduled_at:
            # Тело отложенной записи — вопрос: в списке «Запланировано»
            # иначе стояла бы пустая строка. При выходе тело снимается, и
            # вопрос остаётся только в карточке опроса.
            scheduled = self.env['mail.scheduled.message'].create({
                'model': model,
                'res_id': record.id,
                'author_id': self.env.user.partner_id.id,
                'body': '📊 %s' % question,
                'scheduled_date': scheduled_at,
            })
            vals['scheduled_message_id'] = scheduled.id
            self.sudo().create(vals)
            return {'scheduled': scheduled.id}
        message = record.message_post(
            body='', message_type='comment', subtype_xmlid='mail.mt_comment')
        vals['message_id'] = message.id
        self.sudo().create(vals)
        return {'message': message.id}

    def _coop_check_visible(self):
        self.ensure_one()
        message = self.sudo().message_id
        if not message:
            raise UserError(_("Опрос ещё не опубликован."))
        message.sudo(False).check_access('read')

    @api.model
    def coop_vote(self, poll_id, option_id):
        """Голос. Один, без отзыва (решение 410)."""
        poll = self.browse(poll_id).exists()
        if not poll:
            raise UserError(_("Опрос не найден."))
        poll._coop_check_visible()
        # Два щелчка подряд или две вкладки: голоса одного человека по
        # одному опросу не должны обогнать друг друга. Строка опроса
        # запирается до конца сделки — заодно цепочка хэшей не ветвится.
        self.env.cr.execute(
            'SELECT id FROM coop_wall_poll WHERE id = %s FOR UPDATE', [poll.id])
        poll = poll.sudo()
        if poll._coop_is_closed():
            raise UserError(_("Опрос уже завершён."))
        option = poll.option_ids.filtered(lambda o: o.id == option_id)
        if not option:
            raise UserError(_("Такого варианта нет."))
        poll.vote_ids.sudo()._coop_cast(poll, option, self.env.user.partner_id)
        return poll.with_env(self.env)._coop_data()

    @api.model
    def coop_close(self, poll_id):
        poll = self.browse(poll_id).exists()
        if not poll:
            raise UserError(_("Опрос не найден."))
        if poll.sudo().author_id != self.env.user.partner_id \
                and not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Завершить опрос может только автор."))
        poll.sudo().closed_manually = True
        return poll._coop_data()


class CoopWallPollOption(models.Model):
    _name = 'coop.wall.poll.option'
    _description = 'Вариант ответа'
    _order = 'sequence, id'

    poll_id = fields.Many2one(
        'coop.wall.poll', string='Опрос', required=True, index=True,
        ondelete='cascade')
    name = fields.Char(string='Вариант', required=True)
    sequence = fields.Integer(default=0)


class CoopWallPollVote(models.Model):
    """Голос — запись журнала, а не строка таблицы.

    Отозвать или поменять голос нельзя (решение 410): «записываться будет
    всё в децентрализованную БД». Поэтому голос с первого дня устроен
    так, как устроено событие журнала узла (навык `federation-protocol`):
    номер в журнале опроса (`seq`), хэш предыдущего (`prev_hash`) и хэш
    канонического тела (`hash`). Дробных чисел в теле нет. Правка и
    удаление запрещены на уровне модели; уходит голос только вместе с
    опросом, когда автор удаляет запись.

    Голосующий в теле пока номером участника на этом узле — `did:key`
    человека появится вместе с обменом между узлами.
    """
    _name = 'coop.wall.poll.vote'
    _description = 'Голос в опросе'
    _order = 'poll_id, seq'

    poll_id = fields.Many2one(
        'coop.wall.poll', string='Опрос', required=True, index=True,
        ondelete='cascade')
    option_id = fields.Many2one(
        'coop.wall.poll.option', string='Вариант', required=True, index=True,
        ondelete='cascade')
    partner_id = fields.Many2one(
        'res.partner', string='Кто', required=True, index=True,
        ondelete='cascade')
    date = fields.Datetime(string='Когда', required=True, readonly=True)
    seq = fields.Integer(string='Номер в журнале', required=True, readonly=True)
    prev_hash = fields.Char(string='Хэш предыдущего', readonly=True)
    hash = fields.Char(string='Хэш', required=True, readonly=True, index=True)

    _one_vote = models.Constraint(
        'unique(poll_id, partner_id)',
        'В опросе голосуют один раз.')

    def _coop_cast(self, poll, option, partner, date=None):
        """Записать голос в конец журнала опроса."""
        if self.sudo().search_count([('poll_id', '=', poll.id),
                                     ('partner_id', '=', partner.id)], limit=1):
            raise UserError(_("Вы уже проголосовали в этом опросе."))
        last = self.sudo().search([('poll_id', '=', poll.id)],
                                  order='seq desc', limit=1)
        seq = (last.seq or 0) + 1
        prev = last.hash or ''
        date = date or fields.Datetime.now()
        body = {
            'type': 'poll.vote.cast',
            'poll': poll.id,
            'option': option.id,
            'voter': partner.id,
            'at': fields.Datetime.to_string(date),
            'seq': seq,
            'prev': prev,
        }
        return self.sudo().with_context(coop_vote_cast=True).create({
            'poll_id': poll.id,
            'option_id': option.id,
            'partner_id': partner.id,
            'date': date,
            'seq': seq,
            'prev_hash': prev,
            'hash': hashlib.sha256(canonical(body)).hexdigest(),
        })

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('coop_vote_cast'):
            raise UserError(_("Голос записывается только голосованием."))
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_("Голос не меняется: он записан в журнал опроса."))

    def unlink(self):
        raise UserError(_("Голос не отзывается: он записан в журнал опроса."))


class MailScheduledMessage(models.Model):
    """Отложенная публикация на стене — на движке отложенных сообщений.

    Владелец 24 сентября 2026: часы у «Опубликовать»; до выхода запись
    видит только автор — в списке «Запланировано» над лентой, с
    «Отправить сейчас», «Изменить» и «Отменить» (всё это движок рисует
    сам). Отложить можно и опрос.
    """
    _inherit = 'mail.scheduled.message'

    coop_poll_ids = fields.One2many(
        'coop.wall.poll', 'scheduled_message_id', string='Опрос')

    def _message_created_hook(self, message):
        super()._message_created_hook(message)
        polls = self.sudo().coop_poll_ids
        if polls:
            # Вопрос живёт в карточке опроса, второй раз в тексте записи
            # он не нужен.
            message.sudo().body = ''
            polls.write({'message_id': message.id, 'scheduled_message_id': False})

    @api.model
    def coop_schedule(self, model, res_id, body, attachment_ids, scheduled_at):
        """Отложить запись из поля стены.

        Вложения черновика уже лежат на странице (их грузит поле записи);
        до выхода они переезжают к отложенному сообщению — иначе висели бы
        в файлах страницы раньше самой записи.
        """
        if model not in WALL_MODELS:
            raise UserError(_("Отложить можно только запись на стене."))
        scheduled_at = fields.Datetime.to_datetime(scheduled_at)
        if not scheduled_at or scheduled_at <= fields.Datetime.now():
            raise UserError(_("Время публикации должно быть в будущем."))
        attachments = self.env['ir.attachment'].browse(attachment_ids or []).exists()
        attachments = attachments.filtered(lambda a: a.create_uid == self.env.user)
        scheduled = self.create({
            'model': model,
            'res_id': res_id,
            'author_id': self.env.user.partner_id.id,
            'body': body or '',
            'attachment_ids': [(6, 0, attachments.ids)],
            'scheduled_date': scheduled_at,
        })
        attachments.sudo().write({'res_model': self._name, 'res_id': scheduled.id})
        return scheduled.id
