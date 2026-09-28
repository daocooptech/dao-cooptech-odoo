# -*- coding: utf-8 -*-
from odoo import fields, models


class CoopFedKey(models.Model):
    """Открытые ключи — свои и соседей. Секрет своего рабочего ключа лежит
    в файле (`secret_path`), в базе его нет. У резервного ключа пути нет:
    его секрет хранится вне сервера у человека."""
    _name = 'coop.fed.key'
    _description = 'Ключ узла сети'
    _order = 'owner_did, not_before'

    identity_id = fields.Many2one('coop.fed.identity', string='Наш узел', ondelete='cascade')
    kid = fields.Char('Ключ', required=True, readonly=True)
    owner_did = fields.Char('Чей', required=True, readonly=True, index=True)
    public_key = fields.Char('Открытый ключ (base64url)', required=True, readonly=True)
    purpose = fields.Selection([('working', 'Рабочий'), ('recovery', 'Резервный')],
                               string='Назначение', default='working', required=True)
    not_before = fields.Char('Действует с', readonly=True)
    revoked_at = fields.Char('Отозван с (плановая смена)', readonly=True)
    compromised_at = fields.Char('Украден с', readonly=True)
    secret_path = fields.Char('Файл секрета', readonly=True, groups='base.group_system')

    _kid_uniq = models.Constraint('unique(kid)', 'Ключ с таким идентификатором уже есть.')
