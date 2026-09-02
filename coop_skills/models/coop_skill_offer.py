# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class CoopSkillOffer(models.Model):
    """Предложение навыка — то, что участник готов делать за вознаграждение.

    Это не справочник умений (им остаётся `hr.skill`, чипы на карточке
    человека) и не вакансия. Вакансию размещает тот, кому нужна работа;
    предложение навыка — тот, кто готов работать. Стороны разные, и
    смешивать их в одном списке нельзя: человек, ищущий сварщика, и
    сварщик, ищущий заказ, должны видеть разные экраны.

    У одного человека предложений может быть несколько — по числу
    специализаций, как несколько резюме на hh.ru. В макете это уже так:
    у Данила Дашкевича отдельные карточки на электромонтаж, кладку и
    веб-дизайн. Одно предложение на человека означало бы, что мастер с
    двумя ремёслами обязан выбрать, каким из них он «на самом деле»
    занимается.
    """
    _name = 'coop.skill.offer'
    _description = 'Предложение навыка'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'write_date desc, id desc'

    name = fields.Char(
        string='Чем занимаюсь', required=True, tracking=True,
        help='Коротко и как называют это заказчики: «Электромонтажник», '
             '«Сварщик», «Бухгалтер на аутсорсе».')
    description = fields.Html(
        string='Описание',
        help='Что именно готовы делать, с каким оборудованием, какие есть '
             'допуски и ограничения.')
    image_1920 = fields.Image(string='Фотография работы', max_width=1920, max_height=1920)
    image_512 = fields.Image(related='image_1920', max_width=512, max_height=512, store=True)

    partner_id = fields.Many2one(
        'res.partner', string='Кто предлагает', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner(), tracking=True)
    author_id = fields.Many2one(
        'res.partner', string='Разместил', readonly=True,
        default=lambda self: self.env.user.partner_id, index=True,
        help='Кто из людей это разместил. У объявления частного лица '
             'совпадает с владельцем; у объявления организации '
             'показывает, кто из её представителей нажал кнопку — без '
             'этого спор «кто это разместил» разбирать нечем.')
    partner_trust = fields.Integer(
        related='partner_id.coop_trust', string='Доверие владельца', store=True)

    coop_specialization_id = fields.Many2one(
        'coop.specialization', string='Специализация', index=True,
        ondelete='restrict',
        help='Из общего справочника платформы — того же, по которому '
             'ищут людей, организации и вакансии.')
    coop_specialization_category_id = fields.Many2one(
        'coop.specialization.category', string='Сфера деятельности',
        related='coop_specialization_id.category_id', store=True, index=True)

    skill_ids = fields.Many2many(
        'hr.skill', 'coop_skill_offer_skill_rel', 'offer_id', 'skill_id',
        string='Умения',
        help='Из чего складывается работа: конкретные операции и допуски.')

    city = fields.Char(string='Город', index=True)
    ready_to_travel = fields.Boolean(
        string='Готов к командировкам', default=False,
        help='Работает не только в своём городе. Для половины ремёсел это '
             'решающее условие, поэтому вынесено отдельным признаком, а не '
             'спрятано в описании.')

    # ── Опыт ─────────────────────────────────────────────────────────────
    #
    # Хранится числом месяцев, а показывается словами. В макете опыт
    # написан по-разному — «3 года 2 месяца» и «От 3 лет», — и по тексту
    # ни отфильтровать, ни отсортировать. Число решает обе задачи, а
    # словесная форма собирается из него.
    experience_months = fields.Integer(string='Опыт, месяцев', default=0)
    experience_display = fields.Char(
        string='Опыт', compute='_compute_experience_display', store=True)
    experience_level = fields.Selection([
        ('none', 'Нет опыта'),
        ('junior', 'От года'),
        ('senior', 'От трёх лет'),
    ], string='Уровень опыта', compute='_compute_experience_display',
        store=True, index=True,
        help='Ступени взяты из макета: по ним ищут, когда точный стаж '
             'неважен.')

    # ── Вознаграждение ───────────────────────────────────────────────────
    rate = fields.Monetary(string='Ставка', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        default=lambda self: self.env.company.currency_id)
    rate_kind = fields.Selection([
        ('from', 'от'),
        ('exact', 'ровно'),
        ('piece', 'сдельно, по договорённости'),
    ], string='Уточнение ставки', default='from', required=True)
    rate_period = fields.Selection([
        ('month', 'в месяц'),
        ('day', 'в день'),
        ('hour', 'в час'),
        ('job', 'за работу'),
    ], string='Период', default='month')
    rate_display = fields.Char(
        string='Ставка строкой', compute='_compute_rate_display', store=True)

    # Ключ источника: по нему запись опознаётся при повторной загрузке из
    # внешнего набора. Опознавать по названию нельзя — оно меняется, и
    # тогда загрузчик заводит запись заново вместо того, чтобы поправить
    # существующую. Так у нас однажды и вышло: правка заголовков в наборе
    # добавила семьдесят четыре двойника.
    import_key = fields.Char(
        string='Ключ источника', index=True, copy=False,
        help='Служебное поле. Заполняется при загрузке из внешнего набора '
             'данных, вручную не заполняется.')

    state = fields.Selection([
        ('draft', 'Черновик'),
        ('published', 'Опубликовано'),
        ('paused', 'Приостановлено'),
    ], string='Состояние', default='draft', required=True,
        tracking=True, index=True,
        help='Приостановленное предложение остаётся у владельца, но из '
             'каталога уходит: мастер занят, а не ушёл с платформы.')

    updated_display = fields.Char(
        string='Обновлено', compute='_compute_updated_display',
        help='Свежесть предложения. Мастер, обновлявший карточку на этой '
             'неделе, скорее всего ещё ищет заказ; запись годовой давности '
             'ничего не обещает.')
    partner_offer_count = fields.Integer(
        string='Ещё предложений у автора', compute='_compute_partner_offer_count')

    def _compute_updated_display(self):
        today = fields.Date.context_today(self)
        for record in self:
            if not record.write_date:
                record.updated_display = ''
                continue
            days = (today - record.write_date.date()).days
            if days <= 0:
                record.updated_display = 'Обновлено сегодня'
            elif days == 1:
                record.updated_display = 'Обновлено вчера'
            elif days < 30:
                record.updated_display = 'Обновлено %s %s назад' % (
                    days, _plural(days, 'день', 'дня', 'дней'))
            else:
                months = days // 30
                record.updated_display = 'Обновлено %s %s назад' % (
                    months, _plural(months, 'месяц', 'месяца', 'месяцев'))

    def _compute_partner_offer_count(self):
        counts = {
            partner.id: total
            for partner, total in self.sudo()._read_group(
                [('partner_id', 'in', self.partner_id.ids),
                 ('state', '=', 'published')],
                groupby=['partner_id'], aggregates=['__count'])
        } if self else {}
        for record in self:
            # За вычетом самого предложения: на карточке пишем «ещё N».
            record.partner_offer_count = max(
                0, counts.get(record.partner_id.id, 0) - 1)

    def action_partner_offers(self):
        """Другие предложения этого же человека."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Навыки: %s') % self.partner_id.display_name,
            'res_model': 'coop.skill.offer',
            'view_mode': 'kanban,list,form',
            'domain': [('partner_id', '=', self.partner_id.id),
                       ('state', '=', 'published')],
        }

    @api.depends('experience_months')
    def _compute_experience_display(self):
        for record in self:
            months = max(0, record.experience_months or 0)
            years, rest = divmod(months, 12)

            if not months:
                record.experience_display = 'Без опыта'
                record.experience_level = 'none'
                continue

            parts = []
            if years:
                parts.append('%s %s' % (years, _plural(
                    years, 'год', 'года', 'лет')))
            if rest:
                parts.append('%s %s' % (rest, _plural(
                    rest, 'месяц', 'месяца', 'месяцев')))
            record.experience_display = 'Опыт ' + ' '.join(parts)
            record.experience_level = 'senior' if years >= 3 else 'junior'

    @api.depends('rate', 'rate_kind', 'rate_period', 'currency_id')
    def _compute_rate_display(self):
        periods = {'month': 'в месяц', 'day': 'в день', 'hour': 'в час',
                   'job': 'за работу'}
        for record in self:
            # Три разных исхода, а не два. «Сдельно» — это выбор мастера;
            # незаполненная ставка — это незаполненная ставка, и выдавать
            # её за сдельную работу значит говорить за него.
            if record.rate_kind == 'piece':
                record.rate_display = 'сдельно, по договорённости'
                continue
            if not record.rate:
                record.rate_display = 'цена не указана'
                continue
            amount = '{:,.0f}'.format(record.rate).replace(',', ' ')
            symbol = record.currency_id.symbol or '₽'
            prefix = 'от ' if record.rate_kind == 'from' else ''
            period = periods.get(record.rate_period, '')
            record.rate_display = ('%s%s %s %s' % (prefix, amount, symbol, period)).strip()

    def action_publish(self):
        """Опубликовать предложение навыка.

        Нужна подтверждённая ступень контакта — телефон. Ниже неё
        участник только смотрит: неподтверждённая учётная запись стоит
        ноль минут, и каталог, в который можно писать с такой, наполняется
        не навыками.
        """
        for record in self:
            record.partner_id.coop_require_level(
                'contact', _('опубликовать предложение навыка'))
        self.write({'state': 'published'})
        return True

    def action_pause(self):
        self.write({'state': 'paused'})
        return True

    def action_message_owner(self):
        """Написать тому, кто предлагает навык."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Написать: %s') % self.partner_id.display_name,
            'res_model': 'discuss.channel',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_channel_partner_ids': [(4, self.partner_id.id)]},
        }


def _plural(number, one, few, many):
    """Русское склонение при числительном.

    Нужно потому, что «1 год», «2 года» и «5 лет» — три разные формы, и
    «3 год» на карточке выглядит как недоделанный интерфейс.
    """
    number = abs(number) % 100
    if 11 <= number <= 14:
        return many
    number %= 10
    if number == 1:
        return one
    if 2 <= number <= 4:
        return few
    return many
