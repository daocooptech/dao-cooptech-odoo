# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class CoopExtension(models.Model):
    """Расширение платформы в каталоге.

    Каталог расширений — это витрина над штатным списком приложений Odoo, а
    не его замена. Технически расширение остаётся обычным модулем: кнопка
    «Подключить» ставит именно его. Витрина нужна затем, что штатный список
    говорит на языке разработчика (технические имена, зависимости, версии),
    а кооператору нужно понимать, что он получит и во сколько это обойдётся.

    Отсюда два раздела: **установленные** — то, чем организация уже
    пользуется, и **общий каталог** — всё доступное, включая чужие
    расширения. Разработчик со стороны публикует своё расширение и сам
    назначает условия: бесплатно, помесячно, за год или единовременно
    навсегда.
    """
    _name = 'coop.extension'
    _description = 'Расширение платформы'
    _inherit = ['mail.thread']
    _order = 'sequence, name'

    name = fields.Char(string='Название', required=True, translate=True)
    sequence = fields.Integer(default=10)
    summary = fields.Char(
        string='Коротко', required=True, translate=True,
        help='Одна фраза о том, что расширение даёт участнику. '
             'Не «модуль учёта складских остатков», а «видно, сколько '
             'ресурса свободно, а сколько уже обещано по сделкам».')
    description = fields.Html(string='Описание', translate=True)

    category = fields.Selection([
        ('accounting', 'Учёт'),
        ('process', 'Процессы'),
        ('sales', 'Сбыт'),
        ('finance', 'Финансы'),
        ('community', 'Сообщество'),
        ('integration', 'Интеграции'),
    ], string='Раздел', required=True, default='process')

    # ── Кто автор ───────────────────────────────────────────────────────
    author_id = fields.Many2one(
        'res.partner', string='Автор',
        help='Кто опубликовал расширение. Своё оно или стороннее — видно по '
             'этому полю, а не по мелкому шрифту.')
    is_official = fields.Boolean(
        string='Расширение платформы', default=False,
        help='Сделано рабочей группой платформы. Стороннее расширение этим '
             'признаком не отмечается — участник должен понимать, у кого '
             'спрашивать, если что-то пошло не так.')

    # ── Связь с настоящим модулем Odoo ──────────────────────────────────
    module_name = fields.Char(
        string='Технический модуль',
        help='Имя модуля Odoo. Пусто — значит расширение ещё не готово к '
             'установке и показывается как заявленное.')
    module_id = fields.Many2one('ir.module.module', string='Модуль',
                                compute='_compute_module', store=True)
    module_state = fields.Selection(
        related='module_id.state', string='Состояние модуля', store=True)
    is_installed = fields.Boolean(
        string='Подключено', compute='_compute_module', store=True)

    # ── Условия ─────────────────────────────────────────────────────────
    #
    # Экономику назначает автор, а не платформа. Плата за расширение — это
    # отношения участника с его автором; платформа не становится стороной
    # этих отношений и не берёт долю по умолчанию.
    pricing = fields.Selection([
        ('free', 'Бесплатно'),
        ('month', 'Помесячно'),
        ('year', 'За год'),
        ('once', 'Единовременно, навсегда'),
    ], string='Условия', required=True, default='free')
    price = fields.Monetary(string='Цена', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        default=lambda self: self.env.company.currency_id)
    price_label = fields.Char(compute='_compute_price_label',
                              string='Стоимость')

    publication_state = fields.Selection([
        ('draft', 'Черновик'),
        ('review', 'На проверке'),
        ('published', 'В каталоге'),
        ('archived', 'Снято'),
    ], string='Публикация', default='draft', required=True, tracking=True)

    color = fields.Integer(string='Цвет')

    @api.depends('module_name')
    def _compute_module(self):
        modules = self.env['ir.module.module'].sudo()
        for record in self:
            module = modules.search([('name', '=', record.module_name)], limit=1) \
                if record.module_name else modules.browse()
            record.module_id = module
            record.is_installed = module.state == 'installed' if module else False

    @api.depends('pricing', 'price', 'currency_id')
    def _compute_price_label(self):
        suffix = {'month': ' в месяц', 'year': ' в год', 'once': ' навсегда'}
        for record in self:
            if record.pricing == 'free':
                record.price_label = 'Бесплатно'
            elif not record.price:
                record.price_label = 'Цена не указана'
            else:
                amount = '{:,.0f}'.format(record.price).replace(',', ' ')
                record.price_label = '%s %s%s' % (
                    amount, record.currency_id.symbol or '',
                    suffix.get(record.pricing, ''))

    def action_install(self):
        """Подключить расширение — то есть поставить настоящий модуль Odoo."""
        self.ensure_one()
        if not self.module_id:
            raise UserError(
                'Это расширение пока заявлено, но не готово к установке: '
                'технический модуль для него не указан.')
        self.module_id.sudo().button_immediate_install()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_open_module(self):
        self.ensure_one()
        if not self.module_id:
            raise UserError('У расширения нет технического модуля.')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ir.module.module',
            'res_id': self.module_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_publish(self):
        self.write({'publication_state': 'published'})

    def action_archive_listing(self):
        self.write({'publication_state': 'archived'})
