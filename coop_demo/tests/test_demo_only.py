# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.coop_projects.tests.common import CoopProjectCase

from ..data import load_biography, load_intangible_needs, load_project_needs


@tagged('post_install', '-at_install')
class TestDemoOnly(CoopProjectCase):

    def test_people_projects_untouched(self):
        """Загрузчики не дописывают проект, который завёл человек."""
        project = self.Project.with_user(self.initiator).create({
            'name': 'Проект человека', 'partner_id': self.initiator.partner_id.id,
            'required_total': 100000, 'fallback_plan': 'Первая очередь.',
        })
        project.sudo().state = 'gathering'
        created = project.create_date
        load_project_needs.load_project_needs(self.env)
        load_intangible_needs.load_intangible_needs(self.env)
        load_biography.age_listings(self.env)
        project.invalidate_recordset()
        self.assertFalse(project.sudo().need_ids)
        self.assertFalse(project.sudo().need_intangible_all_ids)
        self.assertEqual(project.create_date, created)
        self.assertEqual(project.required_total, 100000)
