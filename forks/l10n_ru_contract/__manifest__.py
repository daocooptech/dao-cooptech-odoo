# -*- coding: utf-8 -*-
{
    'name': 'Российская локализация - Договоры',
    'summary': """
       Создание договоров, их видов и печать
    """,

    'description': """
       Создание договоров с клиентами и поставщиками. Возможность разделения на виды договоров, отслеживание статуса договора и его печатью
       Создание вида договора клиента(поставщика):
       1. Меню Продажи (Покупки) - Договоры - Виды договора - кнопка "Создать";
       2. На форме указываем: 
            2.1. Журнал и счета дебетовой и кредиторской задолженности;
            2.2. Присваиваем новое название.
       
       Создание договора клиента (поставщика):
       1. Меню Продажи (Покупки) - Договоры - кнопка "Создать";
       2. На форме указываем основные и дополнительные условия договора: 
           2.1. Контрагент - клиент (поставщик);
           2.2. Тип контрагента;
           2.3. Компанию, от лица которой будет подписан договор;
           2.4. Вид договора.

       Для печати:
       1. Открываем созданную запись договора - Действие - "Договор".         
    """,

    'version': '20.0.1.0.0',
    'sequence': 0,
    'author': 'MK.Lab',
    'website': 'https://www.inf-centre.ru/',
    'depends': [
        'base',
        'mail',
        'l10n_ru_base',
        'report_weasyprint',
    ],
    "external_dependencies": {
        "python": ["weasyprint", "pymorphy3", "python-docx", "docxtpl"],
    },
    'data': [
        'data/data.xml',
        'report/report_contract_simple.xml',
        'views/contract_customer_view.xml',
        "views/contract_header_templates.xml",
        'views/res_company_views.xml',
        'views/res_partner_views.xml',
        'views/contract_profile_views.xml',
        'report/report_contract.xml',
        'security/ir.access.csv',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'auto_install': False,
}
