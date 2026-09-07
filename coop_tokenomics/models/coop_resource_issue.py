# -*- coding: utf-8 -*-
"""Выпуск токена требования прямо в объявлении.

Решение владельца: «выпуск — пунктом в конце формы публикации
объявления, галочкой». Отдельный экран выпуска остаётся для правки и
разбора, но заводить обещание участник должен там же, где размещает
сам ресурс: он один раз описывает, что везёт, а не дважды — сперва в
объявлении, потом в бирже.

Четыре признака обязательны, потому что без них обещание не товар, а
намерение: сколько, какого качества, куда и к какому сроку. Пятое —
цена, шестое — залог, который считается сам и вносится при размещении.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopResource(models.Model):
    _inherit = 'coop.resource'

    coop_token_issue = fields.Boolean(
        string='Выпустить токен на биржу',
        help='Обещание поставить этот ресурс к сроку станет торгуемым: '
             'покупатель платит вперёд, деньги ждут поставки, а до срока '
             'обещание можно перепродать.')

    coop_token_claim_id = fields.Many2one(
        'coop.token.claim', string='Выпуск', readonly=True, copy=False,
        help='Заполняется при публикации, если стоит галочка.')

    # Заготовки признаков выпуска. Держим их на объявлении, а не создаём
    # выпуск сразу: черновик объявления правят по многу раз, и каждая
    # правка порождала бы запись на бирже, которой там ещё не место.
    coop_token_quantity = fields.Float(
        string='Сколько поставите', digits=(16, 3),
        help='Столько токенов и будет выпущено: один токен — одна единица.')
    coop_token_unit = fields.Char(string='Единица', default='кг')
    coop_token_quality = fields.Char(
        string='Качество',
        help='ГОСТ, сорт, класс, влажность — то, по чему приёмка отличит '
             'исполненное обещание от неисполненного.')
    coop_token_place = fields.Char(
        string='Место передачи',
        help='Куда покупателю приезжать. «Самовывоз» без адреса — это не '
             'место.')
    coop_token_date = fields.Date(string='Срок поставки')
    coop_token_price = fields.Float(
        string='Цена за единицу', digits=(16, 4),
        help='В рублях. Цена выпуска фиксированная; дальше её меняет '
             'вторичный рынок.')

    coop_token_total = fields.Float(
        string='Стоимость выпуска', compute='_compute_coop_token_amounts',
        digits=(16, 2))
    coop_token_deposit = fields.Float(
        string='Залог к внесению', compute='_compute_coop_token_amounts',
        digits=(16, 2),
        help='Десять процентов от суммы выпуска, но не меньше стоимости '
             'самого выпуска. Вносится при размещении и возвращается '
             'после поставки; при срыве уходит держателям.')

    @api.depends('coop_token_quantity', 'coop_token_price')
    def _compute_coop_token_amounts(self):
        Claim = self.env['coop.token.claim']
        mint_cost = Claim._default_mint_cost()
        for record in self:
            total = (record.coop_token_quantity or 0.0) * (record.coop_token_price or 0.0)
            record.coop_token_total = total
            record.coop_token_deposit = max(total * 0.10, mint_cost) if total else 0.0

    def _check_token_fields(self):
        """Проверить, что обещание описано полностью.

        Ошибка одна на все незаполненные признаки: перечислить сразу
        всё, чего не хватает, честнее, чем гонять человека по кругу —
        заполнил одно, узнал про второе.
        """
        self.ensure_one()
        missing = []
        if not self.coop_token_quantity:
            missing.append(_('сколько поставите'))
        if not (self.coop_token_unit or '').strip():
            missing.append(_('единица измерения'))
        if not (self.coop_token_quality or '').strip():
            missing.append(_('качество'))
        if not (self.coop_token_place or '').strip():
            missing.append(_('место передачи'))
        if not self.coop_token_date:
            missing.append(_('срок поставки'))
        if not self.coop_token_price:
            missing.append(_('цена за единицу'))
        if missing:
            raise UserError(_(
                'Чтобы выпустить токен, опишите обещание целиком. Не '
                'хватает: %(fields)s.\n\nБез этих признаков обещание нельзя '
                'ни принять, ни оспорить: покупатель должен знать, что '
                'именно, какого качества, куда и к какому сроку он купил.',
                fields=', '.join(missing)))
        if self.coop_token_date <= fields.Date.context_today(self):
            raise UserError(_(
                'Срок поставки должен быть в будущем: обещание на сегодня '
                'или вчера торговать нечем.'))

    def action_publish(self):
        """Опубликовать объявление и, если попросили, выпустить токен."""
        result = super().action_publish()
        for record in self:
            if not record.coop_token_issue or record.coop_token_claim_id:
                continue
            record._check_token_fields()
            record.coop_token_claim_id = record._create_token_claim()
        return result

    def _create_token_claim(self):
        """Завести выпуск на бирже по признакам из объявления."""
        self.ensure_one()
        return self.env['coop.token.claim'].create({
            'resource_id': self.id,
            'issuer_id': self.owner_id.id,
            'quantity': self.coop_token_quantity,
            'unit_label': self.coop_token_unit,
            'quality': self.coop_token_quality,
            'delivery_place': self.coop_token_place,
            'delivery_date': self.coop_token_date,
            'price_per_unit': self.coop_token_price,
            'settlement_currency': 'rub',
            # Товара ещё нет — в этом и смысл: фермер весной продаёт
            # осенний урожай. Обратное участник отметит сам в карточке
            # выпуска, если поставляет со склада.
            'is_future': True,
        })

    def action_open_token_claim(self):
        """Открыть карточку выпуска — из объявления одним щелчком."""
        self.ensure_one()
        if not self.coop_token_claim_id:
            raise UserError(_('По этому объявлению токен не выпускался.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'coop.token.claim',
            'res_id': self.coop_token_claim_id.id,
            'views': [[False, 'form']],
        }
