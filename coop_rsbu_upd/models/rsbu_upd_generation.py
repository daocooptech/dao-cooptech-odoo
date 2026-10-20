"""Ручное формирование документа реализации (и УПД) из инвойса Odoo.

Пользователь оформляет и проводит инвойс (account.move, out_invoice) —
РСБУ-слой формирует проводку реализации с зачётом авансов (резолвер
shipment_upd). Документ реализации (rsbu.realization), из которого затем
выгружается/печатается УПД, создаётся НЕ автоматически, а по кнопке
«Создать документ реализации» на форме инвойса.

Документ реализации создаётся для ЛЮБОЙ отгрузки — облагаемой НДС и
«Без НДС». При наличии НДС хотя бы в одной строке он порождает подчинённый
отгрузочный счёт-фактуру (rsbu.invoice, тип «shipment»).

Жизненный цикл закрывающего документа отражает поле closing_document на
инвойсе:
    not_done  — закрывающий документ не сформирован;
    issued    — документ реализации оформлен, ждём подпись клиента;
    signed    — клиент подписал (проставляется вручную).

При создании документа реализации статус переходит в «issued». При
удалении/отмене реализации — возвращается в «not_done» (хук на
rsbu.realization). В «signed» статус переводит только человек. Исходная
РСБУ-проводка инвойса при формировании УПД не меняется: реализация и СФ —
документы-надстройки, собственных проводок отгрузки не создают (их уже
сформировал резолвер при проведении).
"""
from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    closing_document = fields.Selection(
        selection=[
            ('not_done', 'Не сделан'),
            ('issued', 'Оформлен'),
            ('signed', 'Подписан'),
        ],
        string='Закрывающий документ', default='not_done', copy=False,
        tracking=True,
        help='Состояние закрывающего документа (УПД) по реализации: '
             '«Не сделан» — документ реализации не сформирован; '
             '«Оформлен» — создан, ждём подпись клиента; «Подписан» — '
             'клиент подписал (ставится вручную).')

    # Связанный документ реализации РСБУ (источник УПД).
    rsbu_realization_id = fields.Many2one(
        'rsbu.realization', string='Документ реализации (УПД)', copy=False,
        compute='_compute_rsbu_realization_id', store=False,
        help='Документ реализации РСБУ-слоя, сформированный по этому инвойсу '
             'для выгрузки/печати УПД.')

    def _compute_rsbu_realization_id(self):
        Realization = self.env['rsbu.realization'].sudo()
        for move in self:
            move.rsbu_realization_id = Realization.search([
                ('source_model', '=', 'account.move'),
                ('source_res_id', '=', move.id),
                ('state', '!=', 'cancelled'),
                ('company_id', '=', move.company_id.id),
            ], limit=1)

    # ------------------------------------------------------------------
    def _upd_can_create(self):
        """Можно ли сформировать документ реализации по этому инвойсу.

        Документ реализации формируется по любой проведённой реализации
        (out_invoice, с НДС и без), если он ещё не создан.
        """
        self.ensure_one()
        return bool(
            self.move_type == 'out_invoice'
            and self.state == 'posted'
            and not self.rsbu_realization_id
        )

    def action_create_realization(self):
        """Сформировать документ реализации (и УПД) по инвойсу.

        Всегда создаётся rsbu.realization; при наличии НДS хотя бы в одной
        строке — дополнительно порождается подчинённый отгрузочный СФ.
        """
        self.ensure_one()
        if self.move_type != 'out_invoice':
            raise UserError(_(
                'Документ реализации формируется только по счёту покупателю '
                '(реализация).'))
        if self.state != 'posted':
            raise UserError(_(
                'Проведите инвойс перед формированием документа реализации.'))
        if self.rsbu_realization_id:
            raise UserError(_(
                'По этому инвойсу уже сформирован документ реализации: %s.')
                % self.rsbu_realization_id.name)

        Realization = self.env['rsbu.realization'].sudo()
        realization = Realization.create({
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'date': self.invoice_date or self.date or fields.Date.today(),
            'source_model': 'account.move',
            'source_res_id': self.id,
            'amount_untaxed': abs(self.amount_untaxed),
            'amount_tax': abs(self.amount_tax),
            'state': 'confirmed',
        })
        if realization._has_vat(self):
            realization._create_shipment_invoice()
        self.closing_document = 'issued'
        # Связь rsbu_realization_id — non-stored computed; сбрасываем кэш,
        # чтобы кнопки/статус сразу отразили созданную реализацию.
        self.invalidate_recordset(['rsbu_realization_id'])
        return self._upd_open_realization(realization)

    def action_open_realization(self):
        """Открыть сформированный документ реализации (УПД)."""
        self.ensure_one()
        realization = self.rsbu_realization_id
        if not realization:
            raise UserError(_(
                'По этому инвойсу документ реализации ещё не сформирован.'))
        return self._upd_open_realization(realization)

    def _upd_open_realization(self, realization):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Документ реализации (УПД)'),
            'res_model': 'rsbu.realization',
            'view_mode': 'form',
            'res_id': realization.id,
            'target': 'current',
        }
