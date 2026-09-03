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
    name = fields.Char('Учебное заведение', required=True)
    speciality = fields.Char('Специальность')
    year_from = fields.Integer('Год поступления')
    year_to = fields.Integer('Год выпуска')
    level = fields.Selection([
        ('school', 'Школа'),
        ('college', 'Училище или техникум'),
        ('higher', 'Высшее'),
        ('courses', 'Курсы'),
    ], string='Уровень', default='higher', required=True)

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
