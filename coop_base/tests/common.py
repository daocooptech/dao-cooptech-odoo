# -*- coding: utf-8 -*-
"""Общая заготовка для тестов платформы.

Каждый тест заводит участников и организации сам, а не опирается на
наполнение: наполнение меняется при каждой правке загрузчиков, и тест,
который смотрит на «проект номер пять», ломается от постороннего
изменения и перестаёт значить что-либо.
"""
from odoo.tests.common import TransactionCase


class CoopCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env['res.partner']
        cls.Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.Membership = cls.env['coop.membership']
        cls.Verification = cls.env['coop.verification']

    @classmethod
    def _make_person(cls, name, login=None):
        """Участник с учётной записью.

        Без учётной записи половину проверок не сделать: полномочия и
        правила доступа спрашивают у пользователя, а не у партнёра.
        """
        user = cls.Users.create({
            'name': name,
            'login': login or ('%s@test.coop' % abs(hash(name))),
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        return user

    @classmethod
    def _make_org(cls, name):
        return cls.Partner.create({'name': name, 'is_company': True})

    @classmethod
    def _confirm(cls, partner, kind, method='inperson'):
        """Подтвердить участнику ступень.

        Ступень вычисляется из фактов проверки, выставить её напрямую
        нельзя — и не нужно: тест должен идти тем же путём, что и жизнь.
        """
        return cls.Verification.create({
            'partner_id': partner.id,
            'kind': kind,
            'method': method,
            'state': 'confirmed',
        })

    @classmethod
    def _join(cls, person, org, powers=(), role='member', state='active'):
        codes = [cls.env.ref('coop_base.power_%s' % code).id
                 for code in powers]
        values = {
            'partner_id': person.partner_id.id,
            'organization_id': org.id,
            'role': role,
            'state': state,
            'power_ids': [(6, 0, codes)],
        }
        if state == 'active':
            # Действующее членство без основания приёма модель не
            # пропускает — и правильно делает: состав кооператива
            # меняется решением, а не записью в базе.
            values.update(admission_basis='Протокол № 1 от 01.02.2026',
                          joined_on='2026-02-01')
        return cls.Membership.create(values)
