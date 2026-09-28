# -*- coding: utf-8 -*-
"""Состояние сделки выводится из двух журналов, а не хранится в одном.

Главная мысль всей схемы. У сделки две равные стороны, и ни одна не вправе
объявить состояние за обоих. Поэтому состояние нигде не записано — оно
вычисляется из подписанных событий обеих сторон:

    предложена      -> есть deal.proposed от инициатора
    отозвана        -> инициатор отозвал предложение до принятия
    отклонена       -> есть deal.rejected от второй стороны
    принята         -> есть deal.accepted от второй стороны
    исполняется     -> после принятия любая сторона заявила deal.started
    ждёт вторую     -> акт подписан одной стороной
    исполнена       -> акт подписан обеими
    спор            -> любая из сторон заявила deal.disputed, и спор не урегулирован
    отменена        -> спор урегулирован обеими сторонами с исходом «отменить»

Отсюда следует, что общий консенсус сети не нужен: договариваются двое, и
достаточно двух подписей. Ни блокчейн, ни распределённая база с разрешением
конфликтов для этого не требуются.

## Кто что вправе

Инициатор — сторона, чей идентификатор стоит в начале предмета сделки
(`<did инициатора>/deal/<id>`): предмет выпускает тот, кто предлагает. Только
его `deal.proposed` и `deal.withdrawn` засчитываются. Принять или отклонить
может только вторая сторона — иначе инициатор сам «принял» бы свою оферту.
Каждое ответное событие ссылается на предложение полем `refs` в теле: ответ
без ссылки или на чужое предложение не засчитывается.

Акт засчитывается только после принятия: два `deal.act.signed` без оферты и
акцепта — не исполненная сделка, а два бессвязных заявления.

## Порядка между журналами нет

Поэтому взаимоисключающие заявления нельзя рассудить «кто раньше». Если
вторая сторона и приняла, и отклонила, или инициатор отозвал оферту, а вторая
сторона её уже приняла, — это спор, а не гонка, которую выигрывает кто-то
один. Из спора выходят только вместе: `deal.dispute.settled` с одинаковым
решением от обеих сторон.

События третьих узлов игнорируются: сторона сделки — только `parties`.
"""
import decimal

from . import canonical

PROPOSED = 'proposed'
WITHDRAWN = 'withdrawn'
ACCEPTED = 'accepted'
REJECTED = 'rejected'
ACTIVE = 'active'
AWAITING = 'awaiting_counterparty'
DONE = 'done'
DISPUTED = 'disputed'
CANCELLED = 'cancelled'

# Для интерфейса: то, что видит кооператор, без слова «узел».
RUSSIAN = {
    PROPOSED: 'Предложена',
    WITHDRAWN: 'Отозвана',
    ACCEPTED: 'Принята',
    REJECTED: 'Отклонена',
    ACTIVE: 'Исполняется',
    AWAITING: 'Ожидает подписи второй стороны',
    DONE: 'Исполнена',
    DISPUTED: 'Спор',
    CANCELLED: 'Отменена',
}

# Чем может закончиться урегулированный спор.
OUTCOMES = {'done': DONE, 'cancelled': CANCELLED}


def initiator(deal_subject, parties):
    """Сторона, выпустившая предмет сделки, или None, если предмет чужой."""
    for node in parties:
        if deal_subject.startswith(node + '/'):
            return node
    return None


def _body(event):
    """Тело или пустой словарь, если событие пришло вымаранным."""
    return event.get('body') or {}


def _analyse(deal_subject, parties, events):
    if len(parties) != 2 or parties[0] == parties[1]:
        raise ValueError('у сделки ровно две разные стороны')
    first = initiator(deal_subject, parties)
    if first is None:
        return None
    second = parties[1] if parties[0] == first else parties[0]

    mine = [e for e in events
            if e.get('subject') == deal_subject and e.get('node') in parties]

    proposals = {e['id'] for e in mine
                 if e.get('type') == 'deal.proposed' and e['node'] == first}
    if not proposals:
        return None

    def answering(type_, author):
        """События типа от автора, ссылающиеся на действующее предложение."""
        return [e for e in mine
                if e.get('type') == type_ and e['node'] == author
                and _body(e).get('refs') in proposals]

    def authors(type_):
        return {e['node'] for node in parties for e in answering(type_, node)}

    accepted = bool(answering('deal.accepted', second))
    rejected = bool(answering('deal.rejected', second))
    withdrawn = bool(answering('deal.withdrawn', first))

    facts = {'initiator': first, 'counterparty': second, 'signed': set(),
             'payments': [e for node in parties
                          for e in answering('deal.payment.received', node)]}
    if not accepted:
        if rejected:
            facts['state'] = REJECTED
        elif withdrawn:
            facts['state'] = WITHDRAWN
        else:
            facts['state'] = PROPOSED
        return facts

    # Взаимоисключающие заявления — спор, а не гонка.
    conflict = rejected or withdrawn

    disputes = {e['id'] for node in parties for e in answering('deal.disputed', node)}

    # Урегулирование действует, только если обе стороны подписали одно и то же
    # решение: какие заявления о споре оно закрывает и чем заканчивается.
    settled_by = {}
    for node in parties:
        for e in answering('deal.dispute.settled', node):
            body = _body(e)
            if body.get('outcome') not in OUTCOMES:
                continue
            key = canonical.digest({'settles': sorted(body.get('settles') or []),
                                    'outcome': body['outcome']})
            settled_by.setdefault(key, {'nodes': set(), 'body': body})['nodes'].add(node)
    outcomes = {OUTCOMES[item['body']['outcome']] for item in settled_by.values()
                if item['nodes'] == set(parties)
                and disputes <= set(item['body'].get('settles') or [])}

    if disputes or conflict:
        facts['state'] = outcomes.pop() if len(outcomes) == 1 else DISPUTED
        return facts

    signed = authors('deal.act.signed')
    facts['signed'] = signed
    if len(signed) == 2:
        facts['state'] = DONE
    elif len(signed) == 1:
        facts['state'] = AWAITING
    elif authors('deal.started'):
        facts['state'] = ACTIVE
    else:
        facts['state'] = ACCEPTED
    return facts


def state(deal_subject, parties, events):
    """Состояние сделки по событиям обеих сторон.

    deal_subject — идентификатор сделки, parties — два идентификатора узлов
    (did:web), events — события из обоих журналов в любом порядке.
    """
    facts = _analyse(deal_subject, parties, events)
    return None if facts is None else facts['state']


def missing_signature(deal_subject, parties, events):
    """Кого именно ждём. Нужно интерфейсу: «ждём подписи кооператива N»."""
    facts = _analyse(deal_subject, parties, events)
    if facts is None or facts['state'] != AWAITING:
        return None
    return next(node for node in parties if node not in facts['signed'])


def paid(deal_subject, parties, events):
    """Сколько получено по сделке, по валютам: {'RUB': '1500.00'}.

    Авторитетен получатель: `deal.payment.received` — факт о нём самом, и
    публикует его он. Заявление плательщика «я оплатил» денег не доказывает.
    Суммы складываются десятичными числами, никогда не двоичной дробью.
    """
    facts = _analyse(deal_subject, parties, events)
    if facts is None or facts['state'] in (PROPOSED, WITHDRAWN, REJECTED):
        return {}
    totals = {}
    seen = set()
    for e in facts['payments']:
        if e['id'] in seen:
            continue
        amount = _body(e).get('amount') or {}
        if not isinstance(amount.get('amount'), str) or not amount.get('currency'):
            continue
        seen.add(e['id'])
        currency = amount['currency']
        totals[currency] = totals.get(currency, decimal.Decimal(0)) + decimal.Decimal(amount['amount'])
    return {currency: str(total) for currency, total in totals.items()}
