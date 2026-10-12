# -*- coding: utf-8 -*-
from odoo import models


class CoopDocument(models.Model):
    """Панель «Фильтр» раздела документов — как во всех разделах.

    «Вид» и «Состояние» стояли колонкой слева рядом с деревом папок; в
    эталоне (`DocumentsPage`, решение 459) отбор — в панели «Фильтр»
    справа. Папки остались деревом слева: владелец 23.09.2026 просил их
    «как в виндовс», и 13.10.2026 выбрал так и оставить — в панели дерева
    нет, только список.
    """
    _inherit = 'coop.document'

    def _coop_catalog_filters(self, domain):
        def options(field):
            return [{'value': code, 'label': label}
                    for code, label in self._fields[field].selection]

        return [{
            'code': 'kind', 'label': 'Вид',
            'hint': 'Договор, акт, счёт и другие виды документов.',
            'widget': 'select', 'field': 'kind', 'operator': '=',
            'placeholder': 'Любой', 'options': options('kind'),
        }, {
            'code': 'state', 'label': 'Состояние',
            'hint': 'Черновик, на подписи, подписан или отменён.',
            'widget': 'select', 'field': 'state', 'operator': '=',
            'placeholder': 'Любое', 'options': options('state'),
        }]
