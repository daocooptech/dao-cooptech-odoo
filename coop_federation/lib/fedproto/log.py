# -*- coding: utf-8 -*-
"""Журнал событий узла: конверт, подпись, хэш-цепочка, вымарывание.

Каждый узел ведёт свой журнал — только дописываемый и связанный хэшами.
Событие ссылается на предыдущее полем `prev`, поэтому вырезать или подменить
запись в середине нельзя, не переписав весь хвост, а хвост подписан.

Порядок внутри журнала — полный: за него отвечает `seq`. Порядка между
журналами разных узлов нет и не нужно: у каждого факта ровно один
авторитетный узел — тот, о ком факт. Двусторонние объекты (сделка, взаимное
обязательство) продвигаются, только когда подписались обе стороны.

## Почему тело события отделено от конверта

Первая версия подписывала конверт вместе с телом. Тогда адресное событие
нельзя было отдать соседу, не показав содержимого: убрал тело — рассыпалась
цепочка, и получатель больше не может проверить, что журнал полон.

Здесь конверт подписывает не тело, а его хэш (`body_hash`). Тело едет рядом
и отцепляется. Кооператив, которому событие не адресовано, получает конверт
без тела, проверяет подпись и непрерывность цепочки — и не видит ни рубля
чужой сделки. Это и есть выборочное раскрытие, без которого федерация не
проходит по 152-ФЗ.

Вложения живут внутри тела: их адреса и хэши — тоже содержимое, а не служебные
поля конверта.
"""
import base64
import datetime
import re

from . import canonical, ed25519

VERSION = 1
ALG = 'Ed25519'
# Алгоритм подписи входит в конверт и под подпись: иначе его можно было бы
# подменить. Ed25519 обязателен к поддержке всеми; ГОСТ заложен опцией,
# потому что российская первичка рано или поздно потребует отечественной
# криптографии, а менять формат конверта ради этого нельзя.
ALGS = ('Ed25519', 'GOST3410-2012-256')
ENVELOPE = ('v', 'alg', 'node', 'kid', 'seq', 'prev', 'ts', 'type', 'subject', 'to', 'body_hash')
FUTURE_TOLERANCE = 300      # секунд: часы у узлов расходятся, но не на час
TS_RE = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
# Порт в имени хоста кодируется как %3A (спецификация did:web): did:web:localhost%3A8070.
DID_RE = re.compile(r'^did:web:[a-z0-9.\-]+(%3A[0-9]{1,5})?(:[A-Za-z0-9.\-_%]+)*$')

OK = 'ok'
SUSPECT = 'suspect'          # ключ отозван как скомпрометированный задним числом


class Invalid(Exception):
    """Событие, цепочка или ключ не проходят проверку."""


class TooOld(Invalid):
    """Запрошено раньше горизонта хранения — догонять надо со снимка.

    Журнал не хранится вечно: через год-полтора его начало подрезают. Узел,
    отсутствовавший дольше, не может дочитать историю с нуля — и это не
    поломка, а нормальный режим. Ему отдают подписанный снимок состояния на
    определённый номер и хвост журнала после него.
    """

    def __init__(self, horizon):
        Invalid.__init__(self, 'журнал подрезан до seq %d, догоняйте со снимка' % horizon)
        self.horizon = horizon


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def unb64(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def envelope(event):
    """Подписываемая часть: конверт без id, sig и тела."""
    return {k: v for k, v in event.items() if k in ENVELOPE}


def make(node, kid, seq, prev, ts, type_, subject, body, to=None):
    event = {
        'v': VERSION,
        'alg': ALG,
        'node': node,
        'kid': kid,
        'seq': seq,
        'prev': prev,
        'ts': ts,
        'type': type_,
        'subject': subject,
        'body_hash': canonical.digest(body),
        'body': body,
    }
    if to is not None:
        event['to'] = list(to)
    return event


def sign(event, secret):
    """Подписать конверт. Тело в подпись не входит — только его хэш."""
    signed = dict(event)
    head = envelope(signed)
    signed['id'] = canonical.digest(head)
    signed['sig'] = b64(ed25519.sign(secret, canonical.encode(head)))
    return signed


def redact(event):
    """Отцепить тело: конверт остаётся проверяемым, содержимое не видно."""
    return {k: v for k, v in event.items() if k != 'body'}


def check(event, keyring, now=None):
    """Проверить одно событие. Возвращает OK или SUSPECT, иначе бросает Invalid.

    `now` — момент проверки в формате ts; по умолчанию текущее время UTC.
    Нужен, чтобы тесты были детерминированными.
    """
    if event.get('v') != VERSION:
        raise Invalid('версия конверта %r, поддерживается %d' % (event.get('v'), VERSION))
    if event.get('alg') not in ALGS:
        raise Invalid('неизвестный алгоритм подписи %r' % event.get('alg'))
    if event.get('alg') != ALG:
        raise Invalid('алгоритм %s этим узлом не поддерживается' % event['alg'])
    for field in ('node', 'kid', 'seq', 'ts', 'type', 'subject', 'body_hash', 'id', 'sig'):
        if field not in event:
            raise Invalid('нет обязательного поля %s' % field)
    if not DID_RE.match(event['node']):
        raise Invalid('идентификатор узла не похож на did:web: %r' % event['node'])
    if not event['kid'].startswith(event['node'] + '#'):
        raise Invalid('ключ %r принадлежит не этому узлу' % event['kid'])
    if not isinstance(event['seq'], int) or event['seq'] < 0:
        raise Invalid('seq должен быть целым неотрицательным')
    if not TS_RE.match(event['ts']):
        raise Invalid('время не в формате 2026-09-01T10:00:00Z: %r' % event['ts'])
    if (event['seq'] == 0) != (event.get('prev') is None):
        raise Invalid('первое событие журнала и только оно имеет prev = null')

    # Время — заявление автора, а не доверенный источник. Порядок задаёт seq,
    # но событие из далёкого будущего принимать нельзя: им можно было бы
    # застолбить срок, который ещё не наступил.
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    limit = (datetime.datetime.strptime(now, '%Y-%m-%dT%H:%M:%SZ')
             + datetime.timedelta(seconds=FUTURE_TOLERANCE)).strftime('%Y-%m-%dT%H:%M:%SZ')
    if event['ts'] > limit:
        raise Invalid('событие датировано будущим: %s против %s' % (event['ts'], now))

    head = envelope(event)
    if canonical.digest(head) != event['id']:
        raise Invalid('id не совпадает с хэшем конверта — событие изменено')

    # Ключ проверяется на момент события, а не на сегодня: подпись трёхлетней
    # давности обязана сходиться и после плановой смены ключа.
    public_key, status = keyring.resolve(event['kid'], event['ts'])
    if not ed25519.verify(public_key, canonical.encode(head), unb64(event['sig'])):
        raise Invalid('подпись не проходит проверку')

    # Тело едет отдельно и может быть отцеплено: проверяем, только если оно есть.
    if 'body' in event and canonical.digest(event['body']) != event['body_hash']:
        raise Invalid('тело не соответствует хэшу в конверте')
    return status


def check_chain(events, keyring, now=None, after=None):
    """Проверить непрерывность и подлинность журнала.

    `after` — снимок, к которому пристыковывается хвост: тогда цепочка
    начинается не с нуля, а с события, следующего за зафиксированным в
    снимке. Без него журнал обязан начинаться с самого первого события.
    """
    previous, statuses = None, []
    for index, event in enumerate(events):
        statuses.append(check(event, keyring, now))
        if previous is None:
            if after is not None:
                if event['seq'] != after['seq'] + 1:
                    raise Invalid('хвост начинается с seq %d, а снимок на %d'
                                  % (event['seq'], after['seq']))
                if event['prev'] != after['event']:
                    raise Invalid('хвост не пристыковывается к снимку')
            elif event['seq'] != 0:
                raise Invalid('журнал начинается с seq %d, а не с нуля' % event['seq'])
        else:
            if event['seq'] != previous['seq'] + 1:
                raise Invalid('разрыв в нумерации на позиции %d: %d после %d'
                              % (index, event['seq'], previous['seq']))
            if event['prev'] != previous['id']:
                raise Invalid('разрыв цепочки на позиции %d: prev не тот' % index)
            if event['node'] != previous['node']:
                raise Invalid('в одном журнале события разных узлов')
        previous = event
    return SUSPECT if SUSPECT in statuses else OK


class KeyRing(object):
    """Ключи узлов с историей.

    Ключ действует с `since`. Плановый отзыв (`revoked`) не отменяет подписи,
    сделанные до него. Компрометация (`compromised`) — отменяет доверие к
    подписям после указанного момента, но события не выбрасываются: они
    помечаются как сомнительные и требуют переподтверждения. Молча удалять
    историю нельзя — это скрыло бы след взлома.
    """

    def __init__(self):
        self.keys = {}

    def add(self, kid, public_key, since='0000-01-01T00:00:00Z',
            revoked=None, compromised=None):
        self.keys[kid] = {'key': public_key, 'since': since,
                          'revoked': revoked, 'compromised': compromised}
        return self

    def resolve(self, kid, ts):
        entry = self.keys.get(kid)
        if entry is None:
            raise Invalid('ключ %s неизвестен' % kid)
        if ts < entry['since']:
            raise Invalid('ключ %s ещё не действовал на %s' % (kid, ts))
        if entry['revoked'] and ts >= entry['revoked']:
            raise Invalid('ключ %s отозван с %s' % (kid, entry['revoked']))
        if entry['compromised'] and ts >= entry['compromised']:
            return entry['key'], SUSPECT
        return entry['key'], OK


class Log(object):
    """Журнал одного узла в памяти — для тестов и примеров."""

    def __init__(self, node, kid, secret):
        self.node = node
        self.kid = kid
        self.secret = secret
        self.public_key = ed25519.public_key(secret)
        self.events = []
        self.horizon = 0        # ниже этого номера события уже подрезаны

    def keyring(self):
        return KeyRing().add(self.kid, self.public_key)

    def append(self, ts, type_, subject, body, to=None):
        last = self.events[-1] if self.events else None
        event = make(
            node=self.node, kid=self.kid,
            seq=0 if last is None else last['seq'] + 1,
            prev=None if last is None else last['id'],
            ts=ts, type_=type_, subject=subject, body=body, to=to,
        )
        signed = sign(event, self.secret)
        self.events.append(signed)
        return signed

    def prune(self, before_seq):
        """Подрезать начало журнала. Хранить историю вечно не обязательно:
        достаточно года с запасом, дальше догоняют снимком."""
        self.events = [e for e in self.events if e['seq'] >= before_seq]
        self.horizon = before_seq
        return self

    def since(self, seq=0, limit=100, reader=None):
        """Выдача для GET /federation/log.

        `reader` — кто спрашивает, уже подтверждённый подписью запроса
        (`reader.verify`). Параметру `for` из адреса верить на слово нельзя —
        иначе любой, назвавшийся адресатом, получит его тела. Адресные события
        отдаются читателю с телом, остальным — вымаранными: цепочка остаётся
        проверяемой у всех.
        """
        if seq < self.horizon:
            raise TooOld(self.horizon)
        out = []
        for event in self.events:
            if event['seq'] < seq:
                continue
            audience = event.get('to')
            if audience is None or reader in audience or reader == self.node:
                out.append(event)
            else:
                out.append(redact(event))
            if len(out) >= limit:
                break
        return out

    def snapshot_at(self, seq, state, ts):
        """Снимок на указанный номер события."""
        anchor = None
        for event in self.events:
            if event['seq'] == seq:
                anchor = event
                break
        if anchor is None:
            raise Invalid('нет события с номером %d, снимать нечего' % seq)
        return snapshot(self.node, self.kid, seq, anchor['id'], state, ts, self.secret)

    def head(self, ts):
        """Подписанный конец журнала.

        Узлы обмениваются головами соседей и складывают их. Если узел
        показывает разным партнёрам разные истории, расхождение всплывает
        при первой же сверке — без общего реестра и без консенсуса.
        """
        last = self.events[-1] if self.events else None
        head = {'node': self.node, 'kid': self.kid, 'ts': ts,
                'seq': -1 if last is None else last['seq'],
                'id': None if last is None else last['id']}
        head['sig'] = b64(ed25519.sign(self.secret, canonical.encode(
            {k: v for k, v in head.items() if k != 'sig'})))
        return head

    def verify(self, keyring=None, now=None):
        return check_chain(self.events, keyring or self.keyring(), now)


def snapshot(node, kid, seq, event_id, state, ts, secret):
    """Подписанный снимок состояния на определённый номер события.

    Снимок — это не сжатый журнал, а результат его применения: остатки,
    сальдо линий, действующие предложения. Тот же приём, что базовая копия
    плюс журнал упреждающей записи в PostgreSQL: с какого-то момента
    выгоднее отдать состояние, чем всю историю.

    В снимок входит идентификатор события, на котором он снят, — иначе
    хвост журнала некуда пристыковать.
    """
    body = {'v': VERSION, 'node': node, 'kid': kid, 'seq': seq,
            'event': event_id, 'ts': ts, 'state_hash': canonical.digest(state)}
    body['sig'] = b64(ed25519.sign(secret, canonical.encode(
        {k: v for k, v in body.items() if k != 'sig'})))
    return body


def check_snapshot(snap, state, keyring):
    """Проверить снимок и то, что состояние ему соответствует.

    Состояние едет отдельно от подписанной шапки — по той же причине, что и
    тело события: снимок может быть большим, а проверить его подлинность
    надо до того, как всё скачано.
    """
    for field in ('v', 'node', 'kid', 'seq', 'event', 'ts', 'state_hash', 'sig'):
        if field not in snap:
            raise Invalid('в снимке нет поля %s' % field)
    if snap['v'] != VERSION:
        raise Invalid('версия снимка %r' % snap['v'])
    if not snap['kid'].startswith(snap['node'] + '#'):
        raise Invalid('снимок подписан ключом чужого узла')
    body = {k: v for k, v in snap.items() if k != 'sig'}
    public_key, status = keyring.resolve(snap['kid'], snap['ts'])
    if not ed25519.verify(public_key, canonical.encode(body), unb64(snap['sig'])):
        raise Invalid('подпись снимка не проходит проверку')
    if state is not None and canonical.digest(state) != snap['state_hash']:
        raise Invalid('состояние не соответствует хэшу в снимке')
    return status


def check_head(head, keyring):
    """Проверить подписанную голову чужого журнала."""
    body = {k: v for k, v in head.items() if k != 'sig'}
    public_key, status = keyring.resolve(head['kid'], head['ts'])
    if not ed25519.verify(public_key, canonical.encode(body), unb64(head['sig'])):
        raise Invalid('подпись головы журнала не проходит проверку')
    return status
