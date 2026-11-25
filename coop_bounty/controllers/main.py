# -*- coding: utf-8 -*-
"""Публичная страница задачи (№ 464, п. 1).

У каждой задачи — свой адрес, которым можно поделиться, как у Superteam
и Algora. Гость видит задачу целиком; «Взять задачу» ведёт на вход и
возвращает к форме заявки на этой же странице — раньше ссылка вела в
кабинет, и гость упирался во вход без пути обратно.
"""
from urllib.parse import quote

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from ..models.ir_http import coop_inside

# Черновики и отменённые наружу не показываем: первые ещё не задачи,
# вторые уже не задачи.
HIDDEN_STATES = ('draft', 'cancelled')


class CoopBountyWebsite(http.Controller):

    def _task(self, task_id):
        task = request.env['coop.bounty.task'].sudo().browse(task_id).exists()
        if not task or task.state in HIDDEN_STATES:
            raise request.not_found()
        return task

    @http.route('/help-project/task/<int:task_id>', type='http', auth='public',
                website=True, sitemap=False)
    def task_page(self, task_id, **kw):
        task = self._task(task_id)
        # Участнику — карточка задачи внутри платформы (№ 471); путь — через
        # карточку проекта, списка всех задач в меню нет (решение 691).
        inside = coop_inside(
            '/odoo/crowdsourcing/%s/coop.bounty.task/%s' % (task.project_id.id, task.id)
            if task.project_id else '/odoo/bounty/%s' % task.id)
        if inside:
            return inside
        user = request.env.user
        guest = user._is_public()
        mine = task.application_ids.filtered(
            lambda a: a.partner_id == user.partner_id) if not guest else task.application_ids.browse()
        return request.render('coop_bounty.coop_help_task_page', {
            'task': task,
            'guest': guest,
            'my_application': mine[:1],
            'is_author': not guest and task.payer_id in user.coop_publisher_partner_ids,
            'error': kw.get('error'),
            'applied': kw.get('applied'),
            'today': fields.Date.context_today(task),
        })

    @http.route('/help-project/task/<int:task_id>/apply', type='http', auth='user',
                website=True, methods=['GET', 'POST'], sitemap=False)
    def task_apply(self, task_id, **post):
        # GET — сюда возвращает вход: открываем форму заявки на странице.
        if request.httprequest.method == 'GET':
            return request.redirect('/help-project/task/%s#apply' % task_id)
        task = self._task(task_id)
        try:
            answers = []
            for question in task.question_ids:
                answers.append((0, 0, {'question_id': question.id,
                                       'answer': post.get('answer_%s' % question.id, '')}))
            method_id = int(post.get('method_id') or 0)
            if not method_id:
                raise UserError(_('Выберите способ оплаты.'))
            wizard = request.env['coop.bounty.apply'].create({
                'task_id': task.id,
                'method_id': method_id,
                'proposed_deadline': post.get('proposed_deadline') or False,
                'message': post.get('message') or False,
                'answer_line_ids': answers,
            })
            wizard.action_confirm()
        except (UserError, AccessError) as error:
            return request.redirect('/help-project/task/%s?error=%s#apply' % (
                task_id, quote(str(error.args[0]) if error.args else str(error))))
        return request.redirect('/help-project/task/%s?applied=1' % task_id)
