# -*- coding: utf-8 -*-
"""Ежедневный снимок показателей «Моего аккаунта» (решение 473).

Искры в плитках — ход показателя за год. Восстанавливать его каждый раз по
записям нельзя честно: подписчики, сообщества и доверие меняются задним
числом (отписался, вышел, отзыв поправили), и вчерашняя искра сегодня
рисовалась бы иначе. Поэтому раз в сутки показатели плиток сохраняются
снимком, а искра читает снимки.

Истории до первого снимка нет — её один раз восстанавливают по
существующим записям: на конец каждого из прошлых одиннадцати месяцев,
с пометкой «восстановлен». Дальше она копится по-настоящему.
"""
import calendar
import datetime

from odoo import api, fields, models

# Показатель снимка → поле плитки на карточке участника.
METRICS = {
    'friends': 'coop_friend_count',
    'followers': 'coop_follower_count',
    'activity': 'coop_activity_30',
    'deals': 'coop_deal_count',
    'trust': 'coop_trust',
    'projects': 'coop_project_count',
    'communities': 'coop_community_count',
    'coops': 'coop_membership_count',
}


class CoopAccountSnapshot(models.Model):
    _name = 'coop.account.snapshot'
    _description = 'Снимок показателей аккаунта'
    _order = 'date desc, id desc'
    _rec_name = 'date'

    partner_id = fields.Many2one('res.partner', string='Участник', required=True,
                                 index=True, ondelete='cascade')
    date = fields.Date(string='На дату', required=True, index=True)
    restored = fields.Boolean(string='Восстановлен по записям',
                              help='История до первого снимка: собрана по существующим '
                                   'записям на конец месяца.')
    friends = fields.Integer(string='Друзей')
    followers = fields.Integer(string='Подписчиков')
    activity = fields.Integer(string='Действий за 30 дней')
    deals = fields.Integer(string='Сделок')
    trust = fields.Integer(string='Уровень доверия, %')
    projects = fields.Integer(string='Проектов')
    communities = fields.Integer(string='Сообществ')
    coops = fields.Integer(string='Кооперативов')

    _partner_date_unique = models.Constraint(
        'unique(partner_id, date)',
        'На одну дату у участника — один снимок.',
    )

    @api.model
    def _coop_scope(self):
        # «Мой аккаунт» открывают люди со входом на платформу — их и снимаем.
        return self.env['res.users'].sudo().with_context(active_test=True).search(
            [('partner_id', '!=', False)]).partner_id

    @api.model
    def _coop_restore(self, partners):
        """Прошлые одиннадцать месяцев по записям — тем, у кого снимков нет."""
        have = {partner.id for partner, _n in self.sudo()._read_group(
            [('partner_id', 'in', partners.ids)], ['partner_id'], ['__count'])}
        fresh = partners.filtered(lambda p: p.id not in have)
        if not fresh:
            return 0
        months = fresh._coop_year_months()[:-1]
        series = fresh._coop_rebuild_months()
        rows = []
        for partner in fresh:
            values = series[partner.id]
            for i, (y, m) in enumerate(months):
                row = {name: values[name][i] for name in METRICS}
                row.update(partner_id=partner.id, restored=True,
                           date=datetime.date(y, m, calendar.monthrange(y, m)[1]))
                rows.append(row)
        self.sudo().create(rows)
        return len(fresh)

    @api.model
    def _cron_snapshot(self):
        """Снимок на сегодня; кому истории не хватает — сперва восстановить."""
        partners = self._coop_scope()
        self._coop_restore(partners)
        today = fields.Date.context_today(self)
        Snapshot = self.sudo()
        for start in range(0, len(partners), 200):
            chunk = partners[start:start + 200].sudo()
            Snapshot.search([('partner_id', 'in', chunk.ids), ('date', '=', today)]).unlink()
            Snapshot.create([
                dict({name: partner[field] or 0 for name, field in METRICS.items()},
                     partner_id=partner.id, date=today)
                for partner in chunk])
            chunk.invalidate_recordset()
        return len(partners)
