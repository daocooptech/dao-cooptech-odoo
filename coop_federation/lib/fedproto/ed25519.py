# -*- coding: utf-8 -*-
"""Ed25519 на чистом Python — справочная реализация (RFC 8032).

Зачем свой код, когда есть libsodium. Затем, что спецификация обмена должна
проверяться где угодно и без установки зависимостей: этот модуль нужен
тестам и тем, кто пишет свой узел на другом стеке и сверяет байты.

В продакшне так подписывать нельзя: чистый Python на порядки медленнее и не
защищён от атак по времени. Узел использует `cryptography` или libsodium;
здесь — эталон, по которому сверяются их результаты.

Корректность проверяется тестовыми векторами RFC 8032 §7.1 в
test_federation.py.
"""
import hashlib

P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, P - 2, P) % P
_SQRT_M1 = pow(2, (P - 1) // 4, P)

ZERO = (0, 1, 1, 0)                     # нейтральный элемент, расширенные координаты


def _inv(x):
    return pow(x, P - 2, P)


def _recover_x(y, sign):
    """Восстановить x по y и биту знака — точка лежит на кривой Эдвардса."""
    if y >= P:
        return None
    xx = (y * y - 1) * _inv(_D * y * y + 1) % P
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P != 0:
        x = x * _SQRT_M1 % P
    if (x * x - xx) % P != 0:
        return None
    if x == 0 and sign:
        return None
    if x & 1 != sign:
        x = P - x
    return x


_BY = 4 * _inv(5) % P
_BX = _recover_x(_BY, 0)
B = (_BX, _BY, 1, _BX * _BY % P)         # базовая точка


def _add(p1, p2):
    x1, y1, z1, t1 = p1
    x2, y2, z2, t2 = p2
    a = (y1 - x1) * (y2 - x2) % P
    b = (y1 + x1) * (y2 + x2) % P
    c = 2 * t1 * t2 * _D % P
    d = 2 * z1 * z2 % P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _mul(point, scalar):
    result = ZERO
    addend = point
    while scalar > 0:
        if scalar & 1:
            result = _add(result, addend)
        addend = _add(addend, addend)
        scalar >>= 1
    return result


def _equal(p1, p2):
    x1, y1, z1, _ = p1
    x2, y2, z2, _ = p2
    return (x1 * z2 - x2 * z1) % P == 0 and (y1 * z2 - y2 * z1) % P == 0


def _encode(point):
    x, y, z, _ = point
    zi = _inv(z)
    x, y = x * zi % P, y * zi % P
    return int.to_bytes(y | ((x & 1) << 255), 32, 'little')


def _decode(data):
    if len(data) != 32:
        return None
    value = int.from_bytes(data, 'little')
    sign = value >> 255
    y = value & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % P)


def _sha512(*chunks):
    digest = hashlib.sha512()
    for chunk in chunks:
        digest.update(chunk)
    return digest.digest()


def _clamp(head):
    """Обрезка скаляра по RFC 8032: младшие три бита в ноль, бит 254 в единицу."""
    scalar = int.from_bytes(head, 'little')
    scalar &= (1 << 255) - 8
    scalar &= (1 << 254) - 1
    scalar |= 1 << 254
    return scalar


def public_key(secret):
    """32 байта секрета -> 32 байта открытого ключа."""
    if len(secret) != 32:
        raise ValueError('секрет Ed25519 — ровно 32 байта')
    return _encode(_mul(B, _clamp(_sha512(secret)[:32])))


def sign(secret, message):
    """Подпись сообщения: 64 байта."""
    digest = _sha512(secret)
    scalar = _clamp(digest[:32])
    prefix = digest[32:]
    encoded_key = _encode(_mul(B, scalar))
    r = int.from_bytes(_sha512(prefix, message), 'little') % L
    encoded_r = _encode(_mul(B, r))
    k = int.from_bytes(_sha512(encoded_r, encoded_key, message), 'little') % L
    s = (r + k * scalar) % L
    return encoded_r + int.to_bytes(s, 32, 'little')


def verify(key, message, signature):
    """Проверка подписи. Никаких исключений наружу — только True/False."""
    if len(signature) != 64 or len(key) != 32:
        return False
    point_a = _decode(key)
    point_r = _decode(signature[:32])
    if point_a is None or point_r is None:
        return False
    s = int.from_bytes(signature[32:], 'little')
    if s >= L:                           # нестрогая проверка пропустила бы ковкие подписи
        return False
    k = int.from_bytes(_sha512(signature[:32], key, message), 'little') % L
    return _equal(_mul(B, s), _add(point_r, _mul(point_a, k)))
