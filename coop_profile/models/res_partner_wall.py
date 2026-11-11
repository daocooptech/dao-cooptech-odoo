# -*- coding: utf-8 -*-
"""Лента на странице человека и организации: пишет только хозяин.

Владелец 11.11.2026 (решение 653): «нельзя, убрать поле» — гостю писать в
ленту на чужой странице нельзя, «и на сервере». Поле публикации гостю не
показывается (`coop_theme/static/src/js/wall.js`), а здесь — тот же запрет
для запроса в обход страницы: без него запись на чужую стену проходила
через API.

Своя стена — та же, что даёт право править карточку
(`coop_site_partner_ids`): своя страница и страницы организаций, на
которые у человека есть полномочие. Запрещены только записи людей
(`comment`): служебные извещения движка и записи от имени платформы
(`sudo`) ложатся в ленту как прежде.
"""
from odoo import _, models
from odoo.exceptions import AccessError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def message_post(self, **kwargs):
        if kwargs.get('message_type') == 'comment' and not self.env.su:
            mine = self.env.user.coop_site_partner_ids
            if any(record not in mine for record in self):
                raise AccessError(_(
                    'Писать в ленту на чужой странице нельзя. Чтобы '
                    'связаться с участником, нажмите «Написать».'))
        return super().message_post(**kwargs)
