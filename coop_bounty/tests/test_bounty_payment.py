# -*- coding: utf-8 -*-
from ast import literal_eval
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase

CRITERIA = [(0, 0, {'name': 'Результат приложен к сдаче'}),
            (0, 0, {'name': 'Исходники переданы автору'})]


class BountyCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Task = cls.env['coop.bounty.task']
        cls.m = {m.code: m for m in cls.env['coop.bounty.method'].with_context(
            active_test=False).search([])}
        cls.fund = cls.env['coop.bounty.fund'].create({
            'name': 'Фонд для проверки', 'amount': 1000,
            'date_start': fields.Date.today() - timedelta(days=1),
            'date_end': fields.Date.today() + timedelta(days=90),
        })
        # Своему фонду — приоритет над фондом из данных модуля.
        cls.env['coop.bounty.fund'].search([('id', '!=', cls.fund.id)]).write(
            {'date_end': fields.Date.today() - timedelta(days=2)})
        cls.org = cls.env['res.partner'].create({
            'name': 'Пекарня проверочная', 'is_company': True,
            'coop_labor_share_cap': 10, 'city': 'Тула',
        })
        cls.project = cls.env['coop.project'].create({
            'name': 'Пекарня — проверка', 'partner_id': cls.org.id,
            'coop_token_name': 'Токен пекарни', 'coop_token_symbol': 'bread',
            'coop_bounty_token_limit': 50000})
        cls.person = cls.env['res.partner'].create({'name': 'Исполнитель проверочный'})
        cls.user = cls.env['res.users'].create({
            'name': 'Исполнитель проверочный', 'login': 'bounty_tester',
            'partner_id': cls.person.id,
            'group_ids': [(4, cls.env.ref('base.group_user').id)],
        })

    def _platform_task(self, reward=300, codes=('tokens',), **extra):
        values = {
            'name': 'Задача платформы', 'reward_tokens': reward,
            'allowed_method_ids': [(6, 0, [self.m[c].id for c in codes])],
            'criterion_ids': CRITERIA,
        }
        values.update(extra)
        return self.Task.create(values)

    def _apply_and_approve(self, task, code):
        wizard = self.env['coop.bounty.apply'].with_user(self.user).create({
            'task_id': task.id, 'method_id': self.m[code].id})
        wizard.action_confirm()
        task.application_ids.action_approve()

    def _submit(self, task, link='https://cloud.daocoop.tech/s/test'):
        self.env['coop.bounty.submit'].with_user(self.user).create({
            'task_id': task.id, 'link': link}).action_confirm()


@tagged('post_install', '-at_install')
class TestBountyPayment(BountyCase):
    """Способы оплаты, фонд, потолок доли и спор (решения 671–673, 194)."""

    def test_platform_publish_reserves_fund(self):
        task = self._platform_task(reward=300)
        self.assertEqual(task.payer_kind, 'platform')
        task.action_publish()
        self.assertEqual(task.fund_id, self.fund)
        self.assertEqual(self.fund.reserved, 300)
        self.assertEqual(self.fund.free, 700)
        with self.assertRaises(UserError):
            task.write({'reward_tokens': 400})
        task.action_cancel()
        self.assertEqual(self.fund.free, 1000, 'отмена возвращает резерв в фонд')

    def test_platform_publish_without_enough_fund(self):
        task = self._platform_task(reward=1500)
        with self.assertRaises(UserError):
            task.action_publish()
        self.assertEqual(task.state, 'draft')

    def test_platform_task_paid_in_platform_tokens(self):
        task = self._platform_task(codes=())
        task.action_publish()
        self.assertEqual(task.allowed_method_ids.mapped('code'), ['tokens'],
                         'задача нашего проекта — токенами услуг платформы')
        self.assertEqual(task.project_id, self.env.ref('coop_bounty.project_cooptech'))

    def test_project_task_needs_project_token(self):
        bare = self.env['coop.project'].create({'name': 'Без токена', 'partner_id': self.org.id})
        task = self.Task.create({
            'name': 'Логотип пекарни', 'payer_id': self.org.id, 'project_id': bare.id,
            'reward_tokens': 500, 'criterion_ids': CRITERIA,
        })
        self.assertEqual(task.payer_kind, 'project')
        self.assertEqual(task.city, 'Тула', 'город задачи проекта — город организации')
        with self.assertRaises(UserError):
            task.action_publish()
        task.project_id = self.project
        task.action_publish()
        self.assertEqual(task.allowed_method_ids.mapped('code'), ['project_tokens'],
                         'задачи проекта — только его токенами (решение 690)')
        self.assertFalse(task.fund_id, 'задача проекта фонд платформы не трогает')

    def test_project_tokens_credited_on_accept(self):
        task = self.Task.create({
            'name': 'Фото продукции', 'payer_id': self.org.id, 'project_id': self.project.id,
            'reward_tokens': 3000, 'criterion_ids': CRITERIA,
        })
        task.action_publish()
        with self.assertRaises(UserError):
            self.env['coop.bounty.apply'].with_user(self.user).create({
                'task_id': task.id, 'method_id': self.m['share'].id}).action_confirm()
        self._apply_and_approve(task, 'project_tokens')
        self.assertEqual(task.payment_mode, 'project_tokens')
        self._submit(task)
        task.criterion_ids.write({'done': True})
        task.action_accept()
        self.assertEqual(task.state, 'accepted')
        self.assertFalse(task.reward_transaction_id,
                         'токены платформы за задачу проекта не начисляются')
        move = self.env['coop.project.token.move'].search([('task_id', '=', task.id)])
        self.assertEqual(move.amount, 3000)
        self.assertEqual(move.partner_id, self.person)
        self.assertEqual(self.project.coop_token_issued, 3000)

    def test_silence_opens_dispute_and_admin_decides(self):
        task = self._platform_task(reward=200)
        task.action_publish()
        self._apply_and_approve(task, 'tokens')
        self._submit(task)
        task.submitted_on = fields.Date.today() - timedelta(days=8)
        self.Task._cron_open_disputes()
        self.assertEqual(task.state, 'dispute', 'молчание автора — спор, не приёмка')
        decide = self.env['coop.bounty.dispute'].with_user(self.user).create({
            'task_id': task.id, 'outcome': 'assignee', 'decision': 'Результат сдан полностью.'})
        with self.assertRaises(UserError):
            decide.action_confirm()
        admin = self.env.ref('base.user_admin')
        self.env['coop.bounty.dispute'].with_user(admin).create({
            'task_id': task.id, 'outcome': 'assignee',
            'decision': 'Результат сдан полностью, автор не ответил.'}).action_confirm()
        self.assertEqual(task.state, 'accepted', 'решение администратора — поверх неотмеченных пунктов')
        self.assertEqual(task.reward_transaction_id.amount, 200)
        self.assertEqual(self.fund.paid, 200)
        self.assertTrue(task.dispute_decision)


@tagged('post_install', '-at_install')
class TestBountyFlow(BountyCase):
    """Восемь улучшений П1 (№ 464)."""

    def test_criteria_required_and_accept_by_points(self):
        task = self._platform_task(criterion_ids=[])
        with self.assertRaises(UserError):
            task.action_publish()
        task.criterion_ids = CRITERIA
        task.action_publish()
        self._apply_and_approve(task, 'tokens')
        self._submit(task)
        with self.assertRaises(UserError):
            task.action_accept()
        task.criterion_ids[0].done = True
        with self.assertRaises(UserError):
            task.action_accept()
        task.criterion_ids.write({'done': True})
        task.action_accept()
        self.assertEqual(task.state, 'accepted')
        self.assertEqual(task.submission_ids.state, 'accepted')

    def test_submission_versions_and_return(self):
        task = self._platform_task()
        task.action_publish()
        self._apply_and_approve(task, 'tokens')
        with self.assertRaises(UserError):
            self.env['coop.bounty.submit'].with_user(self.user).create(
                {'task_id': task.id}).action_confirm()
        self._submit(task, 'https://cloud.daocoop.tech/s/v1')
        self.assertEqual(task.state, 'submitted')
        self.env['coop.bounty.return'].create({
            'task_id': task.id, 'note': 'Нет исходников'}).action_confirm()
        self.assertEqual(task.state, 'assigned')
        first = task.submission_ids.filtered(lambda s: s.version == 1)
        self.assertEqual(first.state, 'returned')
        self.assertEqual(first.review_note, 'Нет исходников')
        self._submit(task, 'https://cloud.daocoop.tech/s/v2')
        self.assertEqual(sorted(task.submission_ids.mapped('version')), [1, 2])

    def test_executor_silence_reminds_then_drops(self):
        task = self._platform_task(deadline=fields.Date.today() - timedelta(days=1))
        task.action_publish()
        self._apply_and_approve(task, 'tokens')
        self.Task._cron_executor_silence()
        self.assertEqual(task.state, 'assigned')
        self.assertTrue(task.reminded_on, 'на следующий день после срока — напоминание')
        task.deadline = fields.Date.today() - timedelta(days=8)
        self.Task._cron_executor_silence()
        self.assertEqual(task.state, 'published', 'через неделю — снова открыта')
        self.assertFalse(task.assignee_id)
        self.assertEqual(task.application_ids.state, 'dropped')
        self.assertEqual(task.fund_id, self.fund, 'резерв остаётся за задачей')

    def test_review_feeds_trust(self):
        task = self._platform_task()
        task.action_publish()
        self._apply_and_approve(task, 'tokens')
        self._submit(task)
        task.criterion_ids.write({'done': True})
        task.action_accept()
        self.assertEqual(task.with_user(self.user).can_review, True)
        self.env['coop.bounty.review.wizard'].with_user(self.user).create({
            'task_id': task.id, 'rating': '5'}).action_send()
        self.assertFalse(task.with_user(self.user).can_review, 'отзыв — один на сторону')
        self.env['coop.bounty.review'].create({
            'task_id': task.id, 'side': 'author', 'rating': '4',
            'author_id': task.payer_id.id, 'target_id': self.person.id})
        self.assertEqual(self.person.coop_trust, 100, 'положительный отзыв — в доверие')
        self.assertGreaterEqual(self.person.coop_deals_done, 1, 'принятая задача — завершённое дело')
        self.assertEqual(self.person.coop_bounty_done_count, 1)
        self.assertIn('Задача платформы', self.person.coop_bounty_done_html)

    def test_subscription_notifies_by_specialization(self):
        spec = self.env['coop.specialization'].search([], limit=2)
        if len(spec) < 2:
            self.skipTest('нет специализаций')
        self.env['coop.bounty.subscription'].create({
            'partner_id': self.person.id, 'specialization_ids': [(6, 0, spec[:1].ids)]})
        Notification = self.env['coop.notification'].sudo()
        before = Notification.search_count([('partner_id', '=', self.person.id)])
        self._platform_task(coop_specialization_id=spec[1].id).action_publish()
        self.assertEqual(Notification.search_count([('partner_id', '=', self.person.id)]), before)
        self._platform_task(coop_specialization_id=spec[0].id, reward=100).action_publish()
        self.assertEqual(Notification.search_count([('partner_id', '=', self.person.id)]), before + 1)

    def test_apply_requires_answers(self):
        task = self._platform_task(question_ids=[(0, 0, {'name': 'Ссылка на похожий результат',
                                                         'required': True})])
        task.action_publish()
        Wizard = self.env['coop.bounty.apply'].with_user(self.user).with_context(
            default_task_id=task.id)
        empty = Wizard.create({'method_id': self.m['tokens'].id})
        self.assertEqual(len(empty.answer_line_ids), 1, 'вопросы автора — в окне заявки')
        with self.assertRaises(UserError):
            empty.action_confirm()
        filled = Wizard.create({'method_id': self.m['tokens'].id,
                                'proposed_deadline': fields.Date.today() + timedelta(days=5)})
        filled.answer_line_ids.answer = 'https://cloud.daocoop.tech/s/portfolio'
        filled.action_confirm()
        application = task.application_ids
        self.assertEqual(application.answer_ids.answer, 'https://cloud.daocoop.tech/s/portfolio')
        self.assertEqual(application.proposed_deadline, fields.Date.today() + timedelta(days=5))


@tagged('post_install', '-at_install')
class TestBountyPublicPage(HttpCase):
    """Публичная страница задачи: открыта гостю, черновик скрыт."""

    def test_public_task_page(self):
        org = self.env['res.partner'].create({'name': 'Цех проверочный', 'is_company': True})
        project = self.env['coop.project'].create({
            'name': 'Цех — проверка', 'partner_id': org.id, 'coop_token_name': 'Токен цеха',
            'coop_bounty_token_limit': 20000})
        task = self.env['coop.bounty.task'].create({
            'name': 'Задача для страницы', 'payer_id': org.id, 'project_id': project.id,
            'reward_tokens': 1000, 'criterion_ids': CRITERIA,
        })
        draft = self.url_open('/help-project/task/%s' % task.id)
        self.assertEqual(draft.status_code, 404)
        task.action_publish()
        page = self.url_open('/help-project/task/%s' % task.id)
        self.assertEqual(page.status_code, 200)
        self.assertIn('Задача для страницы', page.text)
        self.assertIn('Критерии приёмки', page.text)
        self.assertIn('Токен цеха', page.text)
        self.assertIn('/help-project/task/%s/apply' % task.id, page.text)

    def test_help_page_shows_our_card(self):
        """Гость по «Помощь проекту» видит карточку нашего проекта: токен
        оплаты, счётчики задач и экономику токена (решение 691)."""
        ours = self.env.ref('coop_bounty.project_cooptech')
        page = self.url_open('/help-project')
        self.assertEqual(page.status_code, 200)
        self.assertIn(ours.name, page.text)
        self.assertIn(ours.coop_token_name, page.text)
        self.assertIn('Экономика токена', page.text)
        self.assertIn('coop-help-stats', page.text)

    def test_member_stays_inside(self):
        """Вошедший с публичных адресов попадает внутрь платформы (№ 471)."""
        task = self.env['coop.bounty.task'].search([('state', '=', 'published')], limit=1)
        self.authenticate('admin', 'admin')
        page = self.url_open('/help-project', allow_redirects=False)
        self.assertEqual(page.status_code, 303)
        self.assertTrue(page.headers['Location'].endswith('/odoo/help-project'))
        if task:
            page = self.url_open('/help-project/task/%s' % task.id, allow_redirects=False)
            self.assertEqual(page.status_code, 303)
            self.assertTrue(page.headers['Location'].endswith('/%s' % task.id))
            self.assertIn('/odoo/', page.headers['Location'])


@tagged('post_install', '-at_install')
class TestCrowdCard(BountyCase):
    """Краудсорсинг: каталог проектов, карточка, задачи из списка (№ 466)."""

    def test_project_counts_and_catalog(self):
        task = self.Task.create({
            'name': 'Вывеска пекарни', 'payer_id': self.org.id, 'project_id': self.project.id,
            'reward_tokens': 700, 'criterion_ids': CRITERIA,
        })
        action = self.env.ref('coop_bounty.action_coop_crowd_projects')
        Project = self.env['coop.project']
        self.assertNotIn(self.project, Project.search(literal_eval(action.domain)),
                         'черновик задачи проект в каталог краудсорсинга не приводит')
        task.action_publish()
        self.project.invalidate_recordset()
        self.assertEqual(self.project.coop_crowd_open_count, 1)
        self.assertEqual(self.project.coop_crowd_open_tokens, 700)
        self.assertIn(self.project, Project.search(literal_eval(action.domain)))
        self._apply_and_approve(task, 'project_tokens')
        self.project.invalidate_recordset()
        self.assertEqual((self.project.coop_crowd_open_count, self.project.coop_crowd_work_count),
                         (0, 1))
        card = self.project.action_coop_crowd_card()
        self.assertEqual(card['views'][0][0],
                         self.env.ref('coop_bounty.view_coop_project_crowd_form').id)
        self.assertEqual(task.action_coop_open_card()['res_id'], task.id)

    def test_help_project_is_our_card(self):
        action = self.env['coop.project']._coop_action_help_project()
        ours = self.env.ref('coop_bounty.project_cooptech')
        self.assertEqual(action['res_id'], ours.id)
        self.assertEqual(action['name'], 'Помощь проекту')
        self.assertTrue(ours.coop_is_cooptech)
        self.assertFalse(self.project.coop_is_cooptech)

    def test_no_own_menu_tab(self):
        """Своей вкладки у краудсорсинга нет (решение 691): подписка —
        кнопкой над каталогом, фонд — в карточке нашего проекта."""
        for xmlid in ('menu_coop_bounty_root', 'menu_coop_bounty_task',
                      'menu_coop_bounty_subscription', 'menu_coop_bounty_fund',
                      'menu_coop_bounty_application'):
            self.assertFalse(self.env.ref('coop_bounty.%s' % xmlid, raise_if_not_found=False), xmlid)
        self.assertTrue(self.env.ref('coop_bounty.menu_coop_crowd_projects'))
        # Разметка как записана: кнопка фонда — только менеджерам, и
        # собранный для текущего пользователя вид её бы не показал.
        subscription = self.env.ref('coop_bounty.action_coop_bounty_my_subscription')
        kanban = self.env.ref('coop_bounty.view_coop_project_crowd_kanban').arch_db
        self.assertIn('name="%s"' % subscription.id, kanban)
        fund = self.env.ref('coop_bounty.action_coop_bounty_fund')
        form = self.env.ref('coop_bounty.view_coop_project_crowd_form').arch_db
        self.assertIn('name="%s"' % fund.id, form)

    def test_sync_cooptech_tasks(self):
        self.fund.amount = 200000
        ours = self.env.ref('coop_bounty.project_cooptech')
        Task = self.Task.sudo()
        stale = Task.create({
            'name': 'Сделанная задача из списка', 'project_id': ours.id,
            'reward_tokens': 100, 'criterion_ids': CRITERIA,
            'allowed_method_ids': [(6, 0, self.m['tokens'].ids)],
            'coop_source_ref': 'vault:999999',
        })
        stale.action_publish()
        self.Task._coop_sync_cooptech_tasks()
        synced = Task.search([('coop_source_ref', '!=', False), ('project_id', '=', ours.id),
                              ('id', '!=', stale.id)])
        self.assertGreaterEqual(len(synced), 90, 'открытые задачи списка — в нашем проекте')
        self.assertEqual(stale.state, 'cancelled', 'ушедшая из списка открытая задача снята')
        published = synced.filtered(lambda t: t.state == 'published')
        self.assertTrue(published)
        for task in published[:10]:
            self.assertEqual(task.payer_kind, 'platform')
            self.assertEqual(task.allowed_method_ids.mapped('code'), ['tokens'])
            self.assertTrue(task.criterion_ids)
            self.assertTrue(task.fund_id)
            self.assertEqual(task.token_unit, 'COOP', 'сумма — число и тикер токена')
        self.assertEqual(ours.coop_token_unit, 'COOP')
        count = len(synced)
        self.Task._coop_sync_cooptech_tasks()
        self.assertEqual(Task.search_count([('coop_source_ref', '!=', False),
                                            ('project_id', '=', ours.id),
                                            ('id', '!=', stale.id)]), count,
                         'повторная сверка задач не плодит')

    def test_token_ticker_latin_unique(self):
        self.assertEqual(self.project.coop_token_symbol, 'BREAD', 'тикер — заглавными')
        self.assertEqual(self.env.ref('coop_bounty.project_cooptech').coop_token_symbol, 'COOP')
        other = self.env['coop.project'].create({'name': 'Другой', 'partner_id': self.org.id})
        for bad in ('ХЛБ', 'B', '1ABC', 'TOOLONGTICKER', 'BREAD'):
            with self.assertRaises(ValidationError, msg=bad):
                with self.env.cr.savepoint():
                    other.coop_token_symbol = bad
        self.assertEqual(self.env['coop.project']._coop_ticker_from('Пасека на паях — Тюмень'), 'PNPT')
        self.assertEqual(self.env['coop.project']._coop_ticker_from('Пекарня'), 'PEK')

    def test_token_by_choice(self):
        """Токен — по выбору: без него вкладки нет, с названием — есть."""
        self.assertTrue(self.project.coop_has_token)
        other = self.env['coop.project'].create({'name': 'Без токена', 'partner_id': self.org.id})
        self.assertFalse(other.coop_has_token)
        other.coop_has_token = True
        self.assertTrue(other.coop_has_token)
        other.coop_token_name = 'Токен другого'
        self.assertTrue(other.coop_has_token)
        self.env['coop.project.token.move'].create({
            'project_id': self.project.id, 'partner_id': self.person.id, 'amount': 10})
        with self.assertRaises(ValidationError):
            self.project.coop_has_token = False
