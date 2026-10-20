# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Значок пункта меню для модуля, у которого своего пункта в EXTENSION_ITEMS
# нет, — по разделу каталога, как на карточке (`coop_sign` в виде).
CATEGORY_ICONS = {
    'accounting': 'receipt', 'process': 'settings', 'sales': 'shopping-cart',
    'finance': 'credit-card', 'community': 'building-community',
    'integration': 'plug-connected', 'localization': 'world',
}


# «Строго организационное» (решение 481, «Учёт компании»): модули коробки,
# которые по цепочке зависимостей опираются на учёт компании, и сторонние
# из этих разделов магазина. Человеку в каталоге не показываются.
ORG_ONLY_ROOTS = {'account', 'stock', 'sale', 'purchase', 'mrp', 'hr', 'crm'}
ORG_ONLY_STORE_CATEGORIES = ('accounting', 'sales', 'localization')


def _module_of(xmlid):
    return xmlid.split('.', 1)[0] if xmlid else False


class CoopExtensionConnection(models.Model):
    """Лицо подключило себе расширение (решения 463, 468).

    Модуль ставится на платформу один раз — это делает рабочая группа. А
    в меню он встаёт у того лица, которое его подключило: у человека — в
    его личном меню, у организации — в общем меню всех её представителей.
    Так устроен и Битрикс24, только там у организации свой портал, а у нас
    платформа одна.

    Модуля на платформе ещё нет — подключение всё равно заводится: это
    заявка, и пункт сразу стоит в меню с пометкой «устанавливается».
    Поставили модуль — пункт открывается сам, без повторного нажатия.
    """
    _name = 'coop.extension.connection'
    _description = 'Подключённое расширение'
    _order = 'sequence, id'

    partner_id = fields.Many2one(
        'res.partner', string='Чьё меню', required=True, index=True,
        ondelete='cascade',
        help='Человек или организация. У организации меню общее для всех '
             'её представителей.')
    extension_id = fields.Many2one(
        'coop.extension', string='Расширение', required=True, index=True,
        ondelete='cascade')
    user_id = fields.Many2one(
        'res.users', string='Подключил', default=lambda self: self.env.user,
        ondelete='set null')
    sequence = fields.Integer('Порядок', default=10)
    access_user_ids = fields.Many2many(
        'res.users', 'coop_extension_connection_access_rel', 'connection_id', 'user_id',
        string='Доступ у',
        help='Кому из организации открыт модуль: руководитель отмечает людей '
             '(решение 476). Подключивший руководитель — по умолчанию.')
    coop_my_face = fields.Boolean(
        compute='_compute_coop_my_face', search='_search_coop_my_face',
        help='Меню того лица, от имени которого человек действует сейчас.')
    coop_member_user_ids = fields.Many2many(
        'res.users', compute='_compute_coop_member_user_ids',
        help='Из кого выбирать «Доступ у»: действующие члены организации.')
    coop_can_manage = fields.Boolean(
        compute='_compute_coop_can_manage',
        help='Отмечать «Доступ у» вправе руководитель организации.')
    name = fields.Char(related='extension_id.name', string='Название')
    state = fields.Selection(
        [('on', 'Работает'), ('installing', 'Устанавливается')],
        string='Состояние', compute='_compute_state')

    _coop_connection_unique = models.Constraint(
        'unique(partner_id, extension_id)',
        'Это расширение уже подключено.',
    )

    @api.depends('extension_id.is_installed')
    def _compute_state(self):
        for record in self:
            record.state = 'on' if record.extension_id.is_installed else 'installing'

    def _coop_current_face(self):
        user = self.env.user
        return user.coop_acting_as_id or user.partner_id

    @api.depends_context('uid')
    def _compute_coop_my_face(self):
        face = self._coop_current_face()
        for record in self:
            record.coop_my_face = record.partner_id == face

    def _search_coop_my_face(self, operator, value):
        # Отбор на сервере: в домене действия `user.coop_acting_as_id`
        # клиент Odoo 20 не вычисляет («Name 'user' is not defined»), и
        # «Меню организации» не открывалось вовсе.
        if operator not in ('=', '!=') or not isinstance(value, bool):
            return NotImplemented
        positive = (operator == '=') == value
        return [('partner_id', '=' if positive else '!=', self._coop_current_face().id)]

    @api.depends('partner_id')
    def _compute_coop_member_user_ids(self):
        Membership = self.env['coop.membership'].sudo()
        for record in self:
            record.coop_member_user_ids = Membership.search([
                ('organization_id', '=', record.partner_id.id), ('state', '=', 'active'),
            ]).partner_id.user_ids.filtered(lambda u: not u.share)

    @api.depends_context('uid')
    def _compute_coop_can_manage(self):
        user = self.env.user
        admin = user.has_group('base.group_system')
        for record in self:
            record.coop_can_manage = admin or record.partner_id == user.partner_id \
                or user.coop_has_power('sign', record.partner_id)

    @api.model
    def action_coop_open_access(self):
        """Вкладка «Права доступа» в «Настройках» (решение 481 п. 5).

        От имени организации — её модули коробки и кому они открыты (у
        своих расширений платформы групп нет, отмечать некого). От себя —
        модули организаций, открытые этому человеку: вкладки «Настроек» у
        обоих лиц одни и те же.
        """
        user = self.env.user
        face = self._coop_current_face()
        person = face == user.partner_id
        if person:
            domain = [('access_user_ids', 'in', user.id),
                      ('partner_id', '!=', user.partner_id.id)]
            empty = _('Вам пока не открыт ни один модуль организаций')
            hint = _('Доступ к модулю организации даёт её руководитель — во '
                     'вкладке «Права доступа», действуя от имени организации.')
        else:
            domain = [('partner_id', '=', face.id),
                      ('extension_id.source', '!=', 'cooptech')]
            empty = _('Организация пока не подключала модулей')
            hint = _('Подключите модуль в каталоге расширений — здесь появится, '
                     'кому из организации он открыт.')
        view = self.env.ref('coop_extensions.view_coop_extension_access_list')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Права доступа'),
            'res_model': 'coop.extension.connection',
            'view_mode': 'list',
            'views': [(view.id, 'list')],
            'domain': domain,
            'target': 'current',
            'context': {'coop_settings': True, 'coop_access_person': person},
            'help': '<p class="o_view_nocontent_smiling_face">%s</p><p>%s</p>' % (empty, hint),
        }

    def _coop_check_manage(self):
        """Менять меню организации вправе только её руководитель.

        Руководитель — держатель «Права подписи без доверенности»; он же
        включает приложения организации (решение 450). Своё меню человек
        ведёт сам.
        """
        user = self.env.user
        if self.env.su or user.has_group('base.group_system'):
            return
        for partner in self.mapped('partner_id'):
            if partner == user.partner_id:
                continue
            if not user.coop_has_power('sign', partner):
                raise UserError(_(
                    'Меню организации «%s» общее для всех её представителей, '
                    'и ведёт его руководитель — держатель права подписи.'
                ) % partner.display_name)

    def write(self, vals):
        self._coop_check_manage()
        return super(CoopExtensionConnection, self.sudo()).write(vals)

    def unlink(self):
        self._coop_check_manage()
        return super(CoopExtensionConnection, self.sudo()).unlink()


class CoopExtension(models.Model):
    _inherit = 'coop.extension'

    coop_connect_state = fields.Selection(
        [('base', 'Раздел платформы'), ('on', 'Подключено'),
         ('installing', 'Устанавливается'), ('off', 'Не подключено')],
        string='В моём меню', compute='_compute_coop_connect_state',
        search='_search_coop_connect_state',
        help='У того лица, от имени которого вы сейчас действуете.')
    coop_for_face = fields.Boolean(
        compute='_compute_coop_for_face', search='_search_coop_for_face',
        help='Показывать лицу, от имени которого человек действует: учёт '
             'компании — только организации (решение 481).')
    coop_connected = fields.Boolean(
        string='Подключено мне', compute='_compute_coop_connect_state',
        search='_search_coop_connected')

    # ── Чьё меню ────────────────────────────────────────────────────────

    @api.model
    def _coop_face(self):
        """Лицо, от имени которого человек действует: он сам или организация."""
        user = self.env.user
        return user.coop_acting_as_id or user.partner_id

    @api.model
    def _coop_org_only_modules(self):
        """Имена модулей, которые зависят от учёта компании (замыкание)."""
        self.env.cr.execute("""
            SELECT m.name, d.name FROM ir_module_module_dependency d
            JOIN ir_module_module m ON m.id = d.module_id""")
        deps = {}
        for module, dep in self.env.cr.fetchall():
            deps.setdefault(module, set()).add(dep)
        org = set(ORG_ONLY_ROOTS)
        grown = True
        while grown:
            grown = False
            for module, needs in deps.items():
                if module not in org and needs & org:
                    org.add(module)
                    grown = True
        return org

    def _coop_is_org_only(self):
        self.ensure_one()
        if self.source == 'third':
            return self.category in ORG_ONLY_STORE_CATEGORIES
        # Свои расширения платформы не отсеиваются: они тянут учёт через
        # общие модули, но сделаны для всех (бартер, биржа, сделки).
        return self.source == 'odoo' and bool(self.module_name)             and self.module_name in self._coop_org_only_modules()

    @api.depends_context('uid')
    def _compute_coop_for_face(self):
        person = not self._coop_face_is_org()
        org_only = self._coop_org_only_modules() if person else set()
        for record in self:
            record.coop_for_face = not person or not (
                record.category in ORG_ONLY_STORE_CATEGORIES
                if record.source == 'third'
                else record.source == 'odoo' and record.module_name in org_only)

    def _search_coop_for_face(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            return NotImplemented
        positive = (operator == '=') == value
        if self._coop_face_is_org():
            return [] if positive else [('id', '=', False)]
        org_only = ['|', '&', ('source', '=', 'odoo'),
                    ('module_name', 'in', list(self._coop_org_only_modules())),
                    '&', ('source', '=', 'third'),
                    ('category', 'in', list(ORG_ONLY_STORE_CATEGORIES))]
        return ['!'] + org_only if positive else org_only

    @api.model
    def _coop_face_is_org(self):
        user = self.env.user
        return self._coop_face() != user.partner_id

    @api.model
    def _coop_base_modules(self):
        """Модули разделов платформы: они в меню у всех и всегда."""
        from odoo.addons.coop_theme.models.coop_sidebar_item import MAIN_ITEMS
        return {_module_of(xmlid) for _name, _icon, xmlid in MAIN_ITEMS if xmlid}

    @api.model
    def _coop_action_modules(self, action_ids):
        """Модуль, которому принадлежит каждое действие: {номер: модуль}."""
        if not action_ids:
            return {}
        rows = self.env['ir.model.data'].sudo().search_read(
            [('model', '=like', 'ir.actions.%'), ('res_id', 'in', list(action_ids))],
            ['res_id', 'module'])
        return {row['res_id']: row['module'] for row in rows}

    @api.model
    def _coop_connected_ids(self):
        """Расширения в меню текущего лица: {номер расширения: состояние}."""
        face = self._coop_face()
        Connection = self.env['coop.extension.connection'].sudo()
        result = {}
        for conn in Connection.search([('partner_id', '=', face.id)]):
            result[conn.extension_id.id] = conn.state
        # Разделы платформы — отдельным состоянием: они в меню у всех, и
        # кнопки «Убрать» на их карточке быть не должно.
        base = self._coop_base_modules()
        for ext in self.sudo().search([('module_name', 'in', list(base)),
                                       ('is_installed', '=', True)]):
            result[ext.id] = 'base'
        modules = set()
        if not self._coop_face_is_org():
            # У человека в меню стоят ещё и выданные платформой пункты —
            # «Документы», «Аукционы»… — без записи о подключении. Их модули
            # узнаются по действию пункта.
            items = self.env['coop.sidebar.item'].sudo().search([
                ('user_id', '=', self.env.user.id), ('section', '=', 'ext'),
                ('action_id', '!=', False)])
            modules |= set(self._coop_action_modules(items.mapped('action_id').ids).values())
        if modules:
            # Только расширения: действие пункта «Склад» лежит в плагине
            # «Продажи и склад», и плагин без этого отбора выглядел
            # подключённым, а «Убрать» на нём сносило чужой пункт.
            for ext in self.sudo().search([('module_name', 'in', list(modules)),
                                           ('is_installed', '=', True),
                                           ('kind', '=', 'app')]):
                result.setdefault(ext.id, 'on')
        return result

    @api.depends_context('uid')
    def _compute_coop_connect_state(self):
        connected = self._coop_connected_ids()
        for record in self:
            state = connected.get(record.id, 'off')
            record.coop_connect_state = state
            record.coop_connected = state != 'off'

    def _search_coop_connected(self, operator, value):
        if operator not in ('=', '!='):
            raise UserError(_('Отбор по «Подключено мне» — только да или нет.'))
        ids = list(self._coop_connected_ids())
        positive = (operator == '=') == bool(value)
        return [('id', 'in' if positive else 'not in', ids)]

    def _search_coop_connect_state(self, operator, value):
        connected = self._coop_connected_ids()
        values = value if isinstance(value, (list, tuple)) else [value]
        if operator not in ('=', 'in', '!=', 'not in'):
            raise UserError(_('Отбор по состоянию в меню — только по значению.'))
        if 'off' in values:
            ids = [i for i, s in connected.items() if s not in values]
            positive = operator in ('!=', 'not in')
        else:
            ids = [i for i, s in connected.items() if s in values]
            positive = operator in ('=', 'in')
        return [('id', 'in' if positive else 'not in', ids)]

    # ── Пункт меню расширения ───────────────────────────────────────────

    def _coop_menu_entry(self):
        """Чем расширение стоит в меню: (название, значок, номер действия).

        Свои расширения платформы — как в EXTENSION_ITEMS: то же название и
        действие, что у выданного пункта. Модуль коробки — главный пункт его
        собственного меню. Модуля на платформе нет — действия нет, пункт
        «устанавливается». Стоит, но своего раздела у модуля нет (он
        работает внутри других) — None: в меню ставить нечего.
        """
        self.ensure_one()
        from odoo.addons.coop_theme.models.coop_sidebar_item import EXTENSION_ITEMS
        icon = CATEGORY_ICONS.get(self.category, 'puzzle')
        for name, item_icon, xmlid in EXTENSION_ITEMS:
            if xmlid and _module_of(xmlid) == self.module_name:
                action = self.env.ref(xmlid, raise_if_not_found=False)
                if not self.is_installed:
                    return name, item_icon, False
                return (name, item_icon, action.id) if action else None
        if not self.is_installed:
            return self.name, icon, False
        menus = self.env['ir.model.data'].sudo().search(
            [('module', '=', self.module_name), ('model', '=', 'ir.ui.menu')])
        Menu = self.env['ir.ui.menu'].sudo()
        roots = Menu.browse(menus.mapped('res_id')).exists().filtered(
            lambda m: not m.parent_id).sorted('sequence')
        for root in roots:
            menu = root if root.action else Menu.search(
                [('id', 'child_of', root.id), ('action', '!=', False)],
                order='parent_path, sequence', limit=1)
            if menu and menu.action and menu.action._name.startswith('ir.actions.'):
                return self.name, icon, menu.action.id
        return None

    def _coop_module_groups(self):
        """Группы, которые открывают раздел модуля коробки (решение 476).

        Берутся с корневого пункта меню модуля (нет там — с пункта его
        действия), и только роли модуля — группы с областью (`privilege_id`),
        не из `base`: служебные («этапы», «повторяющиеся задачи») и общие
        роли движка выдавать нельзя. Из ролей — младшая: группа, которая
        подразумевает другую из набора, — уровень руководителя модуля.
        """
        self.ensure_one()
        Groups = self.env['res.groups']
        if self.source == 'cooptech' or not self.is_installed:
            return Groups
        menus = self.env['ir.model.data'].sudo().search(
            [('module', '=', self.module_name), ('model', '=', 'ir.ui.menu')])
        Menu = self.env['ir.ui.menu'].sudo()
        roots = Menu.browse(menus.mapped('res_id')).exists().filtered(lambda m: not m.parent_id)
        groups = roots.group_ids
        entry = self._coop_menu_entry()
        if not groups and entry and entry[2]:
            groups = Menu.search([('id', 'child_of', roots.ids),
                                  ('action', '!=', False)]).filtered(
                lambda m: m.action.id == entry[2]).group_ids
        xmlids = groups.sudo().get_external_id()
        groups = groups.sudo().filtered(
            lambda g: g.privilege_id and not (xmlids.get(g.id) or '').startswith('base.'))
        return groups.filtered(
            lambda g: not ((g.all_implied_ids - g) & groups))

    # ── Подключить и убрать ─────────────────────────────────────────────

    def _coop_check_connectable(self):
        self.ensure_one()
        if self.source == 'third':
            raise UserError(_(
                'Стороннего приложения на платформе нет — это витрина магазина '
                'Odoo. Откройте его страницу в магазине.'))
        if not self.module_id:
            raise UserError(_(
                'Это расширение пока заявлено, но не готово к установке: '
                'технический модуль для него не указан.'))
        if self.module_name in self._coop_base_modules():
            raise UserError(_('Этот раздел есть в меню у всех участников платформы.'))
        if not self._coop_face_is_org() and self._coop_is_org_only():
            raise UserError(_(
                '«%s» работает в учёте организации. Подключите его, действуя '
                'от имени организации.') % self.name)
        if self.kind == 'plugin':
            raise UserError(_(
                '«%s» — плагин: своего раздела у него нет, он работает внутри '
                'других разделов. В меню его ставить не нужно.') % self.name)

    def action_coop_connect(self):
        """Подключить расширение лицу, от имени которого человек действует.

        Модуль стоит — пункт встаёт в меню сразу. Не стоит — пункт встаёт
        с пометкой «устанавливается», а подключение становится заявкой
        рабочей группе (решение 463): она проверяет код и ставит модуль.
        """
        self.ensure_one()
        self._coop_check_connectable()
        entry = self._coop_menu_entry()
        if entry is None:
            raise UserError(_(
                'У модуля «%s» нет своего раздела: он работает внутри других '
                'разделов и уже включён на платформе.') % self.name)
        user = self.env.user
        face = self._coop_face()
        # Пункт, по которому внутри «нет доступа», в меню не ставится
        # (владелец 19.10.2026). Человеку так не подключить учёт
        # организации — склад, закупки, бухгалтерию.
        # Модуль коробки организации открывается тем, кому руководитель дал
        # доступ (решение 476) — группы выдаются при подключении, поэтому
        # «сейчас нет доступа» у организации не помеха.
        org_box = face != user.partner_id and self.source != 'cooptech'
        if entry[2] and not org_box                 and not self.env['coop.sidebar.item']._coop_can_open(user, entry[2]):
            if face == user.partner_id:
                raise UserError(_(
                    '«%s» работает в учёте организации. Подключите его, '
                    'действуя от имени организации.') % entry[0])
            raise UserError(_(
                'У вас нет доступа к разделу «%s» в этой организации, и пункт '
                'в меню не открылся бы.') % entry[0])
        if face != user.partner_id and not (
                user.has_group('base.group_system') or user.coop_has_power('sign', face)):
            raise UserError(_(
                'Меню организации «%s» общее для всех её представителей, и '
                'ведёт его руководитель — держатель права подписи.'
            ) % face.display_name)
        Connection = self.env['coop.extension.connection'].sudo()
        if not Connection.search_count([('partner_id', '=', face.id),
                                        ('extension_id', '=', self.id)]):
            last = Connection.search([('partner_id', '=', face.id)],
                                     order='sequence desc', limit=1)
            Connection.create({
                'partner_id': face.id,
                'extension_id': self.id,
                'user_id': user.id,
                'sequence': (last.sequence if last else 1000) + 10,
                'access_user_ids': [(6, 0, user.ids)] if org_box else [],
            })
        if face == user.partner_id:
            self.env['coop.sidebar.item']._coop_place_extension(user, self, entry)
        # Без действия: каталог сам перечитает карточку и сохранит отбор, а
        # боковое меню обновит вид каталога (`extension_kanban.js`). Раньше
        # здесь была перезагрузка страницы, и фильтры сбрасывались.
        return False

    def action_coop_disconnect(self):
        """Убрать расширение из меню текущего лица. Модуль остаётся на платформе."""
        self.ensure_one()
        user = self.env.user
        face = self._coop_face()
        conns = self.env['coop.extension.connection'].search([
            ('partner_id', '=', face.id), ('extension_id', '=', self.id)])
        conns.unlink()
        if face == user.partner_id:
            self.env['coop.sidebar.item']._coop_remove_extension(user, self)
        # Без действия: каталог сам перечитает карточку и сохранит отбор, а
        # боковое меню обновит вид каталога (`extension_kanban.js`). Раньше
        # здесь была перезагрузка страницы, и фильтры сбрасывались.
        return False
