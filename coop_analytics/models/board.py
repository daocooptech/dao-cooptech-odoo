# -*- coding: utf-8 -*-
"""«Моя панель» платформы (решение 420, слой 1).

Штатная панель `board` хранит у каждого участника свою разметку
(`ir.ui.view.custom`), а тем, кто её не настраивал, показывает общий вид
`board.board_my_dash_view`. Этот общий вид и становится панелью по
умолчанию: одна колонка, по графику в строке (владелец 27.11.2026: «у
каждого графика прокрутка, а может их сделать по 1 графику в строку?» —
в двух колонках графики не помещались и прокручивались). Настроил
панель под себя — дальше она его, по умолчанию её не перетирает.
"""
from xml.sax.saxutils import escape

from odoo import api, models

# (действие, подпись, вид) — по колонкам; колонка одна.
DEFAULT_COLUMNS = [
    [
        ('coop_analytics.action_coop_an_account', 'Мой аккаунт', 'kanban'),
        ('coop_analytics.action_coop_an_money', 'Деньги по месяцам', 'graph'),
        ('coop_analytics.action_coop_an_deals', 'Сделки по месяцам', 'graph'),
        ('coop_analytics.action_coop_an_activity', 'Моя активность по месяцам', 'graph'),
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
                    # Отбор действия — в виджет: виджет панели подставляет
                    # свой отбор вместо отбора действия.
                    domain = (act.domain or '[]').replace('"', "'")
                    items.append('<action name="%d" string="%s" view_mode="%s" '
                                 'context="{}" domain="%s"/>' % (act.id, title, mode,
                                                               escape(domain)))
            columns.append('<column>%s</column>' % ''.join(items))
        view.sudo().arch = ('<form string="Моя панель"><board style="1">%s</board></form>'
                            % ''.join(columns))
        return True
