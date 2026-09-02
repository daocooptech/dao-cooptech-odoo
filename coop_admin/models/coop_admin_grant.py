# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class CoopAdminGrant(models.Model):
    """Решение о выдаче административных полномочий.

    Полномочия выдаются голосованием команды, а не проставляются галочкой
    в карточке пользователя. Поэтому здесь запись о решении: кому, когда,
    кто голосовал, с каким итогом и на каком основании. Отзыв —
    такое же решение, а не удаление записи: история того, кто и когда
    получал всевластие, должна остаться.
    """

    _name = 'coop.admin.grant'
    _description = 'Полномочия администратора'
    _inherit = ['mail.thread']
    _order = 'decided_on desc, id desc'

    partner_id = fields.Many2one(
        'res.partner', string='Кому', required=True, index=True,
        tracking=True, domain=[('is_company', '=', False)])
    user_id = fields.Many2one(
        'res.users', string='Учётная запись', compute='_compute_user_id',
        store=True, index=True,
        help='Полномочия получает человек; действуют они через его '
             'учётную запись. Без записи включать нечего.')

    state = fields.Selection([
        ('proposed', 'Вынесено на голосование'),
        ('granted', 'Выданы'),
        ('rejected', 'Отклонено'),
        ('revoked', 'Отозваны'),
    ], string='Состояние', required=True, default='proposed', index=True,
        tracking=True)

    basis = fields.Text(
        string='Основание', required=True, tracking=True,
        help='Зачем полномочия выдаются. Голосование без внятного повода '
             'через полгода нельзя ни проверить, ни оспорить.')

    voter_ids = fields.Many2many(
        'res.partner', 'coop_admin_grant_voter_rel', 'grant_id', 'partner_id',
        string='Голосовали', help='Состав команды на момент голосования.')
    votes_for = fields.Integer(string='За', tracking=True)
    votes_against = fields.Integer(string='Против', tracking=True)

    decided_on = fields.Date(string='Дата решения', tracking=True)
    revoked_on = fields.Date(string='Дата отзыва', tracking=True)

    # Голосование переезжает в блокчейн; поле заведено сразу, чтобы не
    # добавлять его к уже разошедшимся по узлам решениям.
    chain_network_id = fields.Many2one(
        'coop.wallet.network', string='Сеть', ondelete='set null')
    chain_tx = fields.Char(
        string='Транзакция', help='Пусто, пока голосование ведётся на '
                                  'платформе, а не в сети.')

    @api.depends('partner_id')
    def _compute_user_id(self):
        for record in self:
            record.user_id = self.env['res.users'].sudo().search(
                [('partner_id', '=', record.partner_id.id)], limit=1)

    @api.constrains('state', 'user_id')
    def _check_user_exists(self):
        for record in self:
            if record.state == 'granted' and not record.user_id:
                raise ValidationError(_(
                    'У «%s» нет учётной записи — включать полномочия '
                    'некому.') % record.partner_id.display_name)

    def action_grant(self):
        """Признать голосование состоявшимся и выдать полномочия."""
        for record in self:
            if record.votes_for <= record.votes_against:
                raise UserError(_(
                    'Голосов «за» не больше, чем «против»: %s против %s. '
                    'Полномочия так не выдаются.')
                    % (record.votes_for, record.votes_against))
            # Прежние полномочия того же человека закрываются: два
            # действующих решения об одном и том же — это спор о том,
            # какое из них считать.
            record.search([
                ('partner_id', '=', record.partner_id.id),
                ('state', '=', 'granted'),
                ('id', '!=', record.id),
            ]).write({'state': 'revoked',
                      'revoked_on': fields.Date.context_today(record)})
            record.write({
                'state': 'granted',
                'decided_on': record.decided_on or fields.Date.context_today(record),
            })
            record.user_id.sudo()._coop_sync_admin_grant()
        return True

    def action_revoke(self):
        for record in self:
            record.write({
                'state': 'revoked',
                'revoked_on': fields.Date.context_today(record),
            })
            # Отзыв гасит и включённый режим: иначе человек до конца
            # сеанса продолжает ходить с полномочиями, которых у него уже
            # нет.
            record.user_id.sudo().write({'coop_admin_active': False})
            record.user_id.sudo()._coop_sync_admin_grant()
        return True

    def action_reject(self):
        for record in self:
            record.state = 'rejected'
        return True
