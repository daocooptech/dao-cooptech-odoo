# -*- coding: utf-8 -*-
"""Ответственные у каждой организации (решение 450).

У живой организации на площадке есть руководитель с правом подписи, кто-то
ведёт её счета и кто-то отвечает за сделки. До 07.10.2026 право подписи
было у 45 организаций из 190, а у 25 не было ни одного человека-члена:
такая организация не может ни выставить счёт, ни подписать акт — её
сделки делал загрузчик сверху.

Шаг добирает недостающее и ничего не отбирает:

* руководитель — тот, у кого уже есть право подписи; иначе учредитель или
  член правления; иначе назначается человек: в кооперативе и НКО —
  правление, в коммерческой — сотрудник-директор;
* счета — если полномочия «Бухгалтерия и счета» нет ни у кого, появляется
  главный бухгалтер (сотрудник);
* сделки — если полномочия «Сделки» нет ни у кого, оно у руководителя.

Люди назначаются из того же города, а при нехватке — из любого, начиная с
тех, у кого меньше всего мест работы. Жребий — от номера организации:
повторный прогон даёт тот же состав.
"""
import logging
import random
from datetime import date, timedelta

_logger = logging.getLogger(__name__)

TEST_NAMES = ('Danil', 'Proverka Vyhoda',
              'Игнатьев Денис Олегович', 'Прохорова Вера Андреевна')

HEAD_TITLES = {
    'cooperative': 'Председатель правления',
    'nonprofit': 'Директор',
    'decentralized': 'Координатор',
    'commercial': 'Генеральный директор',
}


def load_staff(env):
    Partner = env['res.partner'].sudo()
    Membership = env['coop.membership'].sudo()
    Power = env['coop.power'].sudo()
    Role = env['coop.membership.role'].sudo()
    powers = {p.code: p for p in Power.search([])}
    roles = {r.code: r for r in Role.search([])}
    if not {'sign', 'treasury', 'deal'} <= set(powers):
        return 0

    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('user_ids', '!=', False), ('name', 'not in', TEST_NAMES)], order='id')
    load = {p.id: 0 for p in people}
    for m in Membership.search([('state', '=', 'active'), ('partner_id', 'in', people.ids)]):
        load[m.partner_id.id] += 1

    orgs = Partner.search([('is_company', '=', True), ('coop_is_participant', '=', True)], order='id')
    added = granted = 0
    for org in orgs:
        rnd = random.Random(20261009 + org.id)
        group = org.coop_legal_form_group_id.code or 'commercial'
        active = Membership.search([
            ('organization_id', '=', org.id), ('state', '=', 'active'),
            ('partner_id.is_company', '=', False)], order='id')

        def holders(code):
            return active.filtered(lambda m: powers[code] in m.power_ids)

        # Открытое членство у человека в организации бывает одно: поданное
        # и выходящее тоже считаются, и второе такое же база не примет.
        taken = set(Membership.search([
            ('organization_id', '=', org.id),
            ('state', 'in', ('applied', 'active', 'leaving'))]).partner_id.ids)

        def pick_person(exclude):
            exclude = set(exclude) | taken
            pool = people.filtered(lambda p: p.id not in exclude)
            same_city = pool.filtered(lambda p: p.city and p.city == org.city)
            pool = same_city or pool
            if not pool:
                return Partner.browse()
            least = min(load[p.id] for p in pool)
            fit = pool.filtered(lambda p: load[p.id] == least)
            return fit[rnd.randrange(len(fit))]

        def appoint(person, role_code, title, codes, months_ago):
            role = roles.get(role_code)
            if not role or not role.fits_group(org.coop_legal_form_group_id):
                role = roles['staff']
            joined = date(2026, 10, 1) - timedelta(days=30 * months_ago)
            membership = Membership.create({
                'partner_id': person.id,
                'organization_id': org.id,
                'role_id': role.id,
                'state': 'active',
                'job_title': title,
                'joined_on': joined,
                'admission_basis': (
                    'Протокол собрания № %s от %s' % (rnd.randint(1, 40), joined.strftime('%d.%m.%Y'))
                    if role.code != 'staff' else
                    'Приказ о приёме № %s-к от %s' % (rnd.randint(1, 90), joined.strftime('%d.%m.%Y'))),
                'power_ids': [(6, 0, [powers[c].id for c in codes if c in powers])],
            })
            load[person.id] = load.get(person.id, 0) + 1
            taken.add(person.id)
            return membership

        # Руководитель с правом подписи. Ищем его там же, где ищет правило
        # исключительности: у подавшего и у выходящего право подписи тоже
        # занято, и второе выдать нельзя.
        head = holders('sign')[:1] or Membership.search([
            ('organization_id', '=', org.id),
            ('state', 'in', ('applied', 'active', 'leaving')),
            ('power_ids', 'in', powers['sign'].id)], limit=1)
        if not head:
            # Ревизия проверяет и исполнительных полномочий не получает;
            # рабочая группа платформы в чужой организации не действует.
            eligible = active.filtered(lambda m: m.role not in ('audit', 'platform'))
            head = (eligible.filtered(lambda m: m.role in ('founder', 'board'))
                    or eligible)[:1]
            if head:
                head.power_ids = [(4, powers['sign'].id), (4, powers['deal'].id)]
                if not head.job_title:
                    head.job_title = HEAD_TITLES.get(group, 'Руководитель')
                granted += 1
            else:
                person = pick_person(set())
                if not person:
                    continue
                head = appoint(
                    person, 'board' if group != 'commercial' else 'staff',
                    HEAD_TITLES.get(group, 'Руководитель'),
                    ('sign', 'deal', 'publish', 'represent', 'roster', 'powers', 'site'),
                    rnd.randint(8, 60))
                added += 1
                active |= head

        # Счета.
        if not holders('treasury'):
            exclude = set(active.partner_id.ids)
            person = pick_person(exclude)
            if person:
                active |= appoint(person, 'staff', 'Главный бухгалтер',
                                  ('treasury', 'represent'), rnd.randint(3, 48))
                added += 1
            else:
                head.power_ids = [(4, powers['treasury'].id)]
                granted += 1

        # Сделки.
        if not holders('deal'):
            head.power_ids = [(4, powers['deal'].id)]
            granted += 1

    _logger.info('Ответственные: назначено людей %s, выдано полномочий %s', added, granted)
    return added
