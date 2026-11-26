# -*- coding: utf-8 -*-
"""№ 333, решения 490–491: отзывы во всех состояниях.

После переноса все раскрытые отзывы — давние, оспорить нечего, и
оспоренных нет. Здесь: у 24 сделок с отзывом раскрытие свежее (до
10 дней назад — «Оспорить» доступна), среди них — сделки, где оценили
dashkevich; 30 отзывов с оценкой до «Нормально» оспорены теми, о ком
написаны, с причиной. Текст отзывов не трогается.
"""
import logging
import random
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields

REASONS = [
    'Срок сдвинули по взаимному согласию, переписка в сделке.',
    'Товар принят по акту без замечаний — претензия появилась через месяц.',
    'Оплата пришла с опозданием на девять дней, отсюда и задержка отгрузки.',
    'Замечания по качеству устранены, повторный акт подписан.',
    'Отзыв о другой поставке: по этой сделке объём и сорт совпали со спецификацией.',
    'Доставку по договорённости выполнял покупатель, за сроки перевозчика не отвечаем.',
    'Недостача возмещена переводом, номер платёжного поручения — в документах сделки.',
    'Работы выполнены по смете, дополнительные — без согласования и не оплачивались.',
    'Претензии в сроки приёмки не было, акт подписан обеими сторонами.',
    'Оценка за цену, а цена была согласована в спецификации до начала работ.',
    'Брак возник при хранении у покупателя, фотографии приёмки приложены.',
    'Отменили не мы: вторая сторона не внесла предоплату по графику.',
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    rnd = random.Random(20261126)
    today = fields.Date.context_today(env['coop.deal'])
    Review = env['coop.deal.review'].sudo()
    Deal = env['coop.deal'].sudo()

    dash = env['res.users'].sudo().search([('login', '=', 'dashkevich')], limit=1)
    fresh = Deal.browse()
    if dash:
        fresh |= Review.search([('target_id', '=', dash.partner_id.id),
                                ('visible', '=', True)], limit=6).deal_id
    others = Deal.search([('reviews_visible', '=', True), ('id', 'not in', fresh.ids)],
                         order='id')
    fresh |= Deal.browse(rnd.sample(others.ids, min(18, len(others))))
    for deal in fresh:
        opened = today - timedelta(days=rnd.randint(0, 10))
        closed = opened - timedelta(days=rnd.randint(0, 14))
        deal.write({'reviews_opened_on': opened,
                    'closed_on': min(deal.closed_on or closed, closed)})

    weak = Review.search([('visible', '=', True), ('rating', 'in', ('1', '2', '3')),
                          ('disputed_on', '=', False)], order='id')
    picked = Review.browse(rnd.sample(weak.ids, min(30, len(weak))))
    for review in picked:
        opened = review.deal_id.reviews_opened_on or today
        review.with_context(coop_review_dispute=True).write({
            'disputed_on': min(today, opened + timedelta(days=rnd.randint(0, 13))),
            'disputed_by_id': review.target_id.id,
            'dispute_reason': rnd.choice(REASONS),
        })
    logging.getLogger(__name__).info(
        'Отзывы 490–491: свежее раскрытие у %s сделок, оспорено %s', len(fresh), len(picked))
