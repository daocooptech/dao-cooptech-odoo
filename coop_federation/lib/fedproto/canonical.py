# -*- coding: utf-8 -*-
"""Каноническая сериализация события — то, над чем считается хэш и подпись.

Узлы сети пишут на разных языках: Python (Odoo), 1С, PHP (Битрикс, WordPress),
Java (Cyclos). Если сериализация хоть в мелочи разойдётся, подписи перестанут
сходиться, и никто не поймёт почему. Поэтому правила жёсткие и без вариантов:

* UTF-8, без BOM;
* ключи объектов упорядочены по кодовым точкам;
* никаких пробелов и переводов строк между элементами;
* экранирование строк по RFC 8785: короткие формы \\b \\f \\n \\r \\t \\" \\\\,
  остальные управляющие символы — \\u00xx строчными буквами, прочее как есть;
* **вещественные числа запрещены**. Деньги и количества передаются строкой
  с фиксированным числом знаков ("1234.56"), потому что 0.1 + 0.2 в разных
  языках даёт разные байты, а значит разные подписи.

Стандарт тот же, что у JCS (RFC 8785), но реализован явно и без зависимостей:
интегратору проще прочитать сорок строк, чем подбирать библиотеку.
"""
import hashlib

_SHORT = {
    0x08: '\\b', 0x09: '\\t', 0x0A: '\\n', 0x0C: '\\f', 0x0D: '\\r',
    0x22: '\\"', 0x5C: '\\\\',
}


def _string(value):
    out = ['"']
    for char in value:
        code = ord(char)
        if code in _SHORT:
            out.append(_SHORT[code])
        elif code < 0x20:
            out.append('\\u%04x' % code)
        else:
            out.append(char)
    out.append('"')
    return ''.join(out)


def dumps(value):
    """Каноническое представление значения в виде строки."""
    if value is None:
        return 'null'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise TypeError('вещественные числа запрещены: передавай строкой, "%r"' % value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (list, tuple)):
        return '[' + ','.join(dumps(item) for item in value) + ']'
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise TypeError('ключи объекта — только строки, получено %r' % (key,))
        pairs = sorted(value.items(), key=lambda kv: [ord(c) for c in kv[0]])
        return '{' + ','.join(_string(k) + ':' + dumps(v) for k, v in pairs) + '}'
    raise TypeError('нечего сериализовать: %r' % (value,))


def encode(value):
    """Каноническое представление в байтах — именно эти байты подписываются."""
    return dumps(value).encode('utf-8')


def digest(value):
    """SHA-256 канонического представления, шестнадцатеричной строкой."""
    return hashlib.sha256(encode(value)).hexdigest()
