# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — стена',
    'summary': 'Записи на стенах людей, организаций, проектов и сообществ: '
               'поле записи, комментарии, действия под записью',
    'description': """
Стена — лента записи движка (`mail`), поставленная под карточку участника,
организации, проекта или сообщества. Раскладку ленты и её вид задаёт
тема (`coop_theme`, `js/wall.js`); здесь — то, что делает ленту стеной
соцсети, а не журналом записи.

Поле записи: кнопки «Фото», «Видео», «Аудио», «Голосовое», «Файл»; снимок
картинкой или файлом на выбор; на телефоне «Опубликовать» галочкой и
крестик «Очистить» (решения 403, 405).

Под записью: «Оценить», «Комментировать», «В избранное»; комментарии —
своя модель `coop.wall.comment` (решение 404); репост; «Поблагодарить»
— рубли по СБП автора и токены в выбранной сети, платформа денег не
касается (решение 406).
Опросы (`coop.wall.poll`, голос не отзывается, журналом с хэшами) и
отложенная публикация на движке отложенных сообщений (решение 410).

Отдельный модуль по слову владельца 24 сентября 2026: «может эффективнее
сделать отдельный модуль» — стена не переписка (`coop_messages`) и не
оформление (`coop_theme`).
""",
    'author': 'ДАО КООПТЕХ',
    'category': 'Cooperative',
    'version': '19.0.1.2.0',
    'license': 'LGPL-3',
    'depends': ['mail', 'coop_base', 'coop_theme', 'coop_wallet', 'coop_settings',
                'coop_messages'],
    'data': [
        'security/ir.model.access.csv',
        'security/coop_wall_rules.xml',
        'views/coop_wall_settings_views.xml',
        'views/coop_wall_feed_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_wall/static/src/js/wall_photo.js',
            'coop_wall/static/src/xml/wall_photo.xml',
            'coop_wall/static/src/js/wall_composer.js',
            'coop_wall/static/src/xml/wall_composer.xml',
            'coop_wall/static/src/scss/wall_composer.scss',
            'coop_wall/static/src/js/wall_post.js',
            'coop_wall/static/src/xml/wall_post.xml',
            'coop_wall/static/src/scss/wall_post.scss',
            'coop_wall/static/src/js/wall_reaction.js',
            'coop_wall/static/src/js/wall_poll.js',
            'coop_wall/static/src/xml/wall_poll.xml',
            'coop_wall/static/src/scss/wall_poll.scss',
            'coop_wall/static/src/js/wall_feed.js',
            'coop_wall/static/src/xml/wall_feed.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
}
