# -*- coding: utf-8 -*-
"""Имя узла в адресной строке: /nn1/my-page вместо /odoo/my-page.

Владелец 28.09.2026: «сделай что бы вместо odoo было nn1 (что означает
network node 1), что бы видно было еще в адресной строке на каком узле
ведется учет».

У каждого узла сети своё имя: здесь nn1, у следующего — nn2. Оно задаётся
строкой `coop_node_path = nn2` в odoo.conf; без неё — nn1. Имя читается при
запуске сервера: маршруты строятся один раз.

Движок по-прежнему знает только /odoo — он зашит в сотне с лишним мест:
письма, переадресации после входа, ссылки в чате. Поэтому /odoo не
отключается, а переадресует на адрес узла, а в браузере роутер движка
переводит адреса туда и обратно (`static/src/js/node_path.js`).
"""
import re

from odoo.tools import config

NODE_PATH = (config.get('coop_node_path') or 'nn1').strip().strip('/')

if not re.fullmatch(r'[a-z][a-z0-9-]{0,15}', NODE_PATH) or NODE_PATH in (
        'odoo', 'web', 'scoped_app', 'website', 'my', 'shop', 'json', 'mail'):
    raise ValueError('coop_node_path = %r: нужна латиница, до 16 знаков, '
                     'не занятая движком' % NODE_PATH)
