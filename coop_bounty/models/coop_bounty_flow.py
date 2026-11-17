# -*- coding: utf-8 -*-
"""Ход задачи после № 439: критерии, вопросы, сдачи, отзывы, подписка.

Восемь улучшений из разбора баунти-площадок (№ 464): условия задачи
списком, по которому принимают и разбирают спор; вопросы автора в
заявке; сдача — записью с версиями; отзывы, которые идут в уровень
доверия, как у сделок (решение 89); подписка на новые задачи.
"""
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

RATINGS = [
    ('5', 'Отлично'),
    ('4', 'Хорошо'),
    ('3', 'Нормально'),
    ('2', 'Так себе'),
    ('1', 'Плохо'),
]
# Как в сделках: «нормально» — не похвала.
POSITIVE = ('4', '5')


class CoopBountyCriterion(models.Model):
    """Пункт приёмки: что должно быть, чтобы результат приняли.

    Пишется до публикации (как у Gitcoin и в программах Immunefi), а при
    приёмке автор отмечает выполненные пункты. Спор администратор
    разбирает по тем же пунктам — не по впечатлению.
    """
    _name = 'coop.bounty.criterion'
    _description = 'Критерий приёмки'
    _order = 'sequence, id'

    task_id = fields.Many2one('coop.bounty.task', string='Задача', required=True,
                              ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Что должно быть', required=True)
    done = fields.Boolean(string='Выполнено')


class CoopBountyQuestion(models.Model):
    """Вопрос автора, на который отвечают в заявке (Superteam, Dework)."""
    _name = 'coop.bounty.question'
    _description = 'Вопрос к заявке'
    _order = 'sequence, id'

    task_id = fields.Many2one('coop.bounty.task', string='Задача', required=True,
                              ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Вопрос', required=True)
    required = fields.Boolean(string='Обязательный', default=True)


class CoopBountyAnswer(models.Model):
    _name = 'coop.bounty.answer'
    _description = 'Ответ в заявке'
    _order = 'id'

    application_id = fields.Many2one('coop.bounty.application', string='Заявка',
                                     required=True, ondelete='cascade', index=True)
    question_id = fields.Many2one('coop.bounty.question', string='Вопрос',
                                  ondelete='set null')
    question = fields.Char(string='Вопрос', required=True,
                           help='Текст вопроса на момент заявки: автор мог его поправить.')
    answer = fields.Text(string='Ответ')


class CoopBountySubmission(models.Model):
    """Сдача результата — запись, а не смена состояния.

    Ссылка, файлы и пара слов о сделанном; при возврате на доработку
    появляется новая версия, прежние остаются с замечаниями автора.
    """
    _name = 'coop.bounty.submission'
    _description = 'Сдача результата'
    _order = 'task_id, version desc'

    task_id = fields.Many2one('coop.bounty.task', string='Задача', required=True,
                              ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='Исполнитель', required=True, index=True)
    version = fields.Integer(string='Версия', required=True, default=1)
    link = fields.Char(string='Ссылка на результат')
    note = fields.Text(string='Что сделано')
    attachment_ids = fields.Many2many('ir.attachment', string='Файлы')
    state = fields.Selection([
        ('review', 'На проверке'),
        ('returned', 'Возвращено на доработку'),
        ('accepted', 'Принято'),
    ], string='Состояние', default='review', required=True)
    review_note = fields.Text(string='Замечания автора')
    reviewed_on = fields.Date(string='Проверено')


class CoopBountyReview(models.Model):
    """Отзыв после приёмки: автор об исполнителе и исполнитель об авторе.

    Идёт в уровень доверия так же, как отзыв по сделке (решение 89):
    доверие — доля положительных отзывов о человеке.
    """
    _name = 'coop.bounty.review'
    _description = 'Отзыв по задаче'
    _order = 'create_date desc, id desc'

    task_id = fields.Many2one('coop.bounty.task', string='Задача', required=True,
                              ondelete='cascade', index=True)
    author_id = fields.Many2one('res.partner', string='Кто оценивает', required=True)
    target_id = fields.Many2one('res.partner', string='Кого оценивают', required=True, index=True)
    side = fields.Selection([
        ('author', 'Автор задачи об исполнителе'),
        ('executor', 'Исполнитель об авторе'),
    ], string='Чей отзыв', required=True)
    rating = fields.Selection(RATINGS, string='Оценка', required=True, default='5')
    body = fields.Text(string='Отзыв')

    _one_per_side = models.Constraint(
        'unique(task_id, side)', 'Отзыв этой стороны по задаче уже есть.')

    @api.model_create_multi
    def create(self, vals_list):
        reviews = super().create(vals_list)
        reviews.mapped('target_id')._coop_recompute_deal_stats()
        return reviews


class CoopBountySubscription(models.Model):
    """Подписка человека на новые задачи по специализации и городу."""
    _name = 'coop.bounty.subscription'
    _description = 'Подписка на задачи'

    partner_id = fields.Many2one('res.partner', string='Кто подписан', required=True,
                                 index=True, ondelete='cascade',
                                 default=lambda self: self.env.user.partner_id)
    specialization_ids = fields.Many2many(
        'coop.specialization', string='Специализации',
        help='Пусто — все специализации.')
    city = fields.Char(string='Город',
                       help='Пусто — любой город. Задачи без города (удалённые) '
                            'приходят при любом городе.')
    by_email = fields.Boolean(string='Присылать письмом',
                              help='Кроме уведомления в колокольчике — письмо на почту.')
    active = fields.Boolean(default=True)

    _one_per_partner = models.Constraint(
        'unique(partner_id)', 'Подписка у человека одна — правится, а не заводится заново.')

    def _compute_display_name(self):
        for sub in self:
            sub.display_name = _('Подписка на задачи')

    def _coop_matches(self, task):
        self.ensure_one()
        if self.specialization_ids and task.coop_specialization_id not in self.specialization_ids:
            return False
        if self.city and task.city and self.city.strip().lower() != task.city.strip().lower():
            return False
        return True

    @api.model
    def _coop_notify_new_task(self, task):
        """Известить подписчиков о новой задаче — колокольчиком и, кто
        просил, письмом. Автору о своей задаче не пишем."""
        subs = self.sudo().search([('active', '=', True)])
        authors = task.manager_id.partner_id | task.payer_id
        matched = subs.filtered(lambda s: s.partner_id not in authors and s._coop_matches(task))
        if not matched:
            return 0
        body = Markup(_('Новая задача по вашей подписке: <b>%s</b>')) % task.name
        self.env['coop.notification'].sudo()._notify(
            matched.mapped('partner_id'), body, record=task, kind='other')
        link = '%s/help-project/task/%s' % (task.get_base_url(), task.id)
        Mail = self.env['mail.mail'].sudo()
        for sub in matched.filtered(lambda s: s.by_email and s.partner_id.email):
            Mail.create({
                'subject': _('Новая задача: %s') % task.name,
                'email_to': sub.partner_id.email,
                'body_html': Markup(
                    '<p>%s</p><p><a href="%s">%s</a></p><p style="color:#888">%s</p>') % (
                    task.name, link, _('Открыть задачу'),
                    _('Письмо по подписке на задачи. Изменить или отключить — '
                      '«Помощь проекту → Подписка на задачи».')),
                'auto_delete': True,
            })
        return len(matched)

    @api.model
    def action_open_my_subscription(self):
        partner = self.env.user.partner_id
        sub = self.with_context(active_test=False).search([('partner_id', '=', partner.id)], limit=1)
        if not sub:
            sub = self.create({'partner_id': partner.id, 'city': partner.city or False})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Подписка на задачи'),
            'res_model': self._name,
            'res_id': sub.id,
            'view_mode': 'form',
            'target': 'current',
        }


class ResPartnerBounty(models.Model):
    """Выполненные задачи в профиле и задачи в уровне доверия."""
    _inherit = 'res.partner'

    coop_bounty_done_count = fields.Integer(
        string='Выполнено задач', compute='_compute_coop_bounty_done')
    coop_bounty_done_html = fields.Html(
        string='Выполненные задачи', compute='_compute_coop_bounty_done', sanitize=False)

    def _compute_coop_bounty_done(self):
        Task = self.env['coop.bounty.task'].sudo()
        Review = self.env['coop.bounty.review'].sudo()
        for partner in self:
            if not partner.id:
                partner.coop_bounty_done_count = 0
                partner.coop_bounty_done_html = False
                continue
            domain = partner._coop_bounty_done_domain()
            partner.coop_bounty_done_count = Task.search_count(domain)
            rows = []
            for task in Task.search(domain, order='accepted_on desc, id desc', limit=5):
                review = Review.search([('task_id', '=', task.id), ('side', '=', 'author')], limit=1)
                mark = (' · %s' % dict(RATINGS)[review.rating].lower()) if review else ''
                author = _('Платформа') if task.payer_kind == 'platform' else (
                    task.project_id.name or task.payer_id.name)
                rows.append(Markup(
                    '<div class="o_coop_edu_row"><span class="o_coop_key">%s</span>'
                    '<span>%s — %s%s</span></div>') % (
                    task.accepted_on.strftime('%d.%m.%Y') if task.accepted_on else '',
                    task.name, author, mark))
            partner.coop_bounty_done_html = Markup('').join(rows) if rows else False

    def _coop_bounty_done_domain(self):
        """Выполненные задачи — принятые с ним исполнителем или с выплатой
        ему: участник команды и сдавший результат постоянной задачи (№ 465)."""
        self.ensure_one()
        return ['|', ('payout_ids.partner_id', '=', self.id),
                '&', ('assignee_id', '=', self.id), ('state', '=', 'accepted')]

    def action_coop_bounty_done(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Выполненные задачи — %s') % self.display_name,
            'res_model': 'coop.bounty.task',
            'view_mode': 'list,form',
            'domain': self._coop_bounty_done_domain(),
            'context': {'create': False},
        }

    def _coop_recompute_deal_stats(self):
        """Сделки и принятые задачи вместе (решение 89).

        Принятая задача — завершённое дело между автором и исполнителем,
        отзыв по ней — такой же отзыв о человеке. Считаем поверх сделок,
        тем же правилом: доверие — доля положительных отзывов от всех
        отзывов о человеке.
        """
        result = super()._coop_recompute_deal_stats()
        Task = self.env['coop.bounty.task'].sudo()
        Review = self.env['coop.bounty.review'].sudo()
        for partner in self:
            done = Task.search_count([
                '|', ('payout_ids.partner_id', '=', partner.id),
                '&', ('state', '=', 'accepted'),
                '|', ('assignee_id', '=', partner.id), ('payer_id', '=', partner.id)])
            reviewed = Review.search_count([('target_id', '=', partner.id)])
            good = Review.search_count([('target_id', '=', partner.id), ('rating', 'in', POSITIVE)])
            if not (done or reviewed):
                continue
            total_reviewed = partner.coop_deals_reviewed + reviewed
            total_good = partner.coop_deals_positive + good
            partner.coop_deals_done += done
            partner.coop_deals_reviewed = total_reviewed
            partner.coop_deals_positive = total_good
            partner.coop_trust = round(total_good * 100.0 / total_reviewed) if total_reviewed else 0
        return result


# ── Окна ─────────────────────────────────────────────────────────────────

class CoopBountySubmit(models.TransientModel):
    _name = 'coop.bounty.submit'
    _description = 'Сдать результат'

    task_id = fields.Many2one('coop.bounty.task', string='Задача', required=True)
    link = fields.Char(string='Ссылка на результат')
    note = fields.Text(string='Что сделано')
    attachment_ids = fields.Many2many('ir.attachment', string='Файлы')

    def action_confirm(self):
        self.ensure_one()
        if not (self.link or self.note or self.attachment_ids):
            raise UserError(_('Приложите результат: ссылку, файлы или описание того, что сделано.'))
        self.task_id._coop_do_submit(self.link, self.note, self.attachment_ids)
        return {'type': 'ir.actions.act_window_close'}


class CoopBountyReturn(models.TransientModel):
    _name = 'coop.bounty.return'
    _description = 'Вернуть на доработку'

    task_id = fields.Many2one('coop.bounty.task', string='Задача', required=True)
    criterion_ids = fields.One2many(related='task_id.criterion_ids', readonly=True)
    note = fields.Text(string='Что доработать', required=True)

    def action_confirm(self):
        self.ensure_one()
        self.task_id._coop_do_return(self.note)
        return {'type': 'ir.actions.act_window_close'}


class CoopBountyReviewWizard(models.TransientModel):
    """Окно отзыва: оценивает тот, кто нажал, оценивают вторую сторону."""
    _name = 'coop.bounty.review.wizard'
    _description = 'Отзыв по задаче'

    task_id = fields.Many2one('coop.bounty.task', string='Задача', required=True, readonly=True)
    target_id = fields.Many2one('res.partner', string='Кого оцениваете',
                                compute='_compute_target')
    rating = fields.Selection(RATINGS, string='Оценка', required=True, default='5')
    body = fields.Text(string='Пара слов')

    @api.depends('task_id')
    def _compute_target(self):
        for wizard in self:
            side = wizard.task_id._coop_my_review_side()
            wizard.target_id = (wizard.task_id.assignee_id if side == 'author'
                                else wizard.task_id.payer_id)

    def action_send(self):
        self.ensure_one()
        task = self.task_id
        side = task._coop_my_review_side()
        if not side:
            raise UserError(_('Оставить отзыв могут автор и исполнитель принятой задачи — по одному.'))
        me = self.env.user.partner_id
        self.env['coop.bounty.review'].sudo().create({
            'task_id': task.id,
            'author_id': (task.payer_id if side == 'author' else me).id,
            'target_id': (task.assignee_id if side == 'author' else task.payer_id).id,
            'side': side,
            'rating': self.rating,
            'body': self.body,
        })
        return {'type': 'ir.actions.act_window_close'}


class CoopBountyApplyAnswer(models.TransientModel):
    _name = 'coop.bounty.apply.answer'
    _description = 'Ответ в окне заявки'

    wizard_id = fields.Many2one('coop.bounty.apply', required=True, ondelete='cascade')
    question_id = fields.Many2one('coop.bounty.question', string='Вопрос', readonly=True)
    question = fields.Char(related='question_id.name', string='Вопрос')
    required = fields.Boolean(related='question_id.required')
    answer = fields.Text(string='Ответ')
