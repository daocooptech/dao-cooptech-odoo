# -*- coding: utf-8 -*-
"""DID-документ узла: построение, разбор и адрес по did:web.

Документ — единственный источник ключей узла. Событие `node.key.rotated`
лишь уведомляет соседей; верить надо документу. Формат — W3C DID Core с
ключами типа Ed25519VerificationKey2020: открытый ключ в поле
`publicKeyMultibase` — это `z` и base58btc от префикса мультикодека
`0xed 0x01` и 32 байтов ключа. Поэтому все такие ключи начинаются с `z6Mk`.

Сверх стандарта у ключа три отметки времени, все необязательные:
`notBefore` — с какого момента действует, `revoked` — плановый отзыв,
`compromised` — с какого момента ключ считается украденным. Плановый отзыв
не отменяет подписи до него; компрометация помечает более поздние подписи
сомнительными. Без отдельной отметки сосед не отличил бы плановую смену ключа
от взлома.
"""
import urllib.parse

from . import log

ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
ED25519_PUB = b'\xed\x01'
KEY_TYPE = 'Ed25519VerificationKey2020'
CONTEXT = ['https://www.w3.org/ns/did/v1',
           'https://w3id.org/security/suites/ed25519-2020/v1']


def b58encode(raw):
    number = int.from_bytes(raw, 'big')
    out = ''
    while number:
        number, rest = divmod(number, 58)
        out = ALPHABET[rest] + out
    zeros = len(raw) - len(raw.lstrip(b'\0'))
    return '1' * zeros + out


def b58decode(text):
    number = 0
    for char in text:
        index = ALPHABET.find(char)
        if index < 0:
            raise log.Invalid('знак %r не из алфавита base58' % char)
        number = number * 58 + index
    body = number.to_bytes((number.bit_length() + 7) // 8, 'big') if number else b''
    zeros = len(text) - len(text.lstrip('1'))
    return b'\0' * zeros + body


def multibase(public_key):
    """Открытый ключ Ed25519 в виде `publicKeyMultibase`."""
    if len(public_key) != 32:
        raise log.Invalid('ключ Ed25519 — 32 байта, а не %d' % len(public_key))
    return 'z' + b58encode(ED25519_PUB + public_key)


def from_multibase(text):
    if not text.startswith('z'):
        raise log.Invalid('ожидается base58btc (префикс z)')
    raw = b58decode(text[1:])
    if not raw.startswith(ED25519_PUB) or len(raw) != 34:
        raise log.Invalid('это не открытый ключ Ed25519')
    return raw[2:]


def url(did, scheme='https'):
    """Где лежит документ: по спецификации did:web.

    did:web:coop.example.ru              -> https://coop.example.ru/.well-known/did.json
    did:web:hub.example.ru:org:borozda   -> https://hub.example.ru/org/borozda/did.json
    did:web:localhost%3A8070             -> https://localhost:8070/.well-known/did.json
    """
    if not log.DID_RE.match(did):
        raise log.Invalid('не did:web: %r' % did)
    parts = did[len('did:web:'):].split(':')
    host = urllib.parse.unquote(parts[0])
    path = '/'.join(urllib.parse.unquote(p) for p in parts[1:])
    return '%s://%s/%s' % (scheme, host, (path + '/did.json') if path else '.well-known/did.json')


def document(did, keys):
    """Собрать документ. keys — список словарей: kid, public_key (bytes),
    необязательно not_before, revoked, compromised (строки времени)."""
    methods = []
    for key in keys:
        if not key['kid'].startswith(did + '#'):
            raise log.Invalid('ключ %s не принадлежит %s' % (key['kid'], did))
        method = {'id': key['kid'], 'type': KEY_TYPE, 'controller': did,
                  'publicKeyMultibase': multibase(key['public_key'])}
        for field, name in (('not_before', 'notBefore'), ('revoked', 'revoked'),
                            ('compromised', 'compromised')):
            if key.get(field):
                method[name] = key[field]
        methods.append(method)
    return {'@context': CONTEXT, 'id': did, 'verificationMethod': methods,
            'assertionMethod': [m['id'] for m in methods]}


def keyring(doc, did=None, into=None):
    """Разобрать документ соседа в связку ключей. `did` — кого мы ожидали:
    документ, выданный за другой узел, отвергается."""
    if did is not None and doc.get('id') != did:
        raise log.Invalid('документ описывает %r, а ожидался %r' % (doc.get('id'), did))
    owner = doc.get('id', '')
    if not log.DID_RE.match(owner):
        raise log.Invalid('в документе нет корректного id')
    ring = into or log.KeyRing()
    for method in doc.get('verificationMethod') or []:
        if method.get('type') != KEY_TYPE:
            continue                    # незнакомый тип ключа — не наш, не ломаемся
        kid = method.get('id', '')
        if not kid.startswith(owner + '#'):
            raise log.Invalid('ключ %r объявлен не своим узлом' % kid)
        ring.add(kid, from_multibase(method['publicKeyMultibase']),
                 since=method.get('notBefore') or '0000-01-01T00:00:00Z',
                 revoked=method.get('revoked'), compromised=method.get('compromised'))
    return ring
