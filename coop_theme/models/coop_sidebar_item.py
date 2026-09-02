# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Разделы платформы в порядке макета. Это не «настройки по умолчанию,
# которые всё равно кто-нибудь поменяет»: порядок согласован с владельцем
# продукта, и до «Расширений» он одинаков у всех — по нему люди
# договариваются, где что лежит. Переставить пункты можно, выбросить —
# нет.
#
# Пустое действие значит, что раздел ещё не перенесён на движок. Пункт
# всё равно стоит в меню и ведёт на страницу, которая прямо об этом
# говорит: меню без него выглядело бы полным, и понять, чего не хватает,
# было бы неоткуда.
MAIN_ITEMS = [
    ('Моя страница', 'fa-user-circle-o', None),
    ('Сообщения', 'fa-comments-o', 'mail.action_discuss'),
    ('Люди', 'fa-users', 'coop_people.action_coop_people'),
    ('Навыки', 'fa-wrench', 'coop_skills.action_coop_skills'),
    ('Вакансии', 'fa-briefcase', 'coop_vacancies.action_coop_vacancies'),
    ('Ресурсы', 'fa-cube', 'coop_resources.action_coop_resources'),
    ('Проекты', 'fa-rocket', 'coop_projects.action_coop_projects'),
    ('Организации', 'fa-university', 'coop_orgs.action_coop_orgs'),
    ('Сообщества', 'fa-comments', None),
    ('Кошелёк', 'fa-credit-card', 'coop_wallet.action_coop_my_wallet'),
    ('Сделки', 'fa-handshake-o', 'coop_deals.action_coop_deals'),
]

# Расширения. В макете их полтора десятка — токеномика, цифровые активы,
# совместные закупки, склад, аукционы; здесь только перенесённое. Пункт,
# за которым стоит чужой модуль Odoo без нашего экрана, выдавал бы чужую
# страницу за перенесённую.
#
# Это подключённое по умолчанию, а не обязательное: расширения у каждого
# свои, и убрать их из своего меню участник вправе.
EXTENSION_ITEMS = [
    ('Каталог расширений', 'fa-th', 'coop_extensions.action_coop_extension_catalog'),
    ('Помощь проекту', 'fa-hand-peace-o', 'coop_bounty.action_coop_bounty_task'),
]

MAIN_BY_NAME = {name: xmlid for name, _icon, xmlid in MAIN_ITEMS}


class CoopSidebarItem(models.Model):
    """Пункт бокового меню — свой у каждого участника.

    Меню одно на платформу только до «Расширений»: эти разделы есть у
    всех и в одном порядке, иначе объяснить друг другу, где что искать,
    станет нельзя. Ниже — то, что участник подключил себе сам, и здесь
    два человека увидят разное.

    Порядок при этом свой у каждого: кто-то живёт в ресурсах, кто-то в
    сделках, и заставлять обоих искать глазами свой раздел незачем.
    """
    _name = 'coop.sidebar.item'
    _description = 'Пункт бокового меню'
    # По разделу — в обратном порядке: значения хранятся строками, и
    # «ext» стоит раньше «main» по алфавиту, а в меню расширения идут
    # последними.
    _order = 'section desc, sequence, id'

    user_id = fields.Many2one(
        'res.users', string='Участник', required=True, ondelete='cascade',
        index=True, default=lambda self: self.env.user)
    name = fields.Char('Название', required=True)
    icon = fields.Char('Значок', help='Класс значка Font Awesome, например fa-users.')
    action_id = fields.Many2one(
        'ir.actions.actions', string='Открывает', ondelete='cascade',
        help='Пусто — раздел из макета, который ещё не перенесён на движок; '
             'такой пункт ведёт на страницу с объяснением.')
    sequence = fields.Integer('Порядок', default=10)
    section = fields.Selection(
        [('main', 'Разделы'), ('ext', 'Расширения')],
        string='Часть меню', required=True, default='ext')
    is_required = fields.Boolean(
        'Обязательный', default=False,
        help='Разделы платформы есть у всех: их можно переставить, но не убрать.')

    _sql_constraints = [
        ('coop_sidebar_unique', 'unique(user_id, section, name)',
         'Такой пункт уже есть в меню.'),
    ]

    def unlink(self):
        required = self.filtered('is_required')
        if required:
            raise UserError(_(
                'Разделы платформы одинаковы у всех участников — по ним люди '
                'договариваются, где что лежит. Переставить их можно, убрать из '
                'меню нельзя: %s') % ', '.join(required.mapped('name')))
        return super().unlink()

    @api.model
    def _defaults_for_user(self, user):
        """Меню по умолчанию.

        Отсутствие действия для обязательного раздела не повод его
        пропустить: узел может стоять без части модулей, и тогда раздел
        показывается как ещё не перенесённый — это правда, а не ошибка.
        Расширение же без своего модуля просто не появляется.
        """
        values = []
        for index, (name, icon, xmlid) in enumerate(MAIN_ITEMS):
            action = self.env.ref(xmlid, raise_if_not_found=False) if xmlid else None
            values.append({
                'user_id': user.id,
                'name': name,
                'icon': icon,
                'action_id': action.id if action else False,
                'sequence': (index + 1) * 10,
                'section': 'main',
                'is_required': True,
            })
        for index, (name, icon, xmlid) in enumerate(EXTENSION_ITEMS):
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if not action:
                continue
            values.append({
                'user_id': user.id,
                'name': name,
                'icon': icon,
                'action_id': action.id,
                'sequence': (index + 1) * 10,
                'section': 'ext',
                'is_required': False,
            })
        return values

    @api.model
    def items_for_current_user(self):
        """Меню текущего участника; при первом обращении — по умолчанию.

        Под sudo: право на своё меню у участника есть, а на `ir.model.data`,
        откуда берутся действия, нет — и не должно быть.
        """
        user = self.env.user
        model = self.sudo()
        items = model.search([('user_id', '=', user.id)])
        if not items:
            items = model.create(model._defaults_for_user(user))
        else:
            items = model._sync_required(items, user)
        return [{
            'id': item.id,
            'label': item.name,
            'icon': item.icon or '',
            'actionId': item.action_id.id or False,
            'section': item.section,
        } for item in items]

    def _sync_required(self, items, user):
        """Дописать разделы, появившиеся после того, как меню уже создано.

        Иначе участник, зашедший до переноса раздела, не увидит его
        никогда: меню у него уже есть, а нового пункта в нём нет.
        """
        known = set(items.filtered(lambda i: i.section == 'main').mapped('name'))
        missing = [v for v in self._defaults_for_user(user)
                   if v['section'] == 'main' and v['name'] not in known]
        if missing:
            items |= self.create(missing)
        # Раздел мог быть перенесён после того, как меню уже собрано, —
        # или перенесён заново, на собственный экран вместо чужого. Второе
        # ровно так и вышло с проектами: пункт вёл в штатный модуль
        # управления проектами, а раздел платформы — это краудресурсинг, и
        # экран у него свой. Поэтому обязательные разделы не только
        # дописываются, но и переставляются на нынешнее действие.
        for item in items.filtered(lambda i: i.section == 'main'):
            xmlid = MAIN_BY_NAME.get(item.name)
            action = self.env.ref(xmlid, raise_if_not_found=False) if xmlid else None
            if action and item.action_id.id != action.id:
                item.action_id = action.id
        return items.sorted(lambda i: (0 if i.section == 'main' else 1, i.sequence, i.id))
