# -*- coding: utf-8 -*-
from odoo import api, fields, models

# О чём извещать — те же виды, что у самих извещений. Отдельный
# перечень завёл бы второй список, который разошёлся бы с первым при
# первом же новом разделе.
KINDS = [
    ('vacancy', 'Вакансии'),
    ('auction', 'Торги'),
    ('deal', 'Сделки'),
    ('project', 'Проекты'),
    ('community', 'Сообщества'),
    ('resource', 'Ресурсы'),
    ('org', 'Организации'),
    ('wallet', 'Кошелёк'),
    ('other', 'Прочее'),
]


class CoopNotificationPref(models.Model):
    """О чём и куда сообщать — по видам событий.

    Строка на вид события, а не одно поле «слать или нет»: человеку
    важны ставки на его торгах и не важны новости сообществ, и общий
    выключатель заставил бы выбирать между всем и ничем.

    Каналов два: на платформе и почтой. Push из макета здесь нет — в
    платформе нет браузерных уведомлений, и переключатель без них
    обещал бы несуществующее.
    """

    _name = 'coop.notification.pref'
    _description = 'Настройка извещений'
    _order = 'partner_id, sequence, id'

    partner_id = fields.Many2one(
        'res.partner', string='Чья настройка', required=True, index=True,
        ondelete='cascade')
    kind = fields.Selection(KINDS, string='О чём', required=True)
    sequence = fields.Integer(
        string='Порядок', default=10,
        help='Тот же порядок, что в перечне видов: по алфавиту строки '
             'встают в порядке, который ничего не значит.')
    in_app = fields.Boolean(
        string='На платформе', default=True,
        help='Извещение в колокольчике.')
    by_email = fields.Boolean(
        string='Почтой', default=False,
        help='Письмо на адрес из карточки.')

    _kind_uniq = models.Constraint(
        'unique (partner_id, kind)',
        'У одного вида событий одна настройка на участника.')

    @api.model
    def _ensure_rows(self, partner):
        """Завести недостающие строки — по одной на вид события.

        Настройки заводятся при первом заходе на вкладку, а не всем
        участникам сразу: строк было бы девять на человека и три с
        половиной тысячи на узле, притом что большинство их никогда не
        откроет.
        """
        existing = set(self.sudo().search(
            [('partner_id', '=', partner.id)]).mapped('kind'))
        new_list = [{'partner_id': partner.id, 'kind': code,
                  'sequence': 10 * (number + 1)}
                 for number, (code, _) in enumerate(KINDS)
                 if code not in existing]
        if new_list:
            self.sudo().create(new_list)
        lines = self.sudo().search([('partner_id', '=', partner.id)])
        # Порядок приводится к перечню каждый раз: строки, заведённые
        # до появления поля, иначе остались бы в алфавитном беспорядке.
        sort_order = {code: 10 * (number + 1)
                   for number, (code, _) in enumerate(KINDS)}
        for line in lines:
            needed_one = sort_order.get(line.kind)
            if needed_one and line.sequence != needed_one:
                line.sequence = needed_one
        return lines

    @api.model
    def _allowed(self, partner, kind):
        """Куда сообщать этому человеку о событии такого вида.

        Пока человек ничего не настраивал, строк нет — и это значит
        умолчание: на платформе да, почтой нет. Заводить строки ради
        ответа на вопрос не нужно.
        """
        pref = self.sudo().search(
            [('partner_id', '=', partner.id), ('kind', '=', kind)], limit=1)
        if not pref:
            return True, False
        return pref.in_app, pref.by_email
