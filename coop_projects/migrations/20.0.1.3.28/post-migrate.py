# -*- coding: utf-8 -*-
"""Повтор 20.0.1.3.27: письмо из развёрнутого окна (15.11, до запрета) — тоже снять.

С этой версии посты проекта подписчикам письмом не уходят
(`project.project._notify_get_recipients`). Старые попытки рассылки у
людей без почты остались в базе ошибками доставки — красный значок на
посте и счётчик сбоев у автора. Письмом ни одно из них не ушло:
снимаем несостоявшиеся почтовые уведомления постов проектов.
"""


def migrate(cr, version):
    cr.execute("""
        DELETE FROM mail_notification n
         USING mail_message m
         WHERE m.id = n.mail_message_id
           AND m.model = 'project.project'
           AND n.notification_type = 'email'
           AND n.notification_status IN ('exception', 'bounce', 'canceled')
    """)
