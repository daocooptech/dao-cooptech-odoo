# -*- coding: utf-8 -*-
"""Заготовка для тестов проектов.

Опирается на заготовку coop_base: участники, организации и ступени
доверия заводятся одинаково во всех разделах, и дублировать это в
каждом модуле значило бы получить три расходящихся способа завести
человека.
"""
from odoo.addons.coop_base.tests.common import CoopCase


class CoopProjectCase(CoopCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['coop.project']
        cls.Contribution = cls.env['coop.project.contribution']
        cls.Resource = cls.env['coop.resource']
        cls.initiator = cls._make_person('Инициатор Проектов')
        # Проект собирает чужие деньги и труд — без подтверждённой
        # личности сбор не открыть.
        cls._confirm(cls.initiator.partner_id, 'identity')

    @classmethod
    def _make_project(cls, name='Проект для проверки', required=100000,
                      partner=None, state=None):
        project = cls.Project.create({
            'name': name,
            'partner_id': (partner or cls.initiator.partner_id).id,
            'required_total': required,
        })
        if state:
            project.state = state
        return project

    @classmethod
    def _make_need(cls, project, name='Нужны доски', price=50000,
                   manager=None, kind='material'):
        return cls.Resource.create({
            'name': name,
            'listing_type': 'request',
            'resource_type': kind,
            'project_id': project.id,
            'owner_id': project.partner_id.id,
            'need_manager_id': manager.id if manager else False,
            'price': price,
            'state': 'published',
        })

    @classmethod
    def _make_offer(cls, project, who, need=None, value=50000,
                    name='Привезу своё'):
        return cls.Contribution.create({
            'project_id': project.id,
            'need_id': need.id if need else False,
            'partner_id': who.partner_id.id if who._name == 'res.users'
                          else who.id,
            'kind': 'material',
            'name': name,
            'value': value,
            'state': 'offered',
        })
