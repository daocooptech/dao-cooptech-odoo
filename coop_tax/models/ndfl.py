# -*- coding: utf-8 -*-
"""Шкала НДФЛ — по тексту ст. 224 НК, а не по памяти.

Резиденту — п. 1: 13 % до 2,4 млн ₽ за год, сверх — 15 / 18 / 20 / 22 %
на суммах свыше 2,4 / 5 / 20 / 50 млн ₽. Нерезиденту — п. 3: «30
процентов в отношении всех доходов», если соглашение об избежании
двойного налогообложения не даёт меньше (решение 513, разбор К1).

Ставка прогрессивная по сумме за налоговый период у одного агента:
налог с выплаты — разница налога с накопленной базы после неё и до неё.
"""
from decimal import ROUND_HALF_UP, Decimal

# (верхняя граница ступени, ставка в процентах); последняя — без границы.
RESIDENT_SCALE = (
    (2_400_000, 13),
    (5_000_000, 15),
    (20_000_000, 18),
    (50_000_000, 20),
    (None, 22),
)
NON_RESIDENT_RATE = 30


def scale_tax(total):
    """Налог по шкале п. 1 ст. 224 с накопленной за год базы."""
    tax, lower = 0.0, 0
    for upper, rate in RESIDENT_SCALE:
        if total <= lower:
            break
        top = total if upper is None else min(total, upper)
        tax += (top - lower) * rate / 100.0
        if upper is None or total <= upper:
            break
        lower = upper
    return tax


def rubles(amount):
    """Налог — в полных рублях, половина копеек — вверх."""
    return float(Decimal(str(amount)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def ndfl(base, earlier_base=0.0, resident=True, treaty_rate=0.0):
    """Налог с выплаты и подпись ставки.

    `earlier_base` — база по прежним выплатам этого агента этому человеку
    за тот же год: от неё зависит, на какую ступень шкалы попадёт новая.
    """
    if base <= 0:
        return 0.0, ''
    if not resident:
        if treaty_rate and treaty_rate < NON_RESIDENT_RATE:
            return rubles(base * treaty_rate / 100.0), '%g %% по соглашению' % treaty_rate
        return rubles(base * NON_RESIDENT_RATE / 100.0), '%d %% — нерезидент' % NON_RESIDENT_RATE
    tax = rubles(scale_tax(earlier_base + base) - scale_tax(earlier_base))
    rates = [rate for lower, (upper, rate) in zip(
        [0] + [u for u, _ in RESIDENT_SCALE[:-1]], RESIDENT_SCALE)
        if earlier_base + base > lower and (upper is None or earlier_base < upper)]
    label = '%d %%' % rates[0] if len(rates) == 1 else '%d–%d %%' % (rates[0], rates[-1])
    return tax, label
