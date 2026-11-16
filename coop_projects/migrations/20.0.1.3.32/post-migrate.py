# -*- coding: utf-8 -*-
"""Лента новостей проекта — не рассылка (владелец 14.11.2026, № 446).

С этой версии записи стены проекта письмом не уходят
(`coop.project._notify_get_recipients`). Прежние попытки — первая
запись «123» в «Общественной библиотеке» с адресатом АНО «Мастерская
будущего» — остались ошибками доставки: красный значок на записи и
счётчик сбоев у автора. Письмом ни одна не ушла: снимаем
несостоявшиеся почтовые уведомления записей стен проектов.
"""


def migrate(cr, version):
    cr.execute("""
        DELETE FROM mail_notification n
         USING mail_message m
         WHERE m.id = n.mail_message_id
           AND m.model = 'coop.project'
           AND n.notification_type = 'email'
           AND n.notification_status IN ('exception', 'bounce', 'canceled')
    """)
