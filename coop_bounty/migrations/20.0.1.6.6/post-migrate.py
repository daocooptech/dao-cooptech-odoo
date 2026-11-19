# -*- coding: utf-8 -*-
"""Карточка нашего проекта «ДАО КООПТЕХ» — правдивое описание и экраны.

Владелец 19.11.2026: «Наполнить» карточку (фото, описание), «нужно
вставить правдивое описание, задачи сделаем скоро интеграцию в 2 стороны,
задача такая стоит» — задачи и потребности не выдумываются, их принесёт
синхронизация доски с vault (№ 452). Город не ставится: правды о нём нет.

Описание — только из проверяемого: решения 183, 157, 266, 670, 690,
фонд и токен — `coop_bounty_data.xml`, история задач — `Задачи/` vault
(первая — 04.08.2026). Фото — экраны платформы из дизайн-системы
(`.claude/design-system/screens/`).
"""
import logging

from odoo import SUPERUSER_ID, api
from odoo.tools.binary import BinaryBytes
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)

DESCRIPTION = """
<p>ДАО КООПТЕХ — децентрализованная социально-экономическая платформа: люди
и организации находят друг друга, договариваются о сделках и вместе
собирают проекты. Платформа задумана как онлайн-акселератор, на котором
проверяют экономические модели кооперации.</p>
<p>Проекты собираются краудресурсингом: вклад вносят не только деньгами, но
и трудом, техникой, материалами, помещением, знаниями. Доля участника —
его вклад, делённый на сумму всех вкладов проекта.</p>
<p>Сеть строится из узлов: данные узла остаются у его владельца, узлы
обмениваются по открытому протоколу. Протокол, эталон и модули платформы
открыты на GitHub (daocooptech).</p>
<p>Сейчас работает MVP на движке Odoo 20 (Rudoo): люди, навыки, вакансии,
ресурсы, проекты, организации, сообщества, кошелёк, сделки, нематериальные
и цифровые активы, расширения. Работа идёт с 4 августа 2026 года, задачи
ведутся открытым списком.</p>
<p>Задачи проекта выставлены в краудсорсинг за токены COOP из фонда
100 000 COOP на 13 ноября 2026 — 12 февраля 2027 года. COOP — предоплата
услуг платформы: 1 COOP = 1 ₽ по цене услуг, в деньги не выводится.</p>
<p>Ближайшая цель — до 20 декабря 2026 года: ещё 5 проектов, 5 организаций
и 15 человек на платформе.</p>
"""

SCREENS = [
    ('09-grafiki-analitika.png', 'Аналитика'),
    ('17-tsifrovye-aktivy.png', 'Цифровые активы'),
    ('13-kalendar-sobytiy.png', 'Календарь событий'),
    ('18-mezhdunarodnye-sdelki.png', 'Международные сделки'),
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    card = env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)
    if not card:
        return
    card.description = DESCRIPTION
    if card.project_id:
        card.project_id.description = DESCRIPTION
    # Фото без подписи положило демо 17.11 — стройка и леса из общего
    # набора, к платформе отношения не имеют. Экраны — с подписями, по
    # ним же повторный прогон узнаёт, что они уже лежат.
    Media = env['coop.media']
    mine = Media.search([('res_model', '=', 'coop.project'), ('res_id', '=', card.id)])
    mine.filtered(lambda media: not media.name).unlink()
    have = set(mine.exists().mapped('name'))
    for sequence, (name, caption) in enumerate(SCREENS, start=1):
        if caption in have:
            continue
        # В Odoo 20 двоичное поле принимает BinaryValue, а не байты/base64.
        with open(file_path(f'coop_bounty/static/img/cooptech/{name}'), 'rb') as image:
            data = BinaryBytes(image.read(), filename=name)
        Media.create({'res_model': 'coop.project', 'res_id': card.id, 'kind': 'photo',
                      'sequence': sequence * 10, 'name': caption, 'image_1920': data})
    _logger.info('Карточка нашего проекта: описание и %s экрана', len(SCREENS))
