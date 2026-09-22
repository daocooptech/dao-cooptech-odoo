# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CoopEducation(models.Model):
    """Где участник учился.

    Отдельной записью, а не строкой в тексте о себе: по учебному
    заведению люди находят друг друга — однокурсник, земляк, выпускник
    того же училища. Из текста такое не выбрать никаким поиском.

    Проверять дипломы платформа не берётся, и вид это признаёт: запись
    заводит сам участник, и она значит «он так о себе говорит».
    Подтверждённое образование — это уровень проверки в карточке, а не
    эта полоса.
    """

    _name = 'coop.education'
    _description = 'Образование участника'
    _order = 'year_to desc, year_from desc, id desc'

    partner_id = fields.Many2one(
        'res.partner', string='Участник', required=True, ondelete='cascade',
        index=True)
    # Из справочника, а не строкой. Владелец 15 сентября 2026: сокращение
    # брать «из каталога учебных заведений страны». По свободной строке
    # люди друг друга не находят: сто человек, написавших «СФУ», «Сиб.
    # федеральный» и «СибФУ», окажутся из разных мест.
    institution_id = fields.Many2one(
        'coop.institution', string='Учебное заведение', index=True,
        ondelete='restrict')
    # Свободная строка осталась запасной: справочник заведомо неполон, и
    # участник, чьего заведения в нём нет, вписывает своё руками.
    name = fields.Char('Название вручную')
    # Своим вычислением, а не заодно с `display_name`: `display_name` —
    # особое поле движка, и когда на нём висит второе поле, движок
    # пересчитывает его по своим правилам, а наше остаётся пустым.
    # Проверено: после привязки к справочнику 306 записей сокращение у
    # всех осталось незаполненным.
    short_name = fields.Char(
        'Сокращённо', compute='_compute_short_name', store=True,
        help='Из справочника; у вписанного вручную — само название.')
    speciality = fields.Char('Специальность')
    year_from = fields.Integer('Год поступления')
    year_to = fields.Integer('Год выпуска')
    level = fields.Selection([
        ('school', 'Школа'),
        ('college', 'Училище или техникум'),
        ('higher', 'Высшее'),
        ('courses', 'Курсы'),
    ], string='Уровень', default='higher', required=True)

    @api.depends('institution_id.short_name', 'institution_id.name', 'name')
    def _compute_short_name(self):
        for record in self:
            institution = record.institution_id
            record.short_name = (institution.short_name or institution.name
                                 or record.name or '')

    @api.onchange('institution_id')
    def _onchange_institution(self):
        """Ступень подставляется из справочника.

        У заведения она своя и не меняется: университет даёт высшее,
        техникум — профессиональное. Спрашивать об этом участника, когда
        ответ уже известен, значит спрашивать зря.
        """
        for record in self:
            if record.institution_id:
                record.level = record.institution_id.kind

    @api.constrains('institution_id', 'name')
    def _check_institution(self):
        """Либо из справочника, либо вписано руками — но не пусто.

        Обязательным `required` тут не обойтись: обязательных полей два, и
        заполнено должно быть любое из них.
        """
        for record in self:
            if not record.institution_id and not (record.name or '').strip():
                raise ValidationError(_(
                    'Выберите учебное заведение из справочника или впишите '
                    'название вручную.'))

    @api.constrains('year_from', 'year_to')
    def _check_years(self):
        """Выпуск не раньше поступления.

        Без проверки годы молча меняются местами при сортировке, и в
        полосе «Образование» школа оказывается после университета.
        """
        for record in self:
            if record.year_from and record.year_to and \
                    record.year_to < record.year_from:
                raise ValidationError(_(
                    'Год выпуска раньше года поступления: %(to)s и '
                    '%(from)s.') % {'to': record.year_to,
                                    'from': record.year_from})

    years = fields.Char('Годы учёбы', compute='_compute_years')

    @api.depends('year_from', 'year_to')
    def _compute_years(self):
        """Годы одной строкой — «2015 — 2018».

        Двумя столбцами в колонке справок они занимают больше места, чем
        само название заведения, а читаются всё равно как одно значение.
        """
        for record in self:
            if record.year_from and record.year_to:
                record.years = '%s — %s' % (record.year_from, record.year_to)
            else:
                record.years = str(record.year_to or record.year_from or '')

    @api.depends('name', 'year_to')
    def _compute_display_name(self):
        for record in self:
            years = ''
            if record.year_to:
                years = ' · %s' % record.year_to
            record.display_name = '%s%s' % (record.name or '', years)


class CoopAchievement(models.Model):
    """Чем участник может подтвердить, что чего-то стоит.

    В макете это отдельная полоса рядом с навыками, и не зря: навык
    говорит «умею», достижение — «сделал». Второе весомее и живёт по
    другим правилам: навык правят, достижение только добавляют.

    Ссылка на подтверждение необязательна намеренно. Требовать её значит
    выбросить всё, что подтверждается бумагой или людьми, а не ссылкой, —
    а таких достижений у кооператора большинство.
    """

    _name = 'coop.achievement'
    _description = 'Достижение участника'
    _order = 'year desc, id desc'

    partner_id = fields.Many2one(
        'res.partner', string='Участник', required=True, ondelete='cascade',
        index=True)
    name = fields.Char('Достижение', required=True)
    year = fields.Integer('Год')
    description = fields.Text('Подробности')
    proof_url = fields.Char(
        'Подтверждение',
        help='Ссылка на диплом, публикацию или запись в реестре, если она есть.')

    @api.constrains('year')
    def _check_year(self):
        """Год в будущем — это опечатка, а не достижение."""
        current = fields.Date.context_today(self).year
        for record in self:
            if record.year and record.year > current:
                raise ValidationError(_(
                    'Год достижения «%(name)s» — %(year)s, он ещё не '
                    'наступил.') % {'name': record.name, 'year': record.year})
