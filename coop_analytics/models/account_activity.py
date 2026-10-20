# -*- coding: utf-8 -*-
"""Активность аккаунта для «Аналитики» (владелец 26.09.2026: «в аналитику
можно добавить информацию по самому аккаунту — количество друзей,
подписчиков, активности»).

Отчёт на представлении базы: одна строка — одно действие участника с датой
и видом. Источники — то, что платформа уже хранит: записи на стене и в
сообществах, сообщения, комментарии, сделки, новые друзья, пройденные
уроки, обмены на бирже, вклады в проекты. Подписчиков здесь нет: время
подписки движок не хранит (`mail.followers` без дат), их число — на
карточке «Мой аккаунт».
"""
import datetime

from odoo import api, fields, models, tools

KINDS = [
    ('post', 'Записи'),
    ('message', 'Сообщения'),
    ('comment', 'Комментарии'),
    ('deal', 'Сделки'),
    ('friend', 'Новые друзья'),
    ('lesson', 'Пройденные уроки'),
    ('dex', 'Обмены на бирже'),
    ('contribution', 'Вклады в проекты'),
]


class CoopAccountActivity(models.Model):
    _name = 'coop.account.activity'
    _description = 'Активность аккаунта'
    _auto = False
    _order = 'date desc'

    partner_id = fields.Many2one('res.partner', string='Участник', readonly=True)
    date = fields.Datetime(string='Когда', readonly=True)
    kind = fields.Selection(KINDS, string='Что', readonly=True)
    count = fields.Integer(string='Действий', readonly=True, aggregator='sum')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT row_number() OVER () AS id, partner_id, date, kind, 1 AS count
                  FROM (
                    SELECT author_id AS partner_id, date,
                           CASE WHEN model = 'discuss.channel' THEN 'message' ELSE 'post' END AS kind
                      FROM mail_message
                     WHERE message_type = 'comment' AND author_id IS NOT NULL
                       AND model IN ('res.partner', 'coop.community', 'coop.project', 'discuss.channel')
                    UNION ALL
                    SELECT author_id, date, 'comment' FROM coop_wall_comment
                     WHERE author_id IS NOT NULL
                    UNION ALL
                    SELECT party_a_id, signed_on::timestamp, 'deal' FROM coop_deal
                     WHERE party_a_id IS NOT NULL AND signed_on IS NOT NULL
                    UNION ALL
                    SELECT party_b_id, signed_on::timestamp, 'deal' FROM coop_deal
                     WHERE party_b_id IS NOT NULL AND signed_on IS NOT NULL
                    UNION ALL
                    SELECT requester_id, write_date, 'friend' FROM coop_friendship
                     WHERE state = 'accepted'
                    UNION ALL
                    SELECT addressee_id, write_date, 'friend' FROM coop_friendship
                     WHERE state = 'accepted'
                    UNION ALL
                    SELECT partner_id, write_date, 'lesson' FROM slide_slide_partner
                     WHERE completed
                    UNION ALL
                    SELECT t.taker_id, t.date, 'dex' FROM coop_crypto_trade t
                    UNION ALL
                    SELECT o.author_id, t.date, 'dex' FROM coop_crypto_trade t
                      JOIN coop_crypto_offer o ON o.id = t.offer_id
                    UNION ALL
                    SELECT partner_id, create_date, 'contribution' FROM coop_project_contribution
                     WHERE partner_id IS NOT NULL
                  ) AS events
                 WHERE partner_id IS NOT NULL AND date IS NOT NULL
            )
        """ % self._table)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_activity_30 = fields.Integer(string='Действий за 30 дней',
                                      compute='_compute_coop_activity_30')
    # «Это я» — отбор без номера пользователя в домене. Виджеты «Моей
    # панели» подставляют свой отбор вместо отбора действия, и `[uid]` в
    # нём не всегда вычисляется: «Мой аккаунт» на панели показывал всех
    # участников (найдено на копии боевой 26.09).
    coop_is_me = fields.Boolean(compute='_compute_coop_is_me', search='_search_coop_is_me')

    def _compute_coop_is_me(self):
        me = self.env.user.partner_id
        for partner in self:
            partner.coop_is_me = partner == me

    def _search_coop_is_me(self, operator, value):
        # Odoo 19 приводит ('coop_is_me', '=', True) к ('coop_is_me', 'in', [True]):
        # разбираем оба вида, иначе «это я» находит всех, кроме меня.
        if operator in ('in', 'not in'):
            wanted = True in value
            positive = wanted if operator == 'in' else not wanted
        else:
            positive = (operator == '=') == bool(value)
        return [('id', 'in' if positive else 'not in', [self.env.user.partner_id.id])]

    # График «Активность» под плитками «Моего аккаунта» (эталон
    # AnalyticsAccountPage, LineChart): действия по месяцам за год и средний
    # месяц пунктиром. Рисуется на сервере готовым SVG: плитки — канбан,
    # своего компонента графика в нём нет, а данные — одна группировка.
    coop_activity_chart = fields.Html(string='Активность по месяцам',
                                      compute='_compute_coop_activity_chart',
                                      sanitize=False)

    MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн',
              'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

    def _compute_coop_activity_chart(self):
        from markupsafe import Markup, escape
        today = fields.Date.context_today(self)
        start = today.replace(day=1)
        months = []
        for back in range(11, -1, -1):
            y, m = start.year, start.month - back
            while m < 1:
                y, m = y - 1, m + 12
            months.append((y, m))
        since = fields.Datetime.to_datetime('%04d-%02d-01' % months[0])
        rows = self.env['coop.account.activity'].sudo()._read_group(
            [('partner_id', 'in', self.ids), ('date', '>=', since)],
            ['partner_id', 'date:month'], ['count:sum'])
        by = {}
        for partner, month, total in rows:
            by[(partner.id, month.year, month.month)] = total
        for partner in self:
            values = [by.get((partner.id, y, m), 0) for y, m in months]
            top = max(values + [1])
            # Шкала до «круглого» числа: 4 деления, как у LineChart.
            step = 1
            for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
                step = s
                if s * 4 >= top:
                    break
            vmax = step * 4
            avg = sum(values) / len(values)
            # Как LineChart эталона: поле 600×200 растягивается по ширине,
            # линия — плавная (кубические кривые через середины), под ней
            # штриховка, линейки на ¼, ½, ¾ и верхе; подписи осей — HTML
            # рядом с полем, а не текст внутри растянутого SVG.
            w, h = 600, 200
            pts = [(i * w / 11.0, h - v * h / float(vmax)) for i, v in enumerate(values)]
            line = 'M%.1f %.1f' % pts[0]
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                mx = (x0 + x1) / 2
                line += ' C%.1f %.1f %.1f %.1f %.1f %.1f' % (mx, y0, mx, y1, x1, y1)
            area = '%s L%d %d L0 %d Z' % (line, w, h, h)
            ya = h - avg * h / float(vmax)
            rules = ''.join('<line class="o_coop_an_rule" x1="0" x2="%d" y1="%.1f" y2="%.1f"/>'
                            % (w, h - g * h, h - g * h) for g in (0.25, 0.5, 0.75, 1))
            svg = (
                '<svg viewBox="0 0 %d %d" preserveAspectRatio="none" aria-hidden="true">'
                '<defs><pattern id="o_coop_an_hatch" width="6" height="6" '
                'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
                '<line x1="0" y1="0" x2="0" y2="6" class="o_coop_an_hatch"/></pattern></defs>'
                '%s<path d="%s" fill="url(#o_coop_an_hatch)" stroke="none"/>'
                '<path d="%s" fill="none" class="o_coop_an_line"/>'
                '<path d="M0 %.1f L%d %.1f" fill="none" class="o_coop_an_line o_coop_an_dashed"/>'
                '</svg>') % (w, h, rules, area, line, ya, w, ya)
            ticks = ''.join('<span>%d</span>' % (step * k) for k in range(4, -1, -1))
            labels = ''.join('<span>%s</span>' % self.MONTHS[m - 1] for _y, m in months)
            partner.coop_activity_chart = Markup(
                '<div class="o_coop_an_panel">'
                '<div class="o_coop_an_panel_head"><h3>Активность</h3>'
                '<a href="/odoo/analytics-activity" class="btn btn-secondary btn-sm">Вся активность</a></div>'
                '<figure class="o_coop_an_chart" role="img" aria-label="Действий по месяцам: %s">'
                '<ul class="o_coop_an_keys"><li><i class="o_coop_an_key"></i>действий в месяц</li>'
                '<li><i class="o_coop_an_key o_coop_an_key_dash"></i>средний месяц <b>%s</b></li></ul>'
                '<div class="o_coop_an_plot"><div class="o_coop_an_axis" aria-hidden="true">%s</div>'
                '<div class="o_coop_an_box">%s<div class="o_coop_an_x">%s</div></div></div>'
                '<figcaption class="o_coop_an_caption">Записи, сообщения, комментарии, сделки, '
                'новые друзья, уроки, обмены и вклады — по месяцам.</figcaption></figure></div>'
                % (escape(', '.join(str(v) for v in values)),
                   escape(('%.1f' % avg).replace('.', ',').replace(',0', '')),
                   Markup(ticks), Markup(svg), Markup(labels)))

    # Искры в плитках «Моего аккаунта» (эталон AnalyticsAccountPage, Spark):
    # справа от числа — ход за год, двенадцать штрихов по месяцам, текущий
    # выделен. Штрих — показатель плитки на конец месяца по ежедневным
    # снимкам (`coop.account.snapshot`, решение 473), текущий — то же число,
    # что в плитке.
    coop_spark_friends = fields.Html(compute='_compute_coop_sparks', sanitize=False)
    coop_spark_followers = fields.Html(compute='_compute_coop_sparks', sanitize=False)
    coop_spark_activity = fields.Html(compute='_compute_coop_sparks', sanitize=False)
    coop_spark_deals = fields.Html(compute='_compute_coop_sparks', sanitize=False)
    coop_spark_trust = fields.Html(compute='_compute_coop_sparks', sanitize=False)
    coop_spark_projects = fields.Html(compute='_compute_coop_sparks', sanitize=False)
    coop_spark_communities = fields.Html(compute='_compute_coop_sparks', sanitize=False)
    coop_spark_coops = fields.Html(compute='_compute_coop_sparks', sanitize=False)

    SPARKS = [
        ('friends', 'coop_spark_friends', 'друзей'),
        ('followers', 'coop_spark_followers', 'подписчиков'),
        ('activity', 'coop_spark_activity', 'действий за 30 дней'),
        ('deals', 'coop_spark_deals', 'сделок'),
        ('trust', 'coop_spark_trust', 'уровень доверия, %'),
        ('projects', 'coop_spark_projects', 'проектов'),
        ('communities', 'coop_spark_communities', 'сообществ'),
        ('coops', 'coop_spark_coops', 'кооперативов'),
    ]

    def _coop_year_months(self):
        start = fields.Date.context_today(self).replace(day=1)
        months = []
        for back in range(11, -1, -1):
            y, m = start.year, start.month - back
            while m < 1:
                y, m = y - 1, m + 12
            months.append((y, m))
        return months

    @staticmethod
    def _coop_spark(values, label):
        from markupsafe import Markup, escape
        top = max(values + [1])
        bars = ''.join(
            '<i%s style="height:%d%%"></i>' % (
                ' class="o_coop_spark_on"' if i == len(values) - 1 else '',
                max(8, round(v * 100.0 / top)))
            for i, v in enumerate(values))
        return Markup('<span class="o_coop_spark" role="img" aria-label="%s">%s</span>' % (
            escape('%s: ход за год — %s' % (label, ', '.join(str(v) for v in values))),
            bars))

    def _compute_coop_sparks(self):
        from .account_snapshot import METRICS
        months = self._coop_year_months()
        keys = [y * 12 + m for y, m in months]
        since = datetime.date(months[0][0], months[0][1], 1)
        last = {}
        # По возрастанию даты: в месяце остаётся последний снимок.
        for snap in self.env['coop.account.snapshot'].sudo().search(
                [('partner_id', 'in', self.ids), ('date', '>=', since)], order='date, id'):
            last[(snap.partner_id.id, snap.date.year * 12 + snap.date.month)] = snap
        for partner in self:
            for metric, field, label in self.SPARKS:
                values = [last[(partner.id, month)][metric] if (partner.id, month) in last else 0
                          for month in keys[:-1]]
                values.append(partner[METRICS[metric]] or 0)
                partner[field] = self._coop_spark(values, label)

    def _coop_rebuild_months(self):
        """Показатели плиток на конец каждого из двенадцати месяцев — по записям.

        Для истории до первого снимка (решение 473). Запасы (друзья,
        подписчики, сделки, проекты, сообщества, кооперативы) — сколько
        набралось к концу месяца; действия — сколько за месяц; доверие —
        доля положительных отзывов к концу месяца, как считается сейчас.
        """
        months = self._coop_year_months()
        keys = [y * 12 + m for y, m in months]

        def key(day):
            return day.year * 12 + day.month

        def stock(dates):
            marks = sorted(key(d) for d in dates if d)
            return [sum(1 for k in marks if k <= month) for month in keys]

        Deal = self.env['coop.deal'].sudo()
        Review = self.env['coop.deal.review'].sudo()
        Friendship = self.env['coop.friendship'].sudo()
        Followers = self.env['mail.followers'].sudo()
        Project = self.env['coop.project'].sudo()
        Membership = self.env['coop.membership'].sudo()
        Member = self.env['coop.community.member'].sudo() \
            if 'coop.community.member' in self.env else None
        since = fields.Datetime.to_datetime('%04d-%02d-01' % months[0])
        activity = {}
        for partner, month, total in self.env['coop.account.activity'].sudo()._read_group(
                [('partner_id', 'in', self.ids), ('date', '>=', since)],
                ['partner_id', 'date:month'], ['count:sum']):
            activity[(partner.id, month.year * 12 + month.month)] = total

        result = {}
        for partner in self:
            links = Friendship.search([
                ('state', '=', 'accepted'),
                '|', ('requester_id', '=', partner.id), ('addressee_id', '=', partner.id)])
            deals = Deal.search(['|', ('party_a_id', '=', partner.id),
                                 ('party_b_id', '=', partner.id)])
            # Отзыв датируется закрытием сделки: оставляют его, когда
            # сделка завершена.
            reviews = [((r.deal_id.closed_on or r.create_date.date()), r.rating in ('4', '5'))
                       for r in Review.search([('target_id', '=', partner.id)])]
            trust = []
            for month in keys:
                seen = [good for day, good in reviews if key(day) <= month]
                trust.append(round(sum(seen) * 100.0 / len(seen)) if seen else 0)
            result[partner.id] = {
                'friends': stock([(l.write_date or l.create_date).date() for l in links]),
                'followers': stock([f.create_date.date() for f in Followers.search([
                    ('res_model', '=', 'res.partner'), ('res_id', '=', partner.id)])
                    if f.create_date]),
                'activity': [activity.get((partner.id, month), 0) for month in keys],
                'deals': stock([d.signed_on or d.create_date.date() for d in deals]),
                'trust': trust,
                'projects': stock([p.create_date.date() for p in Project.search(
                    [('partner_id', '=', partner.id)])]),
                'communities': stock([m.joined_on or m.create_date.date() for m in Member.search([
                    ('partner_id', '=', partner.id), ('state', '=', 'active')])]) if Member is not None else [0] * 12,
                'coops': stock([m.joined_on or m.create_date.date() for m in Membership.search([
                    ('partner_id', '=', partner.id), ('state', '=', 'active')])]),
            }
        return result

    def _compute_coop_activity_30(self):
        since = fields.Datetime.subtract(fields.Datetime.now(), days=30)
        groups = dict(self.env['coop.account.activity'].sudo()._read_group(
            [('partner_id', 'in', self.ids), ('date', '>=', since)], ['partner_id'], ['count:sum']))
        for partner in self:
            partner.coop_activity_30 = groups.get(partner, 0)
