# -*- coding: utf-8 -*-
"""«Моя панель» платформы (решение 420, слой 1).

Штатная панель `board` хранит у каждого участника свою разметку
(`ir.ui.view.custom`), а тем, кто её не настраивал, показывает общий вид
`board.board_my_dash_view`. Этот общий вид и становится панелью по
умолчанию: деньги и сделки слева, вклады, биржа и обучение справа, колонки
поровну — в узкой правой графики сжимались до нечитаемого. Настроил
панель под себя — дальше она его, по умолчанию её не перетирает.
"""
from odoo import api, models

# (действие, подпись, вид) — по колонкам.
DEFAULT_COLUMNS = [
    [
        ('coop_analytics.action_coop_an_money', 'Деньги по месяцам', 'graph'),
        ('coop_analytics.action_coop_an_deals', 'Сделки по месяцам', 'graph'),
    ],
    [
        ('coop_analytics.action_coop_an_contributions', 'Мои вклады в проекты', 'graph'),
        ('coop_analytics.action_coop_an_dex', 'Обмены на бирже', 'graph'),
        ('coop_analytics.action_coop_an_courses', 'Мои курсы по темам', 'graph'),
    ],
]


class Board(models.AbstractModel):
    _inherit = 'board.board'

    @api.model
    def _coop_default_board(self):
        view = self.env.ref('board.board_my_dash_view', raise_if_not_found=False)
        if not view:
            return False
        columns = []
        for column in DEFAULT_COLUMNS:
            items = []
            for xmlid, title, mode in column:
                act = self.env.ref(xmlid, raise_if_not_found=False)
                if act:
                    items.append('<action name="%d" string="%s" view_mode="%s" '
                                 'context="{}" domain="[]"/>' % (act.id, title, mode))
            columns.append('<column>%s</column>' % ''.join(items))
        view.sudo().arch = ('<form string="Моя панель"><board style="1-1">%s</board></form>'
                            % ''.join(columns))
        return True
