# -*- coding: utf-8 -*-
"""Документ с проверяемым отпечатком.

Решение 382 от 22 сентября 2026. Владелец выбрал делать документы
**без записи в цепь блоков**, отдельным разделом меню сразу после
«Управления проектами».

Отпечаток — SHA-256 содержимого файла. Этого достаточно, чтобы ответить
на вопрос, ради которого всё затевалось: **тот ли это документ**. Человек
берёт свой экземпляр, платформа считает его отпечаток и сравнивает.
Совпал — файл не подменён. Разошёлся — перед вами другой файл, и спорить
не о чем.

Цепь блоков добавляет к этому одно: доказательство, что отпечаток
существовал **до** какой-то даты. Это ценно, но упирается в выбор сети и
плату за запись, и держать из-за неё весь раздел незачем.

Отдельным разделом, а не вкладкой сделки: документы нужны сразу
нескольким разделам — сделкам, закупкам, проектам, членству. Спрятанные
во вкладку одного из них, они станут недоступны остальным и появятся там
второй раз.
"""
import base64
import hashlib

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopDocument(models.Model):
    _name = 'coop.document'
    _description = 'Документ'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'coop.page.mixin']
    _order = 'signed_on desc, id desc'

    name = fields.Char(string='Название', required=True, tracking=True)
    kind = fields.Selection([
        ('contract', 'Договор'),
        ('act', 'Акт приёма-передачи'),
        ('closing', 'Закрывающий документ'),
        ('protocol', 'Протокол'),
        ('other', 'Прочее'),
    ], string='Вид', default='act', required=True, index=True, tracking=True)

    # Стороны. Их две, потому что документ — это всегда договорённость
    # между кем-то и кем-то; третьи лица попадают в подписанты.
    party_a_id = fields.Many2one(
        'res.partner', string='Сторона', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner(),
        tracking=True)
    party_b_id = fields.Many2one(
        'res.partner', string='Вторая сторона', index=True, tracking=True)

    signed_on = fields.Date(string='Дата', default=fields.Date.context_today,
                            index=True, tracking=True)
    number = fields.Char(string='Номер', tracking=True)

    # К чему относится. Пара «модель и номер», а не связь: документы
    # приходят о записях из полутора десятков моделей, и заводить под
    # каждую своё поле значило бы переписывать модель при появлении
    # шестнадцатой.
    res_model = fields.Char(string='Модель записи', index=True)
    res_id = fields.Integer(string='Номер записи')
    res_label = fields.Char(string='К чему относится')

    folder_id = fields.Many2one(
        'coop.document.folder', string='Папка', index=True,
        ondelete='set null',
        help='Ваш порядок. Папка личная: один и тот же документ вы и '
             'вторая сторона держите у себя по-разному.')

    # Год отдельным полем — для группировки и отбора. Считать его от даты
    # на лету нельзя: группировать и искать движок умеет только по
    # хранимому, а «документы за 2024» спрашивают чаще всего.
    year = fields.Integer(
        string='Год', compute='_compute_year', store=True, index=True)

    file = fields.Binary(string='Файл', attachment=True)
    file_name = fields.Char(string='Имя файла')

    fingerprint = fields.Char(
        string='Отпечаток', compute='_compute_fingerprint', store=True,
        index=True, copy=False,
        help='SHA-256 содержимого. По нему сверяют, тот ли это документ.')

    state = fields.Selection([
        ('draft', 'Черновик'),
        ('signed', 'Подписан'),
        ('cancelled', 'Отменён'),
    ], string='Состояние', default='draft', required=True, index=True,
        tracking=True)

    note = fields.Text(string='Пояснение')

    @api.depends('signed_on')
    def _compute_year(self):
        for record in self:
            record.year = record.signed_on.year if record.signed_on else 0

    @api.depends('file')
    def _compute_fingerprint(self):
        """Отпечаток считается от самого содержимого.

        Не от имени файла и не от записи: переименуют файл — отпечаток
        обязан остаться прежним, подменят содержимое — обязан
        измениться. В этом весь смысл.
        """
        for record in self:
            record.fingerprint = self._fingerprint_of(record.file)

    @api.model
    def _fingerprint_of(self, value):
        """SHA-256 от двоичного содержимого, как его хранит движок.

        Файл приходит закодированным в base64 — сначала раскодируем.
        Считать отпечаток от закодированного вида было бы ошибкой,
        которую не видно: он тоже стабилен, но не совпадёт ни с одним
        отпечатком, посчитанным снаружи платформы.
        """
        if not value:
            return False
        raw = value
        if isinstance(raw, str):
            raw = raw.encode('ascii', errors='ignore')
        try:
            content = base64.b64decode(raw)
        except Exception:
            content = raw
        return hashlib.sha256(content).hexdigest()

    def action_sign(self):
        """Отметить документ подписанным.

        Файл обязателен: подписывать нечего, если документа нет. Это не
        придирка — запись «подписан» без файла потом невозможно ни
        проверить, ни оспорить.
        """
        for record in self:
            if not record.file:
                raise UserError(_(
                    'Сначала приложите файл: подписывать нечего.'))
            record.state = 'signed'
            record.message_post(body=_(
                'Документ подписан. Отпечаток: %s', record.fingerprint))
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    def action_check(self):
        """Открыть сверку: человек грузит свой экземпляр."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Сверить свой экземпляр'),
            'res_model': 'coop.document.check',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_document_id': self.id},
        }
