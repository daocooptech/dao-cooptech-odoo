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
