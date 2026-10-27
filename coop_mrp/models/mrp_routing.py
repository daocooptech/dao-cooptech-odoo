# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpRoutingWorkcenter(models.Model):
    _inherit = 'mrp.routing.workcenter'

    # В движке у операции нет ни описания, ни листа работ, а эталон
    # (`ProcessSteps`) у каждой операции даёт ссылку «Инструкция».
    coop_instruction = fields.Html(
        string='Инструкция',
        help='Как выполнять операцию. На карточке ресурса открывается по '
             'ссылке «Инструкция», если организация показывает техпроцесс.')
