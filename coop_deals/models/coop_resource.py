# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import _, api, fields, models


class CoopResource(models.Model):
    """Покупатели ресурса — со страницы самого ресурса.

    В дизайн-макете у карточки ресурса был блок «Покупатели» с отбором
    (решения 10, 14 и 16 журнала владельца). На движке данные были —
    сделка знает свой ресурс (`coop.deal.resource_id`), — а со страницы
    ресурса к ним не вело ничего: ни числа, ни перехода. Ревизия макета и
    MVP 22 сентября 2026 записала это расхождением.

    Живёт здесь, а не в `coop_resources`: сделки зависят от ресурсов, а не
    наоборот, и ресурс о сделках знать не должен.
    """
    _inherit = 'coop.resource'

    coop_buyer_count = fields.Integer(
        string='Покупатели', compute='_compute_coop_buyer_count')

    def _compute_coop_buyer_count(self):
        # Покупатель — вторая сторона сделки (`party_b_id`): так сделка
        # сама раскладывает роли — «покупатель, арендатор, заказчик»
        # (подсказка у `role_b`). Считаем людей, а не сделки: один
        # покупатель, купивший трижды, — один покупатель.
        #
        # Раньше считались обе стороны за вычетом хозяина объявления, и
        # у сварочного полуавтомата с семью сделками выходило четырнадцать
        # покупателей: продавцом в сделке бывает не хозяин объявления.
        # Без обхода прав: число должно совпадать с тем, что человек увидит,
        # перейдя по ссылке. Сделка видна только её сторонам, и со счётом
        # в обход прав выходило «Покупатели: 7» при одной сделке в списке.
        groups = self.env['coop.deal']._read_group(
            [('resource_id', 'in', self.ids), ('party_b_id', '!=', False)],
            ['resource_id'], ['party_b_id:count_distinct'])
        counts = {resource.id: count for resource, count in groups}
        for resource in self:
            resource.coop_buyer_count = counts.get(resource.id, 0)

    def action_coop_buyers(self):
        """Сделки по ресурсу — в обычном каталоге сделок, с его отборами.

        Отдельного экрана «Покупатели» не заводим: каталог сделок уже
        умеет искать, отбирать по состоянию и городу и группировать, а
        второй экран с тем же содержимым разошёлся бы с ним при первой же
        правке.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Покупатели: %(name)s', name=self.name),
            'res_model': 'coop.deal',
            'view_mode': 'list,kanban,form',
            'domain': [('resource_id', '=', self.id)],
            'context': {'create': False},
        }

    # ── Отзывы о владельце ───────────────────────────────────────────────
    #
    # Эталон `ResourcePage` (решение 625): под описанием — сводка оценок
    # и последние отзывы о хозяине объявления. Отзывы жили в сделках и на
    # странице ресурса не выводились, хотя «кому я плачу» — первый вопрос
    # того, кто нашёл нужное. Берём только раскрытые: пока второй отзыв не
    # написан, первый не видит никто (правило `coop.deal.review`).
    owner_review_count = fields.Integer(
        string='Отзывов о владельце', compute='_compute_owner_reviews')
    owner_reviews_html = fields.Html(
        string='Отзывы о владельце', compute='_compute_owner_reviews', sanitize=False)

    MONTHS = ('янв.', 'февр.', 'марта', 'апр.', 'мая', 'июня',
              'июля', 'авг.', 'сент.', 'окт.', 'нояб.', 'дек.')

    @api.depends('owner_id')
    def _compute_owner_reviews(self):
        Review = self.env['coop.deal.review'].sudo()
        for resource in self:
            reviews = Review.search([('target_id', '=', resource.owner_id.id),
                                     ('visible', '=', True)]) if resource.owner_id else Review
            resource.owner_review_count = len(reviews)
            resource.owner_reviews_html = resource._coop_reviews_markup(reviews) if reviews else False

    def _coop_reviews_markup(self, reviews):
        """Сводка (средняя, звёзды, полосы по оценкам) и три последних отзыва."""
        rates = [int(r.rating) for r in reviews]
        avg = sum(rates) / len(rates)
        bars = Markup('').join(
            Markup('<div><span>%s</span><em><i style="width:%s%%"></i></em><span>%s</span></div>') % (
                n, round(rates.count(n) * 100 / len(rates)), rates.count(n))
            for n in (5, 4, 3, 2, 1))
        head = Markup(
            '<div class="coop-score"><b>%s</b><div>%s<div class="coop-score_sub">%s</div></div>'
            '<div class="coop-score_bars">%s</div></div>') % (
            ('%.1f' % avg).replace('.', ','), self._coop_stars(round(avg)),
            _('%(n)s по сделкам', n=self._coop_reviews_word(len(rates))), bars)
        rows = Markup('').join(self._coop_review_row(r) for r in reviews[:3])
        return head + rows

    @staticmethod
    def _coop_reviews_word(n):
        if n % 10 == 1 and n % 100 != 11:
            word = 'отзыв'
        elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            word = 'отзыва'
        else:
            word = 'отзывов'
        return '%s %s' % (n, word)

    @staticmethod
    def _coop_stars(value):
        return Markup('<span class="coop-stars" aria-label="%s из 5">%s</span>') % (
            value, Markup('').join(
                Markup('<i class="%s">★</i>') % ('on' if i < value else 'off') for i in range(5)))

    def _coop_review_row(self, review):
        author = review.author_id
        when = review.create_date
        date = '%s %s' % (when.day, self.MONTHS[when.month - 1]) if when else ''
        meta = ' · '.join(filter(None, [review.deal_id.number, date]))
        pic = Markup('<img src="/web/image/res.partner/%s/avatar_128" alt=""/>') % author.id
        body = Markup('<p>%s</p>') % review.body if review.body else ''
        return Markup(
            '<div class="coop-rev"><div class="coop-rev_head"><span class="coop-rev_pic">%s</span>'
            '<div><b>%s</b><span>%s</span></div><div class="coop-rev_rate">%s</div></div>%s</div>') % (
            pic, author.display_name, meta, self._coop_stars(int(review.rating)), body)

    def action_coop_owner_reviews(self):
        """Все раскрытые отзывы о владельце — обычным списком отзывов."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Отзывы: %(name)s', name=self.owner_id.display_name),
            'res_model': 'coop.deal.review',
            'view_mode': 'list',
            'domain': [('target_id', '=', self.owner_id.id), ('visible', '=', True)],
            'context': {'create': False},
        }
