# -*- coding: utf-8 -*-
"""Реквизиты организаций для первичных документов (задача 297).

УПД, счёт-фактура, акт печатаются из реквизитов, которых у организаций
не было: ОКПО, ID участника ЭДО, руководитель с должностью, у части — ИНН,
КПП, ОГРН. Здесь они заполняются у каждой организации-участника.

ИНН у организации лежит в двух полях: платформенном `coop_inn` (его видно
на карточке) и штатном `vat` (через него движковый `inn`, по которому
собираются документы). Главный — `coop_inn`: что видно на карточке, то и
идёт в документ. Если его нет, а `vat` — верный ИНН, берётся `vat`; иначе
номер заводится заново с верной контрольной суммой. КПП так же: движковый
`kpp` повторяет `coop_kpp`. ОГРН уже связан с `coop_ogrn` в `coop_l10n_ru`.

Руководитель компании учёта — член организации с полномочием «Подпись»:
в УПД это «руководитель или иное уполномоченное лицо», и должность в
документ идёт его собственная — директор, председатель или бухгалтер по
доверенности. Главный бухгалтер — член с такой должностью. Оба должны быть
пользователями платформы: документ подписывает тот, кто может войти.

Прогон повторяемый: заполненное не перезаписывается, кроме зеркал
`vat`/`kpp`, которые всегда выравниваются по платформенным полям.
"""
import hashlib
import logging

from .load_org_profiles import (INN_WEIGHTS_10, INN_WEIGHTS_11, INN_WEIGHTS_12,
                                _inn, _kpp, _ogrn, region_of)

_logger = logging.getLogger(__name__)

EDI_OPERATOR = '2BM'

def _checksum(digits, weights):
    return sum(int(d) * w for d, w in zip(digits, weights)) % 11 % 10


def _valid_inn(value):
    value = (value or '').strip()
    if not value.isdigit():
        return False
    if len(value) == 10:
        return int(value[9]) == _checksum(value, INN_WEIGHTS_10)
    if len(value) == 12:
        return (int(value[10]) == _checksum(value, INN_WEIGHTS_11)
                and int(value[11]) == _checksum(value, INN_WEIGHTS_12))
    return False


def _okpo(seed, individual=False):
    """ОКПО с верным контрольным разрядом: 8 знаков у организации, 10 у ИП.

    Разряд — сумма цифр с весами 1, 2, 3… по модулю 11; если вышло 10 —
    веса 3, 4, 5…; если снова 10 — ноль.
    """
    size = 10 if individual else 8
    body = '%0*d' % (size - 1, seed * 104729 % 10 ** (size - 1))
    body = str(int(body[0]) % 9 + 1) + body[1:]
    check = sum(int(d) * (i % 10 + 1) for i, d in enumerate(body)) % 11
    if check == 10:
        check = sum(int(d) * ((i + 2) % 10 + 1) for i, d in enumerate(body)) % 11
    return body + str(check % 10)


def _edi(seed, inn, kpp):
    """ID участника ЭДО в Диадоке: код оператора, ИНН, КПП и номер ящика."""
    box = str(int(hashlib.sha1(str(seed).encode()).hexdigest(), 16))[:21]
    return '-'.join(part for part in (EDI_OPERATOR, inn, kpp, '20' + box) if part)


def _signatory(org, code):
    # Заявление о выходе подписи не снимает: полномочие действует, пока
    # членство не прекращено.
    return org.coop_member_ids.filtered(
        lambda m: m.state != 'ended' and code in m.power_ids.mapped('code'))[:1]


def _ensure_signatory(org, env):
    """Подписант организации; если его нет — первый участник-пользователь.

    У действующей организации подписывать документы кто-то вправе всегда:
    без этого она не выставит ни счёта, ни акта.
    """
    signer = _signatory(org, 'sign')
    if signer:
        return signer
    power = env['coop.power'].sudo().search([('code', '=', 'sign')], limit=1)
    users = env['res.users'].sudo().search([]).mapped('partner_id')
    member = org.coop_member_ids.filtered(
        lambda m: m.state == 'active' and m.partner_id in users).sorted('id')[:1]
    if power and member:
        member.sudo().power_ids = [(4, power.id)]
    return member


def _user_of(partner, env):
    return env['res.users'].sudo().search([('partner_id', '=', partner.id)], limit=1)


def load_requisites(env):
    Partner = env['res.partner'].sudo()
    orgs = Partner.search([('is_company', '=', True), ('coop_is_participant', '=', True)],
                          order='id')
    taken = set(Partner.with_context(active_test=False).search(
        [('coop_inn', '!=', False)]).mapped('coop_inn'))
    cities = [c for c in orgs.mapped('city') if c]
    stats = dict(inn=0, kpp=0, ogrn=0, okpo=0, edi=0, city=0,
                 function=0, chief=0, accountant=0, no_chief=0)

    for org in orgs:
        individual = org.coop_legal_form_id.code == 'ip'
        seed = 5000 + org.id
        values = {}

        region = region_of(org.city)
        size = 12 if individual else 10

        def usable(value):
            return _valid_inn(value) and len(value) == size and value[:2] != '00'

        inn = org.coop_inn
        if not usable(inn):
            inn = org.vat if usable(org.vat) and org.vat not in taken else False
            while not inn or inn in taken:
                inn = _inn(seed, individual, region)
                seed += 7919
            taken.add(inn)
            values['coop_inn'] = inn
            stats['inn'] += 1
        if org.vat != inn:
            values['vat'] = inn

        # КПП и ОГРН — того же региона, что ИНН: код инспекции в КПП — первые
        # четыре цифры ИНН, регион в ОГРН — четвёртая и пятая.
        kpp = org.coop_kpp
        if not individual and (not kpp or kpp[:4] != inn[:4]):
            kpp = _kpp(inn)
            values['coop_kpp'] = kpp
            stats['kpp'] += 1
        if (org.kpp or False) != (kpp or False):
            values['kpp'] = kpp or False

        ogrn = org.coop_ogrn
        if not ogrn or ogrn[3:5] != inn[:2]:
            values['coop_ogrn'] = _ogrn(seed, individual, inn[:2])
            stats['ogrn'] += 1
        if not org.edi or inn not in org.edi:
            values['edi'] = _edi(seed, inn, kpp)
            stats['edi'] += 1
        if not org.okpo:
            values['okpo'] = _okpo(seed, individual)
            stats['okpo'] += 1
        if not org.city and cities:
            values['city'] = cities[seed % len(cities)]
            stats['city'] += 1

        signer = _ensure_signatory(org, env)
        if values:
            org.write(values)

        if signer and signer.job_title and not signer.partner_id.function:
            signer.partner_id.function = signer.job_title
            stats['function'] += 1

        company = org.coop_company_id
        if not company:
            continue
        company_values = {}
        if company.edi != org.edi:
            company_values['edi'] = org.edi
        if not company.edi_operator:
            company_values['edi_operator'] = EDI_OPERATOR
        chief = signer and _user_of(signer.partner_id, env)
        if chief and company.chief_id != chief:
            company_values['chief_id'] = chief.id
            stats['chief'] += 1
        elif not chief and not company.chief_id:
            stats['no_chief'] += 1
        if not company.accountant_id:
            booker = org.coop_member_ids.filtered(
                lambda m: m.state == 'active' and m.job_title == 'Главный бухгалтер')[:1]
            user = booker and _user_of(booker.partner_id, env)
            if user:
                company_values['accountant_id'] = user.id
                stats['accountant'] += 1
        if company_values:
            company.write(company_values)

    _logger.info('Реквизиты организаций (%s): %s', len(orgs), stats)
    return stats
