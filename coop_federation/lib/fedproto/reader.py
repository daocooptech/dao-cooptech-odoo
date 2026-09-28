# -*- coding: utf-8 -*-
"""Кто читает журнал: подпись запроса.

`GET /federation/log?for=<did>` отдаёт адресные события с телом тому, кому
они адресованы. Первая версия верила параметру `for` на слово — и любой,
назвавшийся узлом B, получал тела сделок, адресованных B. Для 152-ФЗ это
прямая утечка.

Теперь `for` учитывается, только если запрос подписан ключом этого узла.
Подписываются метод, путь, параметры запроса, время и сам читатель —
канонической сериализацией, как и события. Неподписанный или неверно
подписанный запрос не получает отказа: ему отдаётся тот же журнал, что
постороннему, — вымаранный. Так узел, не умеющий подписывать запросы, всё
равно полноценно проверяет чужие журналы.

Заголовки: `X-Coop-Reader` (did), `X-Coop-Kid`, `X-Coop-Ts`, `X-Coop-Sig`.
Допуск по времени ±5 минут. Повтор подписанного запроса в этом окне даёт
то же, что и оригинал, — чтение идемпотентно, а канал защищает TLS.
"""
import datetime

from . import canonical, ed25519, log

WINDOW = 300    # секунд в обе стороны
HEADERS = ('X-Coop-Reader', 'X-Coop-Kid', 'X-Coop-Ts', 'X-Coop-Sig')


def payload(method, path, query, reader, ts):
    """Что подписывается. query — словарь строк, как после разбора адреса."""
    return canonical.encode({'method': method.upper(), 'path': path,
                             'query': {k: str(v) for k, v in query.items()},
                             'reader': reader, 'ts': ts})


def sign(reader, kid, secret, method, path, query, ts):
    """Заголовки подписанного запроса."""
    signature = ed25519.sign(secret, payload(method, path, query, reader, ts))
    return {'X-Coop-Reader': reader, 'X-Coop-Kid': kid,
            'X-Coop-Ts': ts, 'X-Coop-Sig': log.b64(signature)}


def verify(headers, method, path, query, keyring, now):
    """DID читателя, если запрос подписан им и `for` совпадает, иначе None.

    Ничего не бросает: неподтверждённый читатель — просто посторонний.
    keyring должен содержать ключи читателя (из его DID-документа).
    """
    try:
        reader, kid, ts, sig = (headers[name] for name in HEADERS)
    except KeyError:
        return None
    if query.get('for') != reader or not kid.startswith(reader + '#'):
        return None
    if not log.TS_RE.match(ts or '') or not log.TS_RE.match(now):
        return None
    fmt = '%Y-%m-%dT%H:%M:%SZ'
    drift = abs((datetime.datetime.strptime(ts, fmt)
                 - datetime.datetime.strptime(now, fmt)).total_seconds())
    if drift > WINDOW:
        return None
    try:
        public_key, status = keyring.resolve(kid, ts)
        raw = log.unb64(sig)
    except (log.Invalid, ValueError):
        return None
    if status != log.OK:
        return None                 # скомпрометированным ключом тела не получить
    if not ed25519.verify(public_key, payload(method, path, query, reader, ts), raw):
        return None
    return reader


def serve(journal, headers, path, query, keyring, now):
    """Ответ на GET /federation/log: порция журнала с учётом читателя."""
    reader = verify(headers, 'GET', path, query, keyring, now) if query.get('for') else None
    since = int(query.get('since', 0))
    limit = max(1, min(int(query.get('limit', 100)), 1000))
    return journal.since(since, limit=limit, reader=reader)
