================
DaData Connector
================

.. |badge1| image:: https://img.shields.io/badge/maturity-Production-green.png
    :target: https://odoo-community.org/page/development-status

|badge1|

Модуль интеграции с сервисом `DaData <https://dadata.ru>`_ для автоматического
заполнения реквизитов контрагентов по ИНН или ОГРН.

**Возможности:**

- Поиск юридических лиц и ИП по ИНН через API DaData
- Автоматическое заполнение реквизитов партнёра: название, адрес, КПП, ОКПО, ОКВЭД, ОГРН, организационно-правовая форма
- Создание контактного лица (руководителя) при наличии данных об управлении
- Виджет поиска ``dadata_search`` на полях ``vat`` и ``ogrn`` в форме партнёра
- Настройка токена DaData через Настройки → Общие настройки → Интеграции

**Таблица содержания**

.. contents::
   :local:

Использование
=============

1. Перейдите в **Настройки → Общие настройки → Интеграции** и укажите токен DaData.
2. Откройте форму контрагента.
3. Введите ИНН в поле **Tax ID** (или ОГРН в поле **ОГРН**).
4. Нажмите кнопку с лупой рядом с полем.
5. В открывшемся диалоге проверьте найденные данные и нажмите **Да** для применения.

Конфигурация
============

Токен DaData задаётся через системный параметр ``dadata_connector.dadata_token``
или через интерфейс настроек.

Получить токен можно в личном кабинете `dadata.ru <https://dadata.ru>`_.

Известные ограничения
=====================

- Поиск работает только для российских юридических лиц и ИП.
- Требуется установленная Python-библиотека ``dadata==21.10.1``.
- Модуль зависит от ``l10n_ru_doc`` для отображения российских реквизитов.

Тесты
=====

Запуск::

    python odoo-bin -d <db> --test-tags dadata_connector

**common.py** — базовый класс ``DadataConnectorCommon`` и фикстуры:

- ``DADATA_LEGAL_RESPONSE`` — эталонный ответ API для юридического лица (ПАО)
- ``DADATA_INDIVIDUAL_RESPONSE`` — эталонный ответ API для индивидуального предпринимателя
- ``DadataConnectorCommon.setUpClass`` — создаёт тестового партнёра и прописывает тестовый токен в системные параметры

**test_res_partner.py** — тесты модели ``res.partner``:

- ``test_get_dadata_token_returns_token`` — токен возвращается, если системный параметр задан
- ``test_get_dadata_token_raises_when_missing`` — ``ValidationError`` при отсутствии токена
- ``test_parse_legal_entity_basic_fields`` — парсинг ИНН, ОГРН, КПП, ОКПО, ОКВЭД, названия, города, индекса и улицы для юрлица
- ``test_parse_legal_entity_company_form`` — код ОПФ ``12300`` маппится в ``plc``
- ``test_parse_legal_entity_wizard_data`` — данные для wizard: статус, тип организации, название, адрес
- ``test_parse_legal_entity_management`` — извлечение имени и должности руководителя
- ``test_parse_legal_entity_fts_registration`` — серия и номер свидетельства ФНС склеиваются через пробел
- ``test_parse_legal_entity_country_and_state`` — страна резолвится по ISO-коду из ``res.country``
- ``test_parse_individual_name`` — ФИО ИП собирается из частей ``fio``
- ``test_parse_individual_no_kpp`` — КПП не попадает в результат для ИП
- ``test_parse_individual_no_management`` — ключ ``management`` отсутствует, если данных нет
- ``test_parse_individual_no_fts_registration`` — ``sp_register_number`` отсутствует при ``fts_registration: null``
- ``test_get_legal_entity_data_returns_action`` — при ``widget=True`` возвращается ``ir.actions.act_window`` с wizard (DaData замокан)
- ``test_get_legal_entity_data_returns_dict_when_no_widget`` — при ``widget=False`` возвращается словарь с реквизитами
- ``test_get_legal_entity_data_raises_when_empty`` — ``ValidationError`` при пустом ответе DaData
- ``test_get_legal_entity_data_raises_on_http_error`` — ``ValidationError`` при ``HTTPStatusError`` от DaData
- ``test_get_view_sets_dadata_search_widget_on_vat`` — ``_get_view`` проставляет ``widget="dadata_search"`` на поле ``vat``

**test_wizard.py** — тесты ``res.partner.auto_data.wizard``:

- ``test_wizard_creation`` — wizard создаётся с корректными значениями полей
- ``test_button_yes_returns_close_action`` — ``button_yes`` возвращает ``act_window_close`` с флагом ``update: True``
- ``test_wizard_status_selection_values`` — все пять значений статуса принимаются без ошибок
- ``test_wizard_organization_type_individual`` — тип ``individual`` сохраняется корректно

Авторы
======

* MK.lab

Разработчики
============

* MK.lab

Changelog
=========

19.0.2026.04.10
~~~~~~~~~~~~~~~

* Портирование на Odoo 19
* Замена ``_lt`` на ``_t`` (убран в Odoo 18+)
* Виджет переименован в ``dadata_search`` во избежание конфликтов
* Переопределение ``_get_view`` для перекрытия ``partner_autocomplete``
* Удалено поле ``psrn_sp`` из логики парсинга
