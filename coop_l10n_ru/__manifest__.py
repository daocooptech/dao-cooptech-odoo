{
    'name': 'ДАО КООПТЕХ - связка с российской локализацией',
    'summary': 'ОГРН хранится в одном поле организации, формы цепочки l10n_ru читают его же',
    'description': """
Связка платформы с цепочкой российских модулей (l10n_ru_doc, l10n_ru_contract).

Решение 446 (НВ11): единственное хранимое поле ОГРН - `res.partner.coop_ogrn`
из coop_orgs. Поля цепочки, где стоял ОГРН (`res.partner.ogrn`,
`res.partner.company_registry`, `res.company.company_registry`), здесь
переопределены как несохраняемые и читают и пишут то же поле. Печатные формы,
шапки договоров и коннектор DaData продолжают работать с прежними именами.

Ставится сам, когда стоят все три модуля.
""",
    'author': 'ДАО КООПТЕХ',
    'category': 'Cooperative',
    'version': '20.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['coop_orgs', 'l10n_ru_contract', 'l10n_ru_doc'],
    'auto_install': True,
    'post_init_hook': 'post_init_hook',
    'installable': True,
}
