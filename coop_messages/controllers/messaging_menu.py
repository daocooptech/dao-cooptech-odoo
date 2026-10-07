# -*- coding: utf-8 -*-
"""Вкладки меню сообщений: «Личные», «Групповые», «Служебные» (НВ19).

В 19 вкладки делились на клиенте (`Store.tabToThreadType`,
`MessagingMenu.threads`). В 20 состав вкладки задаёт сервер — домен по её
`id` здесь, а клиент (`includesChannel` в `coop_messages.js`) повторяет
тот же признак для живых обновлений. Оба места должны говорить одно.

- «Личные» (`chat`) — разговор один на один;
- «Групповые» (`channel`) — группы и каналы: владелец 16.09.2026 — «если
  каналы это обычные групповые чаты, то надо так и написать»;
- «Служебные» (`coop_service`) — переписки с самой платформой; из двух
  других вкладок убраны (решение 16.09.2026, НВ19 — 07.10.2026).
"""
from odoo.fields import Domain

from odoo.addons.mail.controllers.discuss.messaging_menu import DiscussMessagingMenuController

NOT_SERVICE = Domain('coop_kind', '!=', 'service') | Domain('coop_kind', '=', False)
NOT_VIDEO = Domain('default_display_mode', '!=', 'video_full_screen')


class CoopMessagingMenuController(DiscussMessagingMenuController):

    def _get_menu_tab_domain(self, tab_id):
        match tab_id:
            case 'chat':
                return (Domain('channel_type', '=', 'chat') & NOT_VIDEO
                        & Domain('self_member_id.is_pinned', '=', True) & NOT_SERVICE)
            case 'channel':
                pinned = Domain('self_member_id.is_pinned', '=', True)
                if self.env.user._is_internal():
                    pinned |= Domain('message_needaction', '=', True)
                return (Domain('channel_type', 'in', ['channel', 'group']) & NOT_VIDEO
                        & pinned & NOT_SERVICE)
            case 'coop_service':
                return (Domain('coop_kind', '=', 'service')
                        & Domain('self_member_id', '!=', False))
            case _:
                return super()._get_menu_tab_domain(tab_id)

    def _get_menu_tab_filter_domain(self, tab_id, filter_id):
        if (tab_id, filter_id) == ('coop_service', 'coop_service_unread'):
            return Domain('self_member_id.is_unread', '=', True)
        return super()._get_menu_tab_filter_domain(tab_id, filter_id)
