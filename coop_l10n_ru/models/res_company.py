import logging

from psycopg2 import sql

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    company_registry = fields.Char(related='partner_id.coop_ogrn', readonly=False)

    @api.model
    def _coop_platform_rub(self):
        """Валюта площадки — рубль.

        Компания платформы осталась с валютой Odoo по умолчанию — долларом,
        и от неё доллар достался каждой записи площадки, где валюту не
        задали явно: сделкам, ресурсам, кошелькам, паям — при том что
        суммы в них рублёвые. На экранах и дашбордах стоял «$» (замер
        07.10.2026: 27 таблиц, во всех только USD или только RUB — смешанных
        нет, то есть доллар нигде не настоящий).

        Суммы не пересчитываются: они и были в рублях, неверной была только
        ссылка на валюту. Повторный прогон ничего не делает. Если у
        компании платформы появятся проводки, валюту меняет бухгалтер, а не
        этот шаг.
        """
        rub = self.env.ref('base.RUB')
        usd = self.env.ref('base.USD', raise_if_not_found=False)
        company = self.env.ref('base.main_company', raise_if_not_found=False)
        if not company or not usd:
            return
        rub.sudo().active = True
        if company.currency_id != rub:
            if 'account.move.line' in self.env and self.env['account.move.line'].sudo().search_count(
                    [('company_id', '=', company.id)], limit=1):
                _logger.warning('Валюта платформы: у компании есть проводки, оставляю как есть')
                return
            company.sudo().currency_id = rub
            if 'product.pricelist' in self.env:
                self.env['product.pricelist'].sudo().search([
                    ('currency_id', '=', usd.id),
                    ('company_id', 'in', (company.id, False)),
                ]).write({'currency_id': rub.id})
        cr = self.env.cr
        cr.execute("""
            SELECT c.table_name FROM information_schema.columns c
              JOIN information_schema.tables t
                ON t.table_name = c.table_name AND t.table_schema = c.table_schema
             WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
               AND c.column_name = 'currency_id' AND c.table_name LIKE 'coop\_%%'
        """)
        changed = 0
        for (table,) in cr.fetchall():
            cr.execute(sql.SQL('UPDATE {} SET currency_id = %s WHERE currency_id = %s').format(
                sql.Identifier(table)), (rub.id, usd.id))
            changed += cr.rowcount
        if changed:
            self.env.invalidate_all()
            _logger.info('Валюта платформы: ссылок на доллар переведено на рубль — %s', changed)
