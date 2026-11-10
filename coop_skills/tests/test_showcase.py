# -*- coding: utf-8 -*-
from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSkillShowcase(TransactionCase):
    """Витрина навыка по дизайн-системе (`SkillPage`, задача 397)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls._user('Мастер Витрины')
        cls.stranger = cls._user('Гость Витрины')
        cls.offer = cls.env['coop.skill.offer'].create({
            'name': 'Кладка печей', 'partner_id': cls.owner.partner_id.id,
            'city': 'Омск', 'state': 'published'})

    @classmethod
    def _user(cls, name):
        return cls.env['res.users'].create({
            'name': name, 'login': name.replace(' ', '-').lower(),
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    def _arch(self):
        views = self.env['coop.skill.offer'].with_user(self.stranger).get_views(
            [(self.env.ref('coop_skills.view_coop_skill_form').id, 'form')])
        return etree.fromstring(views['views']['form']['arch'])

    def test_owner_card_fields_follow_partner(self):
        """Карточка человека — те же цифры, что у самого человека."""
        partner = self.owner.partner_id
        offer = self.offer.with_user(self.stranger)
        self.assertEqual(offer.partner_trust, partner.coop_trust)
        self.assertEqual(offer.partner_deals_done, partner.coop_deals_done)
        self.assertEqual(offer.partner_deals_reviewed, partner.coop_deals_reviewed)
        self.assertEqual(offer.partner_avatar, partner.avatar_128)

    def test_stranger_reads_showcase(self):
        """Смотрящий со стороны читает всё, что стоит на витрине."""
        arch = self._arch()
        names = {node.get('name') for node in arch.iter('field')}
        values = self.offer.with_user(self.stranger).read(sorted(names))
        self.assertEqual(values[0]['id'], self.offer.id)

    def test_layout(self):
        """Раскладка витрины: шапка, колонки, карточка человека."""
        arch = self._arch()
        self.assertIn('o_coop_show', arch.get('class', ''))
        for cls in ('coop-show_hero', 'coop-show_grid', 'coop-show_main',
                    'coop-show_aside', 'coop-owner', 'coop-price'):
            self.assertTrue(
                arch.xpath("//*[contains(concat(' ', @class, ' '), ' %s ')]" % cls),
                'нет блока %s' % cls)

    def test_conditions_stacked(self):
        """«Условия» — группами друг под другом: в две колонки метки
        второй группы наезжали на значения первой (владелец 10.11.2026)."""
        arch = self._arch()
        block = arch.xpath("//section[h2='Условия']")
        self.assertTrue(block, 'нет блока «Условия»')
        outer = block[0].xpath('./group')[0]
        self.assertEqual(outer.get('col'), '1')

    def test_experience_short(self):
        """Под подписью «Опыт» — без второго «Опыт»."""
        self.offer.experience_months = 38
        self.assertEqual(self.offer.experience_display, 'Опыт 3 года 2 месяца')
        self.assertEqual(self.offer.experience_short, '3 года 2 месяца')
        self.offer.experience_months = 0
        self.assertEqual(self.offer.experience_short, 'нет')

    def test_facts_like_sample(self):
        """Факты под описанием — как в образце: ставка, опыт,
        командировки, город."""
        arch = self._arch()
        labels = [dt.text for dt in arch.xpath("//dl[contains(@class, 'coop-show_facts')]/div/dt")]
        self.assertEqual(labels, ['Ставка', 'Опыт', 'Командировки', 'Город'])

    def test_single_message_button(self):
        """«Написать» — одна, в карточке человека, не дублем в шапке."""
        arch = self._arch()
        buttons = arch.xpath("//button[@name='action_message_owner']")
        self.assertEqual(len(buttons), 1)
        self.assertTrue(buttons[0].xpath("ancestor::*[contains(@class, 'coop-owner')]"))
