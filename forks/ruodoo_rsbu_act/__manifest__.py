# -*- coding: utf-8 -*-
{
    'name': 'РСБУ — Акт сверки взаиморасчётов',
    'version': '19.0.2026.10.01',
    'summary': 'Акт сверки по РСБУ-слою: выгрузка в DOCX и в XML (приказ ФНС 405)',
    'description': """
РСБУ — Акт сверки взаиморасчётов

Формирование акта сверки взаимных расчётов с контрагентом из данных
РСБУ-слоя (журнал хозяйственных операций rsbu.move): сальдо на начало и
конец периода, обороты по дебету/кредиту в разрезе контрагента по счетам
расчётов (60/62/76), с детализацией операций.

Возможности:

* Сбор сальдо и оборотов по контрагенту за период из rsbu.move.line
  (счета расчётов — активно-пассивные, субконто «Контрагент»/«Договор»).
* Печатная форма акта сверки в DOCX (движок docx_report).
* Электронный акт сверки в XML — формат обмена ФНС (приказ ФНС России
  от 13.05.2022 № ЕД-7-26/405@, КНД 1110332, версия 5.01, ON_AKTSVEROTP),
  с блокирующей проверкой по XSD.

Реквизиты сторон (ИНН/КПП/ОГРН, подписант) — из res.company /
res.partner (rsbu_reporting_base, l10n_ru).
    """,
    'author': 'MK.Lab, RuOdoo',
    'website': 'https://ruodoo.ru',
    'category': 'Accounting/Localizations',
    'depends': [
        'rsbu_journal',
        'rsbu_reporting_base',
        'docx_report',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/docx_templates.xml',
        'views/ruodoo_rsbu_act_views.xml',
    ],
    'external_dependencies': {
        'python': ['lxml'],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'maintainers': ['mklab', 'ruodoo'],
}
