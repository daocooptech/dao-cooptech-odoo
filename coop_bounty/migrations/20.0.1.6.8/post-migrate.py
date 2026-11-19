# -*- coding: utf-8 -*-
"""Второе фото карточки «ДАО КООПТЕХ» — карта децентрализованной сети.

Владелец 19.11.2026: «вторую замени» — вместо пары «централизованная /
децентрализованная сеть» одна карта «Децентрализованная сеть» (файл
владельца, `new 01/images/cooptech/2.jpg`).
"""
import logging

from odoo import SUPERUSER_ID, api
from odoo.tools.binary import BinaryBytes
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)

NAME = '02-detsentralizatsiya.jpg'
CAPTION = 'Децентрализованная сеть'


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    card = env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)
    if not card:
        return
    second = env['coop.media'].search([('res_model', '=', 'coop.project'),
                                       ('res_id', '=', card.id), ('sequence', '=', 20)], limit=1)
    # В Odoo 20 двоичное поле принимает BinaryValue, а не байты/base64.
    with open(file_path(f'coop_bounty/static/img/cooptech/{NAME}'), 'rb') as image:
        data = BinaryBytes(image.read(), filename=NAME)
    values = {'name': CAPTION, 'image_1920': data}
    if second:
        second.write(values)
    else:
        env['coop.media'].create({'res_model': 'coop.project', 'res_id': card.id,
                                  'kind': 'photo', 'sequence': 20, **values})
    _logger.info('Карточка нашего проекта: второе фото заменено')
