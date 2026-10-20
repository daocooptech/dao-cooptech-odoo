from odoo import models


class RsbuAccount(models.Model):
    """Расширение плана счетов: наполнение хука агрегации данными журнала."""
    _inherit = 'rsbu.account'

    def _read_postings(self, domain=None):
        """Прочитать проведённые строки журнала для агрегации.

        Переопределяет заглушку Этапа 1. Возвращает строки rsbu.move.line
        по поддереву счёта, только проведённые (state='posted'), с учётом
        дополнительного domain (период/компания) из вызывающего метода.
        """
        self.ensure_one()
        base_domain = [
            ('account_id', 'in', self._get_subtree_account_ids()),
            ('state', '=', 'posted'),
        ]
        if domain:
            # Отфильтровать по period/company — поля есть на строке (related).
            base_domain += domain
        return self.env['rsbu.move.line'].search(base_domain)
