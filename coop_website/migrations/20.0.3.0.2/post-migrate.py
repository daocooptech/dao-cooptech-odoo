# -*- coding: utf-8 -*-
"""Значок вкладки сайта — нынешний логотип платформы.

Значок ставится из `cooptech-logo.png` один раз и запоминается признаком
`coop_website.favicon_set`. Поставили его, когда в файле ещё был старый
знак «DC»; логотип потом заменили, а значок так и остался «DC»
(владелец 12.11.2026: «почему на лендинге не наш логотип везде»).

Движок режет значок по центру в квадрат 256×256: от слова «coop»
осталась бы середина. Поэтому логотип вписывается в квадрат на своей
чёрной подложке целиком. Поле ждёт сырые байты картинки, не base64.
"""
import os

from odoo import SUPERUSER_ID, api
from odoo.addons.coop_website.models.coop_landing import LOGO, square_logo


def migrate(cr, version):
    if not os.path.exists(LOGO):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['website'].search([]).write({'favicon': square_logo()})
