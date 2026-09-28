# -*- coding: utf-8 -*-
"""Ed25519 через `cryptography` вместо эталонного `ed25519.py`.

Эталон написан на чистом Python ради проверяемости: его можно прочитать
строку за строкой и сверить с RFC 8032. Для работы он не годится — в сто
раз медленнее (5 мс на подпись против 0,05 мс) и не защищён от атак по
времени. `cryptography` входит в требования самого Odoo.

Файлы эталона не правятся (их отпечатки сверяет тест), поэтому модули
журнала и читателя получают этот адаптер подменой ссылки на модуль: они
обращаются к `ed25519.sign(...)` в момент вызова, а не при импорте.
Интерфейс тот же: sign(secret, message), verify(public, message, sig),
public_key(secret) — байты на входе и выходе.
"""
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .fedproto import log as _log, reader as _reader


def public_key(secret):
    return Ed25519PrivateKey.from_private_bytes(secret).public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)


def sign(secret, message):
    return Ed25519PrivateKey.from_private_bytes(secret).sign(message)


def verify(public, message, signature):
    try:
        Ed25519PublicKey.from_public_bytes(public).verify(signature, message)
    except (InvalidSignature, ValueError):
        return False
    return True


def generate():
    """Новый секрет — 32 случайных байта из генератора ОС."""
    from cryptography.hazmat.primitives.serialization import NoEncryption, PrivateFormat
    return Ed25519PrivateKey.generate().private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption())


class _Adapter(object):
    sign = staticmethod(sign)
    verify = staticmethod(verify)
    public_key = staticmethod(public_key)


_log.ed25519 = _Adapter
_reader.ed25519 = _Adapter
