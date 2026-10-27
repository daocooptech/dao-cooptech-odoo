# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Решение 374: что показывать из подключённых систем, решает владелец
    # данных, по каждому блоку. Техпроцесс для многих — коммерческая тайна,
    # поэтому по умолчанию скрыт: прозрачность — предложение, а не условие.
    coop_show_process = fields.Boolean(
        string='Показывать техпроцесс',
        help='Этапы и операции техкарты и последняя партия видны на '
             'карточках ресурсов организации.')

    def write(self, vals):
        # Как приложения организации: показ включает руководитель, а права
        # на запись карточки у него может не быть (её правит держатель
        # «Страницы») — после проверки «Подписи» пишется от имени системы.
        if 'coop_show_process' in vals and not self.env.su \
                and not self.env.user.has_group('base.group_system'):
            for org in self:
                if not self.env.user.coop_has_power('sign', org):
                    raise UserError(_(
                        'Показ техпроцесса организации «%s» включает и '
                        'выключает руководитель.') % org.display_name)
            super(ResPartner, self.sudo()).write(
                {'coop_show_process': vals['coop_show_process']})
            vals = {k: v for k, v in vals.items() if k != 'coop_show_process'}
            if not vals:
                return True
        return super().write(vals)
