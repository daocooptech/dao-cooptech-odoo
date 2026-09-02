# -*- coding: utf-8 -*-
from odoo import api, models


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
        for block in blocks:
            if block.get('widget') in ('select', 'chips') and block.get('field'):
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
        records = self.env['ir.filters'].search([
            ('model_id', '=', res_model),
            ('user_ids', 'in', [self.env.uid]),
        ], order='name')
        return [{'id': r.id, 'name': r.name, 'domain': r.domain}
                for r in records]

    @api.model
    def coop_drop_search(self, filter_id):
        record = self.env['ir.filters'].browse(filter_id)
        if self.env.uid in record.user_ids.ids:
            record.unlink()
        return True
