# -*- coding: utf-8 -*-
"""Кооперативные участки потребительских обществ (решение 428).

Участок по 3085-1 (ст. 1, 17) — часть общества, объединяющая пайщиков для
собраний, как правило по месту жительства. У каждого потребительского
общества с заметным составом — участки по городам, где живут его пайщики.
У самого крупного — ещё участок «Шанхай»: граждане РФ, живущие в Шанхае
(валютные резиденты, налоговые нерезиденты), и иностранец. Только членство
и голосование — без деятельности в Китае (заключение юриста 28.09).
"""
import datetime
import logging

_logger = logging.getLogger(__name__)

MAIN_LOGIN = 'dashkevich'
SHANGHAI_SIZE = 6

MEETINGS = [
    (-120, 'online', 'held', 'Выборы уполномоченного на общее собрание уполномоченных',
     'Уполномоченным избран {delegate}'),
    (-45, 'online', 'held', 'Вопрос о вступлении общества в союз потребительских обществ',
     'Поддержать вступление'),
    (20, 'online', 'planned', 'Отчёт правления за год и порядок кооперативных выплат', ''),
]


def _meetings(env, section, members):
    Meeting = env['coop.org.section.meeting'].sudo()
    if section.meeting_ids:
        return
    today = datetime.date.today()
    delegate = section.delegate_ids[:1].name or '—'
    n = max(len(members), 1)
    for shift, mode, state, agenda, decision in MEETINGS:
        values = {
            'section_id': section.id,
            'date': today + datetime.timedelta(days=shift),
            'mode': mode,
            'state': state,
            'agenda': agenda,
            'decision': decision.format(delegate=delegate) if state == 'held' else False,
        }
        if state == 'held':
            against = n // 6
            abstain = 1 if n > 3 else 0
            values.update(votes_for=max(n - against - abstain, 1),
                          votes_against=against, votes_abstain=abstain)
        Meeting.create(values)


def load_sections(env):
    if 'coop.org.section' not in env:
        return
    Section = env['coop.org.section'].sudo()
    Membership = env['coop.membership'].sudo().with_context(tracking_disable=True)
    Partner = env['res.partner'].sudo().with_context(tracking_disable=True)
    member_role = env['coop.membership.role'].sudo().search([('code', '=', 'member')], limit=1)
    russia = env['res.country'].sudo().search([('code', '=', 'RU')], limit=1)
    china = env['res.country'].sudo().search([('code', '=', 'CN')], limit=1)
    main = env['res.users'].sudo().search([('login', '=', MAIN_LOGIN)], limit=1).partner_id

    societies = Partner.search([('coop_cooperative_kind', '=', 'consumer_society')], order='id')
    biggest, biggest_count = None, 0
    made = 0
    for org in societies:
        active = Membership.search([('organization_id', '=', org.id), ('state', '=', 'active')])
        if len(active) < 4:
            continue
        if len(active) > biggest_count:
            biggest, biggest_count = org, len(active)
        # Участки по городам, где живут пайщики: три самых людных, остальные —
        # к самому большому из них.
        # Только российские города и только где пайщиков хотя бы двое:
        # участок из одного человека собрания не проведёт. Живущие за
        # границей — в самом людном участке, пока своего у них нет.
        by_city = {}
        for m in active:
            if m.partner_id.country_id.code == 'RU' and m.partner_id.city:
                by_city.setdefault(m.partner_id.city, []).append(m)
        cities = sorted((c for c in by_city if len(by_city[c]) >= 2),
                        key=lambda c: -len(by_city[c]))[:3]
        if not cities:
            cities = [org.city or 'Центральный']
        sections = {}
        for seq, city in enumerate(cities):
            name = 'Участок «%s»' % city
            section = Section.search([('organization_id', '=', org.id), ('name', '=', name)], limit=1)
            if not section:
                section = Section.create({'organization_id': org.id, 'name': name,
                                          'city': city, 'country_id': russia.id, 'sequence': seq + 1})
                made += 1
            sections[city] = section
        first = sections[cities[0]]
        for m in active:
            if m.section_id and m.section_id.city == 'Шанхай':
                continue
            target = sections.get(m.partner_id.city, first)
            if m.section_id != target:
                m.section_id = target.id
        for section in sections.values():
            members = section.membership_ids.filtered(lambda m: m.state == 'active')
            if not section.delegate_ids and members:
                section.delegate_ids = [(6, 0, [members.sorted('id')[0].partner_id.id])]
            _meetings(env, section, members)

    if biggest and china and member_role:
        _shanghai(env, biggest, china, member_role, main)
    _logger.info('Кооперативные участки: заведено %s, крупнейшее общество — %s',
                 made, biggest.name if biggest else '—')


def _shanghai(env, org, china, member_role, main):
    """Участок «Шанхай» крупнейшего общества — только членство и голосование."""
    Section = env['coop.org.section'].sudo()
    Membership = env['coop.membership'].sudo().with_context(tracking_disable=True)
    Partner = env['res.partner'].sudo().with_context(tracking_disable=True)
    section = Section.search([('organization_id', '=', org.id), ('name', '=', 'Участок «Шанхай»')], limit=1)
    if not section:
        section = Section.create({'organization_id': org.id, 'name': 'Участок «Шанхай»',
                                  'city': 'Шанхай', 'country_id': china.id, 'sequence': 90})
    members = Membership.search([('section_id', '=', section.id)])
    people = members.mapped('partner_id')
    if len(people) < SHANGHAI_SIZE:
        # Пайщики самого общества, переехавшие в Шанхай: новых членств не
        # заводим — чистка оставляет человеку не больше заданного числа и
        # сняла бы их. Сначала те, кто уже живёт в Шанхае; не трогаем
        # главного участника, правление и уполномоченных других участков.
        delegates = set(Section.search([('organization_id', '=', org.id)]).mapped('delegate_ids').ids)
        candidates = Membership.search([
            ('organization_id', '=', org.id), ('state', '=', 'active'),
            ('section_id', '!=', section.id), ('partner_id', '!=', main.id),
            ('partner_id.is_company', '=', False)], order='id desc')
        candidates = candidates.filtered(
            lambda m: m.role not in ('board', 'founder', 'audit', 'staff')
            and m.partner_id.id not in delegates)
        candidates = candidates.sorted(lambda m: 0 if m.partner_id.city == 'Шанхай' else 1)
        for membership in candidates[:SHANGHAI_SIZE - len(people)]:
            membership.section_id = section.id
        members = Membership.search([('section_id', '=', section.id)])
        people = members.mapped('partner_id')
    if len(people) < SHANGHAI_SIZE:
        # Своих рядовых пайщиков не хватило — принимаем новых. Чистка членств
        # (`load_memberships.trim_memberships`) держит членство в зарубежном
        # участке наравне с правлением и снимает у человека другое, рядовое.
        taken = set(Membership.search([('organization_id', '=', org.id)]).mapped('partner_id').ids)
        pool = Partner.search([('coop_is_participant', '=', True), ('is_company', '=', False),
                               ('id', 'not in', list(taken)), ('id', '!=', main.id)], order='id desc')
        pool = pool.filtered(lambda p: p.country_id.code == 'RU')
        for partner in pool[:SHANGHAI_SIZE - len(people)]:
            Membership.create({
                'partner_id': partner.id, 'organization_id': org.id,
                'role_id': member_role.id, 'state': 'active',
                'joined_on': datetime.date.today() - datetime.timedelta(days=200 + partner.id % 300),
                'admission_basis': 'Решение правления, заявление подано онлайн',
                'section_id': section.id,
            })
        members = Membership.search([('section_id', '=', section.id)])
        people = members.mapped('partner_id')
    # Проживание — Шанхай. Граждане РФ — валютные резиденты, но налоговые
    # нерезиденты; один — иностранец (нерезидент). Раз в прогон, потому что
    # разброс резидентства идёт раньше и мог вернуть их в Россию.
    for index, partner in enumerate(people.sorted('id')):
        fx = index != len(people) - 1
        values = {'country_id': china.id, 'city': 'Шанхай',
                  'coop_fx_resident': fx, 'coop_tax_resident': False}
        if any(partner[k] != (v if k != 'country_id' else china) for k, v in values.items()):
            partner.write(values)
    if not section.delegate_ids and people:
        section.delegate_ids = [(6, 0, [people.sorted('id')[0].id])]
    _meetings(env, section, members)
