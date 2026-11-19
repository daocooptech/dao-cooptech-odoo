# -*- coding: utf-8 -*-
"""Фото карточки «ДАО КООПТЕХ» — картинки владельца и снимки платформы.

Владелец 19.11.2026: «фото замени, две которые я скинул, скрин страницы
человека, организации, проекта, навыка, вакансии, кошелек, токеномика».
Две картинки — файлы владельца (`new 01/images/cooptech/`); снимки —
страницы стенда под dashkevich, 1440×900, демо-записи (человек, ДАО «Сеть
взаимопомощи», проект, навык, вакансия), кошелёк и биржа токеномики.
Всё прежнее у карточки снимается: демо-фото без подписи и экраны
дизайн-системы из 20.0.1.6.6.
"""
import logging

from odoo import SUPERUSER_ID, api
from odoo.tools.binary import BinaryBytes
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)

PHOTOS = [
    ('01-gorod-budushchego.jpg', 'Город будущего — The Venus Project'),
    ('02-detsentralizatsiya.jpg', 'Децентрализованная сеть'),
    ('03-chelovek.jpg', 'Страница человека'),
    ('04-organizatsiya.jpg', 'Страница организации'),
    ('05-proekt.jpg', 'Страница проекта'),
    ('06-navyk.jpg', 'Страница навыка'),
    ('07-vakansiya.jpg', 'Страница вакансии'),
    ('08-koshelek.jpg', 'Кошелёк'),
    ('09-tokenomika.jpg', 'Токеномика — биржа'),
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    card = env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)
    if not card:
        return
    Media = env['coop.media']
    Media.search([('res_model', '=', 'coop.project'), ('res_id', '=', card.id)]).unlink()
    for sequence, (name, caption) in enumerate(PHOTOS, start=1):
        # В Odoo 20 двоичное поле принимает BinaryValue, а не байты/base64.
        with open(file_path(f'coop_bounty/static/img/cooptech/{name}'), 'rb') as image:
            data = BinaryBytes(image.read(), filename=name)
        Media.create({'res_model': 'coop.project', 'res_id': card.id, 'kind': 'photo',
                      'sequence': sequence * 10, 'name': caption, 'image_1920': data})
    _logger.info('Карточка нашего проекта: %s фото', len(PHOTOS))
