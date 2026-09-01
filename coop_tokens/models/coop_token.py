# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopTokenTransaction(models.Model):
    """Движение внутренних токенов платформы.

    Токен — внутренняя расчётная единица платформы, и границы у неё узкие
    намеренно. Ими оплачиваются услуги самой платформы (пока — продвижение
    объявления в каталоге), и только это.

    Чем токен здесь **не** является и почему:

    - не средство расчёта между участниками. Рассчитываться собственной
      единицей за товары и услуги нельзя: введение денежных суррогатов на
      территории России запрещено (ст. 75 Конституции, ст. 27 ФЗ от
      10.07.2002 № 86-ФЗ). Поэтому перевода токенов от участника к
      участнику здесь нет — и появиться он не должен;
    - не обменивается обратно на деньги. Обратный выкуп превратил бы токен
      в средство платежа и потребовал бы совсем другого регулирования;
    - не цифровая валюта и не ЦФА по 259-ФЗ: токен не удостоверяет прав
      требования и не обращается вне платформы.

    Что он есть: предоплаченная единица услуги платформы плюс механизм
    поощрения. Пополнить баланс можно рублями (аванс за услугу) или
    получить начислением за вклад в общее дело — второе решает владелец,
    правила начисления согласуются отдельно.

    Хранятся движения, а не остаток. Остаток считается как их сумма:
    иначе первое же расхождение между «сколько было» и «откуда взялось»
    станет неразрешимым — по остатку нельзя восстановить историю, по
    истории остаток восстанавливается всегда.
    """
    _name = 'coop.token.transaction'
    _description = 'Движение токенов'
    _order = 'create_date desc, id desc'

    partner_id = fields.Many2one(
        'res.partner', string='Участник', required=True,
        ondelete='cascade', index=True)
    amount = fields.Integer(
        string='Токенов', required=True,
        help='Положительное — начисление, отрицательное — списание.')
    kind = fields.Selection([
        ('topup', 'Пополнение'),
        ('grant', 'Начисление за вклад'),
        ('promotion', 'Оплата продвижения'),
        ('refund', 'Возврат'),
        ('correction', 'Корректировка'),
    ], string='Основание', required=True, index=True)
    description = fields.Char(string='Пояснение')

    # Ссылка на то, за что списано. Без неё через месяц никто не скажет,
    # какое именно объявление продвигали за эти токены.
    res_model = fields.Char(string='Модель объекта')
    res_id = fields.Integer(string='Объект')

    _sql_constraints = [
        ('amount_not_zero', 'check(amount != 0)',
         'Движение на ноль токенов не имеет смысла.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.partner_id._compute_coop_token_balance()
        return records


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_token_ids = fields.One2many(
        'coop.token.transaction', 'partner_id', string='Движения токенов')
    coop_token_balance = fields.Integer(
        string='Токенов на балансе', compute='_compute_coop_token_balance',
        store=True, help='Сумма всех начислений и списаний.')

    @api.depends('coop_token_ids.amount')
    def _compute_coop_token_balance(self):
        totals = {
            partner.id: total
            for partner, total in self.env['coop.token.transaction'].sudo()._read_group(
                [('partner_id', 'in', self.ids)],
                groupby=['partner_id'], aggregates=['amount:sum'])
        } if self.ids else {}
        for record in self:
            record.coop_token_balance = totals.get(record.id, 0)

    def coop_token_spend(self, amount, kind, description=None, record=None):
        """Списать токены. Возвращает созданное движение.

        Проверка баланса здесь, а не в вызывающем коде: списание в минус
        означало бы, что платформа оказала услугу в долг, а правил
        задолженности у нас нет и заводить их незачем.
        """
        self.ensure_one()
        amount = abs(int(amount))
        if self.coop_token_balance < amount:
            raise UserError(_(
                'Не хватает токенов: нужно %(need)s, на балансе %(have)s.',
                need=amount, have=self.coop_token_balance))
        values = {
            'partner_id': self.id,
            'amount': -amount,
            'kind': kind,
            'description': description,
        }
        if record is not None:
            values.update({'res_model': record._name, 'res_id': record.id})
        return self.env['coop.token.transaction'].sudo().create(values)
