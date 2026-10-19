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
        [('on', 'Подключено'), ('installing', 'Устанавливается'),
         ('off', 'Не подключено')],
        string='В моём меню', compute='_compute_coop_connect_state',
        search='_search_coop_connect_state',
        help='У того лица, от имени которого вы сейчас действуете.')
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
        modules = set(self._coop_base_modules())
        if not self._coop_face_is_org():
            # У человека в меню стоят ещё и выданные платформой пункты —
            # «Документы», «Аукционы»… — без записи о подключении. Их модули
            # узнаются по действию пункта.
            items = self.env['coop.sidebar.item'].sudo().search([
                ('user_id', '=', self.env.user.id), ('section', '=', 'ext'),
                ('action_id', '!=', False)])
            modules |= set(self._coop_action_modules(items.mapped('action_id').ids).values())
        if modules:
            for ext in self.sudo().search([('module_name', 'in', list(modules)),
                                           ('is_installed', '=', True)]):
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
        if entry[2] and not self.env['coop.sidebar.item']._coop_can_open(user, entry[2]):
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
