from odoo import api, models


class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    @api.model
    def _rsbu_next_for_company(self, xmlid, company, date=None):
        """Следующий номер документа РСБУ-слоя — своя нумерация у компании.

        У выпуска последовательности слоя заведены без компании: номера
        операций, счетов-фактур и реализаций шли бы сквозь весь пул.
        Последовательность компании заводится копией общей при первом
        номере.
        """
        template = self.env.ref(xmlid).sudo()
        sequence = self.sudo().search([
            ('code', '=', template.code),
            ('company_id', '=', company.id),
        ], limit=1)
        if not sequence:
            sequence = template.copy({
                'company_id': company.id,
                'number_next': 1,
            })
        return sequence.next_by_id(sequence_date=date)
