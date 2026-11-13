# -*- coding: utf-8 -*-
"""Фото и видео организации — слайдер на карточке (задача 444).

Обложка (`image_1920`) у организации стоит отдельно, в левой колонке,
поэтому в слайдер она не попадает: там цеха, склады, люди за работой.
"""
from odoo import models


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner', 'coop.media.mixin']

    def _coop_media_photos(self):
        return []

    def coop_media_add(self, kind, data=None, url=None, name=None, mimetype=None):
        """Фото — всегда в ленту, а не на обложку."""
        self.ensure_one()
        if kind == 'photo':
            self.check_access('write')
            if not data:
                return super().coop_media_add(kind, data=data, name=name)
            return self._coop_media_add_photo(data, name)
        return super().coop_media_add(kind, data=data, url=url, name=name, mimetype=mimetype)
