# -*- coding: utf-8 -*-
import random
from datetime import date, timedelta

# Задачи рабочей группы и ДАО-проектов прошлых лет — по ним в реестре
# натуральных доходов история за 2025 год (решение 515).
PAST_TASKS = (
    'Разметка фото ресурсов по рубрикам', 'Перевод справки на казахский',
    'Сверка адресов складов с картой', 'Вычитка карточек вакансий',
    'Описание полок каталога «Сельхозтехника»', 'Проверка ИНН организаций по ЕГРЮЛ',
    'Съёмка склада для витрины', 'Тест оформления сделки с телефона',
    'Сбор отзывов участников о закупках', 'Перевод правил сети на английский',
    'Разбор жалоб на объявления', 'Подбор фото для проектов без снимков',
    'Расшифровка записи общего собрания', 'Сверка рубрик закупок с жизнью',
    'Описание видов пая для справки', 'Проверка ссылок в рассылке',
    'Наполнение каталога навыков', 'Видеоинструкция «Как вступить в кооператив»',
    'Сверка курсов валют в кошельке', 'Опрос фермеров о совместных закупках',
    'Карточки организаций без ОКВЭД', 'Тест выгрузки в 1С',
)


def post_init_hook(env):
    """Узлы выбирают по-разному, и выплаты, проведённые до модуля, получают
    свой НДФЛ.

    Каждый четвёртый кооператив с паевыми счетами выбрал «только сверх
    внесённого» (решение 513): на платформе видны оба варианта и разница
    в «на руки». Остальные — по умолчанию, со всей суммы.
    """
    accounts = env['coop.share.account'].search([])
    coops = accounts.mapped('cooperative_id').sorted('id')
    coops.filtered(lambda c: c.id % 4 == 0).write({'coop_ndfl_share_base': 'excess'})
    moves = env['coop.share.move'].search([('kind', 'in', ('payout', 'return'))])
    moves._coop_tax_fill()
    demo_natural_income(env)
    demo_payout_limits(env)
    demo_labor_payouts(env)


def demo_labor_payouts(env, login='dashkevich'):
    """Выплаты членам артелей за трудовое участие (решения 514, 516).

    Три артели из пяти платят взносы на травматизм — тариф по классу
    риска, у большинства низкий; две из пяти — МСП из перечня. Выплаты
    2025–2026 годов, раз в месяц-два: последняя — ещё начислена, редкие —
    отменены. Нерезиденты-члены работают кто в России с патентом или
    разрешением, кто за рубежом. Витринный человек получает выплаты в
    артели, где у него пай или членство.
    """
    Payout = env['coop.tax.labor.payout'].sudo()
    if Payout.search_count([]):
        return
    rng = random.Random(514)
    coops = env['res.partner'].sudo().search(
        [('coop_cooperative_kind', 'in', ('production', 'agri_production'))], order='id')
    if not coops:
        return
    rates = (0.2, 0.2, 0.2, 0.3, 0.4, 0.5, 0.7, 0.9, 1.2, 1.7, 2.5, 4.1, 8.5)
    for coop in coops:
        paying = rng.random() < 0.6
        coop.write({'coop_injury_insurance': paying,
                    'coop_injury_rate': rng.choice(rates) if paying else 0.2,
                    'coop_tax_sme': rng.random() < 0.4})
    members = env['coop.membership'].sudo().search([
        ('organization_id', 'in', coops.ids), ('state', '=', 'active'),
        ('partner_id.is_company', '=', False)], order='id')
    pairs = [(m.organization_id, m.partner_id) for m in members]
    rng.shuffle(pairs)
    pairs = pairs[:42]
    user = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    if user:
        own = env['coop.share.account'].sudo().search(
            [('partner_id', '=', user.partner_id.id),
             ('cooperative_id', 'in', coops.ids)], limit=1).cooperative_id
        own = own or members.filtered(lambda m: m.partner_id == user.partner_id)[:1].organization_id
        pairs.append((own or coops[0], user.partner_id))

    rows = []
    months = [(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, 11)]
    for coop, person in pairs:
        showcase = user and person == user.partner_id
        picked = months[-6:] if showcase else sorted(rng.sample(months, rng.randint(3, 5)))
        base = rng.randrange(50, 360) * 500
        extra = {}
        if not person.coop_tax_resident:
            if rng.random() < 0.5:
                extra = {'work_place': 'abroad'}
            else:
                extra = {'work_place': 'ru', 'permit': rng.choice(('patent', 'permit'))}
        for year, month in picked:
            amount = max(15000, base + rng.randrange(-20, 21) * 500)
            rows.append((date(year, month, 25 if month != 12 else 20), coop, person, amount, extra))
    last = max(r[0] for r in rows)
    for when, coop, person, amount, extra in sorted(rows, key=lambda r: (r[0], r[1].id, r[2].id)):
        state = 'draft' if when == last else ('cancelled' if rng.random() < 0.05 else 'paid')
        Payout.create(dict(extra, cooperative_id=coop.id, partner_id=person.id,
                           date=when, amount=float(amount), state=state,
                           name='Выплата за трудовое участие, %02d.%d' % (when.month, when.year)))


def demo_payout_limits(env):
    """Лимит кооперативных выплат по годам (решение 517).

    Каждый пятый кооператив считает от доходов после обязательных
    платежей, остальные — от чистой прибыли. Итоги 2024 и 2025 годов — у
    всех, кроме тех, кто 2025 ещё не закрыл; 2022–2023 — там, где за них
    начисляли. Потолок подогнан под проведённые начисления с запасом,
    у трёх лет начислено сверх лимита (до появления контроля), в
    убыточные годы выплат нет.
    """
    Limit = env['coop.tax.payout.limit'].sudo()
    if Limit.search_count([]):
        return
    rng = random.Random(517)
    accounts = env['coop.share.account'].sudo().search([])
    coops = accounts.mapped('cooperative_id').sorted('id')
    coops.filtered(lambda c: c.id % 5 == 0).write({'coop_payout_limit_base': 'income_after_taxes'})
    accrued = {}
    for move in env['coop.share.move'].sudo().search([
            ('kind', '=', 'accrual'), ('state', '=', 'confirmed')]):
        key = (move.account_id.cooperative_id.id, move.coop_result_year)
        accrued[key] = accrued.get(key, 0.0) + move.amount
    open_2025 = set(rng.sample(coops.ids, min(8, len(coops))))
    keys = [(coop, year) for coop in coops for year in (2024, 2025)
            if not (year == 2025 and coop.id in open_2025)]
    keys += [(coop, year) for coop in coops for year in (2022, 2023)
             if accrued.get((coop.id, year))]
    over = set(rng.sample([k for k in keys if accrued.get((k[0].id, k[1]))], 3))
    for coop, year in sorted(keys, key=lambda k: (k[1], k[0].id)):
        done = accrued.get((coop.id, year), 0.0)
        if not done and rng.random() < 0.15:
            net, income, retained = 0.0, rng.randrange(2, 30) * 100000.0, 0.0
        else:
            net = rng.randrange(15, 400) * 10000.0
            income = net * rng.uniform(2.5, 7.0)
            retained = net * rng.uniform(0.55, 0.9)
            base = net if coop.coop_payout_limit_base == 'net_profit' else income
            limit = min(0.2 * base, retained)
            if done:
                target = done * (rng.uniform(0.7, 0.9) if (coop, year) in over
                                 else rng.uniform(1.1, 3.0))
                scale = target / limit
                net, income, retained = net * scale, income * scale, retained * scale
        Limit.create({
            'cooperative_id': coop.id, 'year': year,
            'net_profit': round(net, -3), 'income_after_taxes': round(income, -3),
            'retained': round(retained, -3),
        })


def demo_natural_income(env):
    """Способ оплаты у задач и реестр доходов в натуральной форме.

    Две задачи из пяти — токенами, остальные — ценой в рублях с зачётом.
    В реестре 2025 и 2026 годы во всех состояниях: удержано из выплаты
    пая, удержано частично, не удержано и сообщено, не удержано и ещё не
    сообщено, исчислено в текущем году.
    """
    Income = env['coop.tax.natural.income'].sudo()
    if Income.search_count([]):
        return
    rng = random.Random(515)
    platform = env.company.partner_id
    tasks = env['coop.bounty.task'].sudo().search([], order='id')
    accepted = tasks.filtered(lambda t: t.state == 'accepted')
    for task in tasks:
        tokens = task.id % 5 in (0, 2) if task.state != 'accepted' \
            else accepted.ids.index(task.id) % 2 == 0
        task.write({'payment_mode': 'tokens' if tokens else 'rub_offset',
                    'payer_id': task.payer_id.id or platform.id})

    # История — у тех, кто подавал заявки, и у пайщиков: у вторых агент
    # иногда кооператив, и налог удержан из выплаты пая.
    people = env['coop.bounty.application'].sudo().search([]).mapped('partner_id')
    accounts = env['coop.share.account'].sudo().search([('partner_id.is_company', '=', False)])
    rows = []
    for year, count in ((2025, 80), (2026, 58)):
        start = date(year, 1, 10)
        span = (date(year, 12, 20) if year == 2025 else date(2026, 10, 20)) - start
        for _i in range(count):
            when = start + timedelta(days=rng.randrange(span.days))
            tokens = rng.randrange(6, 61) * 10
            if accounts and rng.random() < 0.3:
                account = rng.choice(accounts)
                rows.append((when, account.partner_id, account.cooperative_id, tokens))
            elif people:
                rows.append((when, rng.choice(people), platform, tokens))
    report_day = date(2026, 2, 20)
    for when, partner, agent, tokens in sorted(rows, key=lambda r: r[0]):
        amount = float(tokens)
        tax, rate = Income._coop_ndfl(partner, agent, amount, when)
        values = {
            'name': 'Вознаграждение за задачу «%s»' % rng.choice(PAST_TASKS),
            'partner_id': partner.id, 'agent_id': agent.id, 'date': when,
            'tokens': tokens, 'amount': amount, 'rate': rate or False,
            'ndfl_amount': tax,
        }
        roll = rng.random()
        payout_day = when + timedelta(days=rng.randrange(5, 40))
        note = 'Выплата пая от %s' % payout_day.strftime('%d.%m.%Y')
        if agent != platform and payout_day.year == when.year:
            if roll < 0.55:
                values.update(withheld=tax, withheld_note=note)
            elif roll < 0.85:
                values.update(withheld=int(tax / 2), withheld_note=note)
        if when.year == 2025 and values.get('withheld', 0) < tax and rng.random() < 0.88:
            values['reported_on'] = report_day
        Income.create(values)

    for task in tasks.filtered(lambda t: t.state == 'accepted' and t.payment_mode == 'tokens'):
        Income._coop_register_task(task)
    demo_natural_income_showcase(env)


def demo_natural_income_showcase(env, login='dashkevich'):
    """Свои доходы в натуральной форме у витринного человека.

    Реестр он видит по правилу «свои доходы»: без своих строк раздел у него
    пуст. Восемь задач за два года — удержано из выплаты пая, удержано
    наполовину, не удержано и сообщено, не удержано и не сообщено,
    исчислено в текущем году.
    """
    Income = env['coop.tax.natural.income'].sudo()
    user = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    if not user or Income.search_count([('partner_id', '=', user.partner_id.id)]):
        return
    partner = user.partner_id
    platform = env.company.partner_id
    account = env['coop.share.account'].sudo().search(
        [('partner_id', '=', partner.id)], order='id', limit=1)
    coop = account.cooperative_id or platform
    # (дата, агент, токены, удержано: 'full' / 'half' / None, сообщено)
    plan = (
        (date(2025, 3, 14), coop, 320, 'full', False),
        (date(2025, 6, 2), platform, 450, None, True),
        (date(2025, 9, 23), coop, 180, 'half', True),
        (date(2025, 11, 17), platform, 600, None, False),
        (date(2026, 2, 9), coop, 240, 'full', False),
        (date(2026, 5, 28), platform, 380, None, False),
        (date(2026, 8, 12), coop, 520, 'half', False),
        (date(2026, 10, 6), platform, 150, None, False),
    )
    for when, agent, tokens, withheld, reported in plan:
        amount = float(tokens)
        tax, rate = Income._coop_ndfl(partner, agent, amount, when)
        values = {
            'name': 'Вознаграждение за задачу «%s»' % PAST_TASKS[when.month % len(PAST_TASKS)],
            'partner_id': partner.id, 'agent_id': agent.id, 'date': when,
            'tokens': tokens, 'amount': amount, 'rate': rate or False,
            'ndfl_amount': tax,
        }
        if withheld and agent != platform:
            note = 'Выплата пая от %s' % (when + timedelta(days=21)).strftime('%d.%m.%Y')
            values.update(withheld=tax if withheld == 'full' else int(tax / 2),
                          withheld_note=note)
        if reported:
            values['reported_on'] = date(2026, 2, 20)
        Income.create(values)
