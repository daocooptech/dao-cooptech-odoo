# -*- coding: utf-8 -*-
"""Фотографии тем участникам, кому их не досталось.

Часть людей заведена не каталогом, а справочными данными — те, на кого
ссылаются членство, сделка и учётная запись пайщика. Фотографии у них не
было, и на странице человека, в полосе «Друзья» и в составе организации
они выглядели серыми кружками с буквой.

Пустая карточка — это состояние, которое должно попадаться при проверке,
но не у четверти каталога сразу: тогда не видно, как выглядит полоса из
плиток с лицами, ради которой она и сделана.
"""
import base64
import logging
import os

_logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
AVATAR_DIR = os.path.join(os.path.dirname(HERE), 'static', 'img', 'avatars')


def load_faces(env):
    """Раздать фотографии участникам без изображения."""
    if not os.path.isdir(AVATAR_DIR):
        _logger.info('Фотографии: папка %s не найдена', AVATAR_DIR)
        return 0

    files = sorted(name for name in os.listdir(AVATAR_DIR)
                   if name.lower().endswith(('.jpg', '.jpeg', '.png')))
    if not files:
        return 0

    Partner = env['res.partner'].sudo()
    members = env['coop.membership'].sudo().search([]).mapped('partner_id')
    without = Partner.search([
        ('id', 'in', members.ids),
        ('is_company', '=', False),
        ('image_1920', '=', False),
    ])

    given = 0
    for index, partner in enumerate(without):
        # По остатку от номера записи, а не случайно: повторный прогон
        # даёт тем же людям те же лица, и снимки на экране не пляшут от
        # пересборки к пересборке.
        path = os.path.join(AVATAR_DIR, files[partner.id % len(files)])
        with open(path, 'rb') as handle:
            partner.image_1920 = base64.b64encode(handle.read())
        given += 1

    _logger.info('Фотографии: выдано %s из %s участников', given, len(members))
    return given
