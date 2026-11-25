# -*- coding: utf-8 -*-
"""Отклик навыком на трудовую потребность и подбор (№ 474)."""
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .common import CoopProjectCase


@tagged('post_install', '-at_install')
class TestNeedSkill(CoopProjectCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        category = cls.env['coop.specialization.category'].create({'name': 'Сфера 474'})
        cls.spec = cls.env['coop.specialization'].create(
            {'name': 'Сварщик 474', 'category_id': category.id})
        cls.project = cls._make_project(state='gathering')
        cls.need = cls._make_need(cls.project, name='Сварить каркас', kind='labour')
        cls.need.need_specialization_id = cls.spec
        cls.worker = cls._make_person('Мастер Сварки')
        cls.offer = cls.env['coop.skill.offer'].create({
            'name': 'Сварка полуавтоматом', 'partner_id': cls.worker.partner_id.id,
            'coop_specialization_id': cls.spec.id, 'state': 'published',
            'currency_id': cls.project.currency_id.id,
            'rate': 6000, 'rate_kind': 'from', 'rate_period': 'day'})

    def _respond(self, qty=4):
        wizard = self.env['coop.project.contribute'].with_user(self.worker).create({
            'project_id': self.project.id, 'need_id': self.need.id, 'kind': 'labour',
            'name': 'Сварю', 'value': 1, 'labour_qty': qty,
            'skill_offer_id': self.offer.id})
        wizard.action_offer()
        return self.Contribution.search([('need_id', '=', self.need.id)])

    def test_match_and_invite(self):
        need = self.need.with_user(self.initiator)
        self.assertEqual(need.need_match_count, 1)
        self.assertEqual([o['id'] for o in need.need_matches_json['offers']], [self.offer.id])
        need.action_invite_offer(self.offer.id)
        need.action_invite_offer(self.offer.id)
        self.assertEqual(need.need_matches_json['offers'][0]['status'], 'invited')
        notes = self.env['coop.notification'].sudo().search(
            [('partner_id', '=', self.worker.partner_id.id), ('body', 'ilike', 'приглашают')])
        self.assertEqual(len(notes), 1)

    def test_stranger_does_not_match(self):
        need = self.need.with_user(self.worker)
        self.assertFalse(need.need_matches_json)
        with self.assertRaises(UserError):
            need.action_invite_offer(self.offer.id)

    def test_value_is_rate_by_quantity(self):
        offer = self._respond()
        self.assertEqual(offer.value, 24000)
        self.assertEqual((offer.labour_rate, offer.labour_period), (6000, 'day'))

    def test_window_counts_value(self):
        action = self.need.with_user(self.worker).action_join_need()
        form = Form(self.env['coop.project.contribute'].with_user(
            self.worker).with_context(**action['context']))
        form.skill_offer_id = self.offer
        form.labour_qty = 3
        self.assertEqual(form.value, 18000)

    def test_piece_rate_names_own_sum(self):
        self.offer.rate_kind = 'piece'
        self.assertEqual(self._respond().value, 1)

    def test_foreign_skill_refused(self):
        self.offer.partner_id = self._make_person('Чужой Мастер').partner_id
        with self.assertRaises(UserError):
            self._respond()

    def test_counter_rate(self):
        offer = self._respond()
        with self.assertRaises(UserError):
            offer.with_user(self.worker)._propose_rate(5000)
        offer.with_user(self.initiator)._propose_rate(5000)
        self.assertEqual(offer.value, 24000)
        with self.assertRaises(UserError):
            offer.with_user(self.initiator).action_counter_agree()
        offer.with_user(self.worker).action_counter_agree()
        self.assertEqual((offer.value, offer.labour_rate, offer.counter_rate, offer.state),
                         (20000, 5000, 0, 'offered'))
        offer.with_user(self.initiator).action_accept()
        self.assertEqual(self.need.price, 20000)

    def test_counter_refused_keeps_rate(self):
        offer = self._respond()
        offer.with_user(self.initiator)._propose_rate(5000)
        offer.with_user(self.worker).action_counter_refuse()
        self.assertEqual((offer.value, offer.counter_rate), (24000, 0))
