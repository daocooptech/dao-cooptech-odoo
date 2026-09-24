# -*- coding: utf-8 -*-
from odoo import fields, models


class IrAttachment(models.Model):
    """Фото на стене — картинкой или файлом.

    Владелец 24 сентября 2026: «как надо сделать, чтобы спрашивал:
    загрузить как файл или картинкой». Как в мессенджерах: картинка
    видна в записи миниатюрой, файл лежит карточкой, которую скачивают.

    Движок решает это сам по типу содержимого: всё, что `image/*`, —
    миниатюра. Выбор человека хранится здесь, на вложении, и уходит в
    браузер вместе с прочими его полями; показ правит `js/wall_photo.js`.
    """
    _inherit = "ir.attachment"

    coop_as_file = fields.Boolean(
        string="Файлом, а не картинкой",
        help="Снимок показывается в ленте карточкой для скачивания, "
             "а не миниатюрой.",
    )

    def _post_add_create(self, **kwargs):
        # Загрузка из поля ленты передаёт сюда всё, что прислал браузер
        # сверх самого файла (`/mail/attachment/upload`).
        super()._post_add_create(**kwargs)
        if kwargs.get("coop_as_file"):
            self.coop_as_file = True

    def _to_store_defaults(self, target):
        return super()._to_store_defaults(target) + ["coop_as_file"]
