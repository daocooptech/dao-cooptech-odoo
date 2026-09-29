# -*- coding: utf-8 -*-
"""Заявка «Написать нам» с лендинга (решение 438, п. 11: «Форма на сайте»).

Кто хочет свой сервер в сети или стать партнёром-оператором, пишет рабочей
группе. Заявка приходит в платформу, а не на почту: рабочая группа видит
её в разделе «Заявки с сайта» и отвечает оттуда. Администраторы
подписаны на каждую заявку и получают уведомление во «Входящих».
"""
from odoo import api, fields, models

TOPICS = [
    ('node', 'Свой сервер в сети'),
    ('partner', 'Партнёр-оператор'),
    ('org', 'Подключить организацию'),
    ('other', 'Другое'),
]


class CoopContactRequest(models.Model):
    _name = 'coop.contact.request'
    _description = 'Заявка с сайта'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Как обращаться', required=True)
    email = fields.Char(string='Почта или телефон', required=True)
    organization = fields.Char(string='Организация')
    topic = fields.Selection(TOPICS, string='Тема', default='other', required=True)
    message = fields.Text(string='Сообщение', required=True)
    state = fields.Selection([('new', 'Новая'), ('answered', 'Отвечено'), ('closed', 'Закрыта')],
                             string='Состояние', default='new', required=True, tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        admins = self.env.ref('base.group_system').sudo().all_user_ids.partner_id
        for record in records:
            record.message_subscribe(partner_ids=admins.ids)
            record.message_post(
                body='Новая заявка с сайта: %s — %s' % (
                    dict(TOPICS).get(record.topic), record.name),
                message_type='notification', subtype_xmlid='mail.mt_comment')
        return records
