# -*- coding: utf-8 -*-
"""Куда человек попадает после входа.

Поле `action_id` объявлено на общей `ir.actions.actions`, а `env.ref`
отдаёт запись наследника — сравнивать надо номера, иначе проверка всегда
ложна при совпадающем действии.

Решение владельца от 14 сентября 2026: после ввода логина и пароля
человек попадает на свою страницу. Проверка нужна именно здесь: ошибка
в домашнем экране не даёт ни ошибки, ни пустого экрана — участник просто
видит не то и молча привыкает искать нужное руками.
"""
from odoo.tests import tagged

from .common import CoopCase


@tagged('post_install', '-at_install')
class TestHomeScreen(CoopCase):

    def test_domashniy_ekran_moya_stranitsa(self):
        home = self.env.ref('coop_profile.action_coop_my_page',
                            raise_if_not_found=False)
        if not home:
            self.skipTest('Модуль профиля не установлен')
        person = self._make_person('Вошедший Участник')
        self.assertEqual(person.action_id.id, home.id)

    def test_moya_stranitsa_otkryvaet_svoyu_kartochku(self):
        """Не список людей, а карточку того, кто вошёл."""
        home = self.env.ref('coop_profile.action_coop_my_page',
                            raise_if_not_found=False)
        if not home:
            self.skipTest('Модуль профиля не установлен')
        person = self._make_person('Открывший Свою Страницу')
        action = self.env['ir.actions.server'].browse(home.id).with_user(
            person).run()
        self.assertEqual(action.get('res_model'), 'res.partner')
        self.assertEqual(action.get('res_id'), person.partner_id.id)

    def test_yazyk_novoy_zapisi_russkiy(self):
        """Шаблона новой учётной записи в Odoo 19 нет — умолчание при
        создании. Без него участник заходит в английский интерфейс."""
        person = self._make_person('Русскоязычный Участник')
        self.assertEqual(person.lang, 'ru_RU')

    def test_svoy_vybor_ne_perebivaem(self):
        """Выбрал себе домашним что-то другое — оставляем как есть."""
        other = self.env.ref('coop_people.action_coop_people',
                             raise_if_not_found=False)
        if not other:
            self.skipTest('Каталог людей не установлен')
        person = self._make_person('Выбравший Своё')
        person.action_id = other.id
        self.env['coop.setup'].apply()
        person.invalidate_recordset()
        # Каталог людей был нашим прежним умолчанием, поэтому его как раз
        # переводим. Проверяем на действии, которого мы никогда не
        # ставили по умолчанию.
        person.action_id = self.env.ref('base.action_partner_form').id
        self.env['coop.setup'].apply()
        person.invalidate_recordset()
        self.assertEqual(person.action_id.id,
                         self.env.ref('base.action_partner_form').id)
