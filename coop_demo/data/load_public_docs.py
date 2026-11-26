# -*- coding: utf-8 -*-
"""Публичные документы организаций — файлами в «Документах» (решение 704).

Устав, положение о взносах, положение о распределении прибыли, отчётность
за 2025 год. Каждый — PDF, собранный из данных самой организации:
название, форма, ОГРН, ИНН, город, взносы, основа кооперативных выплат,
доля в неделимый фонд, число членов. Прогон повторяемый: документ не
заводится, если карточка уже на него ссылается; текст — от номера записи.
"""
import base64
import io
import logging
import random
from datetime import date

from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)

FONT = 'CoopRoboto'
FONT_BOLD = 'CoopRobotoBold'

MONTHS = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
          'августа', 'сентября', 'октября', 'ноября', 'декабря')

CHARTER_SECTIONS = (
    ('Общие положения', 'Организация создана и действует в соответствии с '
     'законодательством Российской Федерации и настоящим уставом. '
     'Место нахождения — {city}. Организация является юридическим лицом, '
     'имеет самостоятельный баланс, печать и счета в банках.'),
    ('Цели и предмет деятельности', 'Основной вид деятельности — {okved}. '
     'Организация вправе вести любую деятельность, не запрещённую законом, '
     'если она отвечает целям, ради которых организация создана.'),
    ('Участники и порядок приёма', 'Приём в члены — по письменному заявлению '
     'решением правления. Заявление подаётся на платформе ДАО КООПТЕХ; '
     'решение принимается не позднее тридцати дней со дня подачи.'),
    ('Взносы и имущество', 'Вступительный взнос — {entrance}; обязательный '
     'паевой взнос — {share}. Имущество формируется из взносов, доходов от '
     'деятельности и иных не запрещённых законом источников.'),
    ('Распределение доходов', 'Итог года распределяется {basis}. {fund_line}'),
    ('Органы управления', 'Высший орган — общее собрание. Исполнительные '
     'органы — правление и председатель, избираемые на пять лет. Контроль — '
     'ревизионная комиссия.'),
    ('Выход и возврат пая', 'Член вправе выйти по заявлению. Паевой взнос '
     'возвращается по утверждении годовой отчётности, не позднее трёх '
     'месяцев после её утверждения.'),
    ('Реорганизация и ликвидация', 'Реорганизация и ликвидация — по решению '
     'общего собрания или суда в порядке, установленном законом.'),
)


def _register_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if FONT in pdfmetrics.getRegisteredFontNames():
        return
    root = 'web/static/fonts/google/Roboto/'
    pdfmetrics.registerFont(TTFont(FONT, file_path(root + 'Roboto-Regular.ttf')))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, file_path(root + 'Roboto-Bold.ttf')))


def make_pdf(title, org_line, blocks, footer):
    """PDF А4: заголовок, строка организации, разделы (заголовок, текст)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    _register_fonts()
    body = ParagraphStyle('b', fontName=FONT, fontSize=10.5, leading=15, spaceAfter=6)
    head = ParagraphStyle('h', fontName=FONT_BOLD, fontSize=12, leading=16,
                          spaceBefore=8, spaceAfter=4)
    top = ParagraphStyle('t', fontName=FONT_BOLD, fontSize=16, leading=20,
                         alignment=1, spaceAfter=4)
    sub = ParagraphStyle('s', fontName=FONT, fontSize=10.5, leading=14,
                         alignment=1, spaceAfter=10)
    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=22 * mm, rightMargin=18 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm, title=title,
                            author=org_line)
    story = [Paragraph(title, top), Paragraph(org_line, sub)]
    for number, (heading, text) in enumerate(blocks, 1):
        story += [Paragraph('%d. %s' % (number, heading), head), Paragraph(text, body)]
    story += [Spacer(1, 10 * mm), Paragraph(footer, body)]
    pdf.build(story)
    return buffer.getvalue()


def _rub(value):
    return ('%s ₽' % '{:,.0f}'.format(value).replace(',', ' ')) if value else 'размер определяет общее собрание'


def _day(value):
    return '%d %s %d г.' % (value.day, MONTHS[value.month - 1], value.year)


def _facts(org):
    basis = {'labor': 'между членами по личному трудовому участию',
             'turnover': 'между членами пропорционально участию в обороте, '
                         'включая работы по договорам подряда'}
    return {
        'city': org.city or 'Россия',
        'okved': (org.coop_okved_id.name or 'деятельность в интересах членов').lower(),
        'entrance': _rub(org.coop_entrance_fee),
        'share': _rub(org.coop_min_share_fee),
        'basis': basis.get(org.coop_payout_basis,
                           'по решению общего собрания участников'),
        'fund_line': ('В неделимый фонд направляется %s %% итога года.'
                      % '{:g}'.format(org.coop_indivisible_fund_percent))
                     if org.coop_indivisible_fund_percent
                     else 'Неделимый фонд не формируется.',
    }


def _org_line(org):
    parts = [org.name]
    if org.coop_ogrn:
        parts.append('ОГРН %s' % org.coop_ogrn)
    if org.coop_inn:
        parts.append('ИНН %s' % org.coop_inn)
    return ' · '.join(parts)


def _approved(rnd, year_from=2019, year_to=2025):
    return date(rnd.randint(year_from, year_to), rnd.randint(1, 12), rnd.randint(1, 28))


def _charter(org, rnd):
    facts = _facts(org)
    sections = CHARTER_SECTIONS if org.coop_is_cooperative else (
        CHARTER_SECTIONS[0], CHARTER_SECTIONS[1], CHARTER_SECTIONS[5], CHARTER_SECTIONS[7])
    approved = _approved(rnd)
    blocks = [(h, t.format(**facts)) for h, t in sections]
    footer = ('Утверждён общим собранием %s, протокол № %d. Редакция действует '
              'с %s.') % (_day(approved), rnd.randint(1, 30), _day(approved))
    return 'Устав, ред. %d' % approved.year, approved, make_pdf(
        'УСТАВ', _org_line(org), blocks, footer)


def _fees(org, rnd):
    facts = _facts(org)
    approved = _approved(rnd, 2021)
    blocks = [
        ('Вступительный взнос', 'Размер — %s. Вносится в течение десяти дней '
         'после решения правления о приёме и при выходе не возвращается.' % facts['entrance']),
        ('Обязательный паевой взнос', 'Размер — %s. Может вноситься деньгами, '
         'имуществом или правами, оценёнными правлением.' % facts['share']),
        ('Дополнительный паевой взнос', 'Вносится добровольно, увеличивает пай '
         'и учитывается при распределении итога года.'),
        ('Возврат пая', 'Пай возвращается выходящему члену деньгами или, по '
         'соглашению, имуществом — после утверждения годовой отчётности.'),
    ]
    footer = 'Утверждено общим собранием %s.' % _day(approved)
    return 'Положение о взносах', approved, make_pdf(
        'ПОЛОЖЕНИЕ О ВЗНОСАХ И ВОЗВРАТЕ ПАЯ', _org_line(org), blocks, footer)


def _profit(org, rnd):
    facts = _facts(org)
    approved = _approved(rnd, 2021)
    blocks = [
        ('Основа распределения', 'Итог года распределяется %s.' % facts['basis']),
        ('Неделимый фонд', facts['fund_line']),
        ('Сроки', 'Кооперативные выплаты начисляются после утверждения годовой '
         'отчётности общим собранием и выплачиваются в течение трёх месяцев.'),
        ('Форма выплат', 'Деньгами на счёт члена или зачислением в пай — по '
         'заявлению члена.'),
    ]
    footer = 'Утверждено общим собранием %s.' % _day(approved)
    return 'Положение о прибыли', approved, make_pdf(
        'ПОЛОЖЕНИЕ О РАСПРЕДЕЛЕНИИ ПРИБЫЛИ', _org_line(org), blocks, footer)


def _report(org, rnd):
    # Демо-состав заводится позже документов — тогда число из жребия.
    members = (len(org.coop_member_ids.filtered(lambda m: m.state == 'active'))
               or rnd.randint(7, 120))
    revenue = rnd.randint(18, 950) * 100_000
    result = int(revenue * rnd.uniform(-0.04, 0.12))
    approved = date(2026, rnd.randint(3, 6), rnd.randint(1, 28))
    blocks = [
        ('Состав', 'На 31 декабря 2025 года — %d членов.' % members),
        ('Выручка за 2025 год', _rub(revenue) + '.'),
        ('Итог года', ('Прибыль %s.' if result >= 0 else 'Убыток %s.') % _rub(abs(result))),
        ('Паевой фонд', 'На конец года — %s.' % _rub(rnd.randint(5, 400) * 10_000)),
        ('Ревизия', 'Ревизионная комиссия нарушений не выявила; заключение '
         'приложено к протоколу общего собрания.'),
    ]
    footer = 'Утверждена общим собранием %s.' % _day(approved)
    return 'Отчётность за 2025 год', approved, make_pdf(
        'ГОДОВАЯ ОТЧЁТНОСТЬ ЗА 2025 ГОД', _org_line(org), blocks, footer)


BUILDERS = {'charter': (_charter, 'charter.pdf'), 'fees': (_fees, 'fees.pdf'),
            'profit': (_profit, 'profit.pdf'), 'report': (_report, 'report-2025.pdf')}
FIELDS = {'charter': 'coop_charter_doc_id', 'fees': 'coop_fees_rules_doc_id',
          'profit': 'coop_profit_rules_doc_id', 'report': 'coop_report_doc_id'}


def put_docs(org, slots):
    """Завести недостающие публичные документы организации."""
    made = 0
    for slot in slots:
        if org[FIELDS[slot]]:
            continue
        build, file_name = BUILDERS[slot]
        rnd = random.Random('%s-%d' % (slot, org.id))
        name, approved, data = build(org, rnd)
        org.with_context(tracking_disable=True)._coop_put_public_doc(
            slot, name, base64.b64encode(data), file_name, signed_on=approved)
        made += 1
    return made


def load_charters(env):
    """Устав у организаций с правовой формой, кроме ИП и кооперативов
    (у кооперативов документы заводит `load_join_terms`)."""
    orgs = env['res.partner'].sudo().search([
        ('is_company', '=', True), ('coop_is_participant', '=', True),
        ('coop_legal_form_id', '!=', False), ('coop_legal_form_id.code', '!=', 'ip'),
        ('coop_is_cooperative', '=', False), ('coop_charter_doc_id', '=', False)], order='id')
    made = sum(put_docs(org, ('charter',)) for org in orgs)
    _logger.info('Уставы организаций: заведено %s', made)
    return made


def from_old_links(env):
    """Перенос в базе, где документы были ссылками (столбцы `*_url`).

    Где ссылка была — заводится файл того же вида; где не было — пусто,
    как и было (в том числе «устав не выложен», решение 679)."""
    cr = env.cr
    columns = {'coop_charter_url': 'charter', 'coop_fees_rules_url': 'fees',
               'coop_profit_rules_url': 'profit', 'coop_report_url': 'report'}
    cr.execute("""SELECT column_name FROM information_schema.columns
                  WHERE table_name = 'res_partner' AND column_name = ANY(%s)""",
               [list(columns)])
    present = [row[0] for row in cr.fetchall()]
    if not present:
        return 0
    cr.execute('SELECT id, %s FROM res_partner WHERE is_company ORDER BY id'
               % ', '.join(present))
    Partner = env['res.partner'].sudo()
    made = 0
    for row in cr.fetchall():
        org = Partner.browse(row[0])
        slots = [columns[name] for name, value in zip(present, row[1:]) if value]
        # У предпринимателя устава не бывает — старая ссылка была ошибкой.
        if org.coop_legal_form_id.code == 'ip':
            slots = [slot for slot in slots if slot != 'charter']
        if slots:
            made += put_docs(org, slots)
    _logger.info('Публичные документы из ссылок: заведено %s', made)
    return made
