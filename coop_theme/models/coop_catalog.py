# -*- coding: utf-8 -*-
import ast
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class CoopCatalog(models.AbstractModel):
    """Описание панели фильтров каталога и счётчики к ней.

    Панель собирается на сервере, а не задаётся в представлении: набор
    полей у каждого каталога свой, а у ресурсов он вдобавок зависит от
    выбранной рубрики. Штатная панель Odoo этого не умеет — она берёт
    фиксированный список полей из разметки и работает только со
    ссылками и списками значений, без диапазонов и свободного ввода.

    Сам набор фильтров каждый каталог объявляет у себя: тема не должна
    знать, что у ресурса есть способ получения, а у вакансии — занятость.
    """

    _name = 'coop.catalog'
    _description = 'Панель фильтров каталога'

    @api.model
    def catalog_filters(self, res_model, domain=None):
        """Поля панели вместе со счётчиками по текущей выборке."""
        model = self.env[res_model]
        describe = getattr(model, '_coop_catalog_filters', None)
        if not describe:
            return []
        blocks = describe(domain or [])
        counted = [b for b in blocks
                   if b.get('widget') in ('select', 'chips') and b.get('field')]

        # Характеристики считаются все разом: у каждой свой ключ в одной
        # и той же колонке значений, и разбирать их по отдельным
        # группировкам значит платить по два запроса за каждую. Каталог
        # знает, как это сделать одним, — спрашиваем его.
        attr_blocks = [b for b in counted if b['field'].startswith('attrs.')]
        attr_ids = {id(b) for b in attr_blocks}
        if attr_blocks and hasattr(model, '_coop_attr_counts'):
            codes = [b['field'].split('.', 1)[1] for b in attr_blocks]
            try:
                attr_counts = model._coop_attr_counts(domain or [], codes)
            except Exception:
                _logger.exception(
                    'Не удалось посчитать значения характеристик каталога %s',
                    res_model)
                attr_counts = {}
            for block in attr_blocks:
                values = attr_counts.get(block['field'].split('.', 1)[1], {})
                for option in block.get('options', []):
                    option['count'] = values.get(option['value'], 0)

        for block in counted:
            if id(block) not in attr_ids:
                self._fill_counts(model, block, domain or [])
        return blocks

    def _fill_counts(self, model, block, domain):
        """Счётчики значений.

        Считаются по всем прочим применённым условиям, но без учёта
        самого этого поля: иначе выбор «Предложение» обнулит счётчик у
        «Спроса», и выбрать второе станет нечем.
        """
        field = block['field']
        others = [leaf for leaf in domain
                  if not (isinstance(leaf, (list, tuple)) and leaf and leaf[0] == field)]
        try:
            groups = model._read_group(others, [field], ['__count'])
        except Exception:
            # Молча ноль во всех счётчиках — худший исход: панель выглядит
            # рабочей и говорит неправду. Показать её всё-таки надо, но
            # причина обязана попасть в журнал, иначе искать её негде.
            _logger.exception(
                'Не удалось посчитать значения поля «%s» каталога %s',
                field, model._name)
            return
        counts = {}
        for value, count in groups:
            # Для ссылок группировка отдаёт запись, для списков значений —
            # строку. В Odoo 19 это кортежи, а не словари.
            counts[value.id if hasattr(value, 'id') else value] = count
        for option in block.get('options', []):
            option['count'] = counts.get(option['value'], 0)

    # ── Сохранённые поиски ─────────────────────────────────────────────
    #
    # Своей модели не заводим: у Odoo для этого есть `ir.filters`, и
    # сохранённый поиск виден там же, где остальные избранные фильтры.

    @api.model
    def coop_save_search(self, res_model, name, domain):
        return self.env['ir.filters'].create({
            'name': name or 'Поиск',
            'model_id': res_model,
            'domain': repr(domain or []),
            'user_ids': [(6, 0, [self.env.uid])],
            'context': "{}",
        }).id

    @api.model
    def coop_saved_searches(self, res_model):
        """Сохранённые поиски участника, с уже разобранным условием.

        Условие разбирается здесь, а не в браузере. Хранится оно в виде
        записи Python, и на той стороне его чинили заменой апострофов на
        кавычки — на первом же городе с апострофом в названии или на
        сохранённом «истина/ложь» такой разбор ломается и молча отдаёт
        пустой фильтр.
        """
        records = self.env['ir.filters'].search([
            ('model_id', '=', res_model),
            ('user_ids', 'in', [self.env.uid]),
        ], order='name')
        result = []
        for record in records:
            try:
                domain = ast.literal_eval(record.domain or '[]')
            except (ValueError, SyntaxError):
                _logger.warning(
                    'Сохранённый поиск %s: условие не читается: %s',
                    record.id, record.domain)
                continue
            result.append({'id': record.id, 'name': record.name,
                           'domain': domain})
        return result

    @api.model
    def coop_drop_search(self, filter_id):
        record = self.env['ir.filters'].browse(filter_id).exists()
        if record and self.env.uid in record.user_ids.ids:
            record.unlink()
        return True
