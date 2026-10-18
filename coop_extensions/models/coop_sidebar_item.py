# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.addons.coop_theme.models.coop_sidebar_item import (
    EXTENSION_ITEMS, MODEL_HINTS, REQUIRES)


class CoopSidebarItem(models.Model):
    """Меню по лицу (решения 463, 468).

    Разделы платформы одинаковы у всех. Расширения — по лицу, от имени
    которого человек действует: у человека — его личное меню, у
    организации — общее меню её представителей, которое ведёт руководитель.
    До 18 октября 2026 переключатель «действую от имени» меню не менял
    вовсе, и у организации своих расширений не было.
    """
    _inherit = 'coop.sidebar.item'

    extension_id = fields.Many2one(
        'coop.extension', string='Расширение', ondelete='cascade',
        help='Пункт, подключённый из каталога. Пока модуля на платформе нет, '
             'пункт стоит с пометкой «устанавливается».')

    # ── CRM — только у организаций ──────────────────────────────────────

    def _has_crm(self, user):
        """У человека CRM нет (правило владельца, решение 450): его лиды —
        обращения в «Сделках». CRM стоит в меню организации."""
        if 'crm.lead' not in self.env:
            return None
        return False

    # ── Личное меню: пункт из каталога ──────────────────────────────────

    @api.model
    def _coop_place_extension(self, user, extension, entry):
        name, icon, action_id = entry
        Item = self.sudo()
        mine = Item.search([('user_id', '=', user.id), ('section', '=', 'ext')])
        same = mine.filtered(lambda i: i.name == name)
        if same:
            same.write({'extension_id': extension.id,
                        'action_id': same.action_id.id or action_id or False})
            return same
        return Item.create({
            'user_id': user.id,
            'name': name,
            'icon': icon,
            'action_id': action_id or False,
            'extension_id': extension.id,
            'section': 'ext',
            'sequence': max(mine.mapped('sequence') or [0]) + 10,
        })

    @api.model
    def _coop_remove_extension(self, user, extension):
        Item = self.sudo()
        mine = Item.search([('user_id', '=', user.id), ('section', '=', 'ext')])
        modules = self.env['coop.extension']._coop_action_modules(
            mine.mapped('action_id').ids)
        stale = mine.filtered(
            lambda i: i.extension_id == extension
            or modules.get(i.action_id.id) == extension.module_name)
        stale.write({'is_required': False})
        stale.unlink()

    def unlink(self):
        # Убрал пункт в «Настроить меню» — подключение снимается вместе с
        # ним: иначе каталог показывал бы расширение подключённым.
        Connection = self.env['coop.extension.connection'].sudo()
        for item in self.filtered('extension_id'):
            Connection.search([('partner_id', '=', item.user_id.partner_id.id),
                               ('extension_id', '=', item.extension_id.id)]).unlink()
        return super().unlink()

    def _coop_activate_installed(self, user):
        """Модуль поставили — пункт «устанавливается» открывается сам."""
        waiting = self.sudo().search([
            ('user_id', '=', user.id), ('extension_id', '!=', False),
            ('action_id', '=', False)])
        for item in waiting.filtered(lambda i: i.extension_id.is_installed):
            entry = item.extension_id._coop_menu_entry()
            if entry and entry[2]:
                item.action_id = entry[2]

    # ── Меню организации ────────────────────────────────────────────────

    @api.model
    def _coop_seed_org(self, org):
        """Меню организации с самого начала — тот же набор, что у людей
        (владелец 18.10.2026), плюс CRM. Заводится один раз: что руководитель
        убрал, назад не возвращается."""
        Connection = self.env['coop.extension.connection'].sudo()
        if org.coop_menu_seeded:
            return
        Extension = self.env['coop.extension'].sudo()
        existing = set(Connection.search([('partner_id', '=', org.id)]).mapped(
            'extension_id').ids)
        vals = []
        for index, (_name, _icon, xmlid) in enumerate(EXTENSION_ITEMS):
            module = xmlid.split('.', 1)[0] if xmlid else False
            if not module:
                continue
            ext = Extension.search([('module_name', '=', module)], limit=1)
            if ext and ext.id not in existing:
                vals.append({'partner_id': org.id, 'extension_id': ext.id,
                             'user_id': False, 'sequence': (index + 1) * 10})
                existing.add(ext.id)
        if vals:
            Connection.create(vals)
        org.sudo().coop_menu_seeded = True

    def _coop_org_allows(self, name, user, org):
        """Пункты по участию — и в меню организации."""
        if name == 'CRM':
            if 'crm.lead' not in self.env:
                return False
            if 'coop_app_crm' in org._fields and not org.coop_app_crm:
                return False
            return user.has_group('sales_team.group_sale_salesman')
        if name in REQUIRES:
            return bool(self._requirement(name, user))
        return True

    @api.model
    def _coop_org_items(self, user, org):
        self._coop_seed_org(org)
        conns = self.env['coop.extension.connection'].sudo().search(
            [('partner_id', '=', org.id)])
        rows = []
        for conn in conns:
            entry = conn.extension_id._coop_menu_entry()
            if not entry:
                continue
            name, icon, action_id = entry
            if not self._coop_org_allows(name, user, org):
                continue
            rows.append((conn, name, icon, action_id))
        action_ids = [a for *_rest, a in rows if a]
        windows = self.env['ir.actions.act_window'].sudo().browse(action_ids).exists()
        models_by_action = {w.id: w.res_model for w in windows}
        paths = self.env['ir.actions.actions'].sudo().browse(action_ids).exists()
        path_by_action = {a.id: a.path for a in paths if a.path}
        return [{
            'id': 'org-%s' % conn.id,
            'label': name,
            'icon': icon or '',
            'actionId': action_id or False,
            'model': models_by_action.get(action_id) or MODEL_HINTS.get(name) or False,
            'path': path_by_action.get(action_id) or False,
            'section': 'ext',
            'pending': not conn.extension_id.is_installed,
        } for conn, name, icon, action_id in rows]

    @api.model
    def items_for_current_user(self):
        user = self.env.user
        self._coop_activate_installed(user)
        items = super().items_for_current_user()
        org = user.coop_acting_as_id
        if org and org != user.partner_id:
            return [i for i in items if i.get('section') != 'ext'] \
                + self._coop_org_items(user, org)
        pending = set(self.sudo().search([
            ('user_id', '=', user.id), ('extension_id', '!=', False),
            ('extension_id.is_installed', '=', False)]).ids)
        for item in items:
            if item.get('id') in pending:
                item['pending'] = True
        return items


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_menu_seeded = fields.Boolean(
        'Меню организации заведено', copy=False,
        help='Набор по умолчанию выдан. Что руководитель потом убрал, назад '
             'не возвращается.')
