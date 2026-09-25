# -*- coding: utf-8 -*-
"""Справка для 3-НДФЛ по подарку токенами (решение 410, п. 1).

Подарок токенами от человека, который получателю не родственник, —
доход: 13% НДФЛ со стоимости на день зачисления, декларацию подаёт сам
получатель. Платформа налоговым агентом не становится и стоимость в
рублях не считает (решение 410, п. 2: рублёвой оценки не показываем):
справка собирает то, что для декларации нужно знать о самом переводе, —
кто, когда, в какой сети, сколько и каким хешем, — и говорит, как
посчитать стоимость.
"""
from markupsafe import Markup, escape

from odoo import fields, http
from odoo.http import request


class CoopWallController(http.Controller):

    @http.route('/coop/wall/thanks/<int:thanks_id>/ndfl', type='http', auth='user')
    def ndfl(self, thanks_id, **kw):
        thanks = request.env['coop.wall.thanks'].sudo().browse(thanks_id).exists()
        if not thanks or thanks.recipient_id != request.env.user.partner_id \
                or thanks.channel != 'token':
            raise request.not_found()
        when = thanks.credited_on or thanks.date
        local = fields.Datetime.context_timestamp(thanks, when) if when else None
        rows = [
            ('Получатель', thanks.recipient_id.name),
            ('Даритель', thanks.sender_id.name),
            ('Сеть', thanks.network_id.name or '—'),
            ('Токен', thanks.token or thanks.currency or '—'),
            ('Количество', ('%.8f' % thanks.amount).rstrip('0').rstrip('.').replace('.', ',')),
            ('Дата и время зачисления', local.strftime('%d.%m.%Y %H:%M (%Z)') if local else '—'),
            ('Хеш транзакции', thanks.tx_hash or 'не указан — впишите из обозревателя сети'),
            ('Запись, за которую подарок', (thanks.post_id.record_name or '') + ' · ' +
             (thanks.post_id.date.strftime('%d.%m.%Y') if thanks.post_id.date else '')),
        ]
        table = Markup('').join(
            Markup('<tr><th>%s</th><td>%s</td></tr>') % (k, v) for k, v in rows)
        html = Markup('''<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<title>Справка к 3-НДФЛ — подарок токенами</title><style>
body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:#1f2328;max-width:760px;margin:24px auto;padding:0 16px}
h1{font-size:20px;margin:0 0 4px}.muted{color:#6c757d}
table{border-collapse:collapse;width:100%%;margin:16px 0}th,td{border:1px solid #d0d0cc;padding:6px 10px;text-align:left;vertical-align:top}
th{width:38%%;background:#f6f6f3;font-weight:600}code{overflow-wrap:anywhere}
ol li{margin:4px 0}.btn{padding:8px 14px;border:0;border-radius:8px;background:#146b64;color:#fff;cursor:pointer}
@media print{.noprint{display:none}}
</style></head><body>
<div class="muted">ДАО КООПТЕХ</div>
<h1>Справка для декларации 3-НДФЛ: подарок токенами</h1>
<p class="muted">Составлена %(today)s по данным платформы. Платформа не передавала ни токенов, ни денег —
перевод прошёл напрямую между кошельками.</p>
<table>%(table)s</table>
<h2 style="font-size:16px">Как посчитать доход</h2>
<ol>
<li>Возьмите котировку токена на дату и время зачисления на бирже или в агрегаторе котировок
и сохраните её снимок.</li>
<li>Если котировка в иностранной валюте — пересчитайте в рубли по официальному курсу Банка
России на дату зачисления.</li>
<li>Стоимость подарка = количество × котировка (× курс ЦБ). С неё — 13%% НДФЛ, если даритель вам
не родственник (п. 18.1 ст. 217, ст. 228 НК).</li>
<li>Декларацию 3-НДФЛ подайте до 30 апреля следующего года, налог уплатите до 15 июля.
За неподанную декларацию штраф — от 1 000 ₽.</li>
</ol>
<p class="noprint"><button class="btn" onclick="window.print()">Распечатать или сохранить в PDF</button></p>
</body></html>''') % {'today': fields.Date.context_today(thanks).strftime('%d.%m.%Y'),
                      'table': table}
        return request.make_response(html)
