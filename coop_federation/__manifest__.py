# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — федерация узлов',
    'summary': 'Узел сети: did:web, ключ, подписанный журнал событий, две точки протокола',
    'description': """
Шаг 1 переноса федерации на движок (решения 108, 429, 430, 432).

Платформа становится узлом сети: у неё есть идентификатор did:web, ключ
Ed25519 и журнал событий — только дописываемый, связанный хэшами,
подписанный. Журнал отдаётся по двум обязательным точкам протокола:
GET /.well-known/did.json и GET /federation/log. Тела адресных событий
получает только адресат, подписавший запрос; остальным — конверт без тела.

Протокол — копия эталона federation/ref (daocooptech/dao-cooptech) байт в
байт, lib/fedproto; подпись — через cryptography. Секрет ключа — в файле
<data_dir>/federation/<база>/, не в базе. Копия базы ключа не получает и
подписать ничего не может (data/neutralize.sql).

Соседи, приём чужих журналов и сделки между узлами — шаги 2 и 3.
""",
    'author': 'ДАО КООПТЕХ',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['coop_theme'],
    'external_dependencies': {'python': ['cryptography']},
    'data': [
        'data/coop_fed_cron.xml',
        'views/coop_fed_views.xml',
        'security/ir.access.csv',
    ],
    'post_init_hook': '_post_init',
    'installable': True,
    'application': False,
}
