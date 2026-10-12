import json
import logging

import requests

from odoo import api, fields, models
from odoo.modules.module import get_module_path

_logger = logging.getLogger(__name__)

# Поиск адресов OpenStreetMap. Условия сервиса: не чаще запроса в секунду
# и честная подпись в User-Agent. Объявления сохраняют редко, и ни того,
# ни другого здесь не нарушить.
NOMINATIM = 'https://nominatim.openstreetmap.org/search'
USER_AGENT = 'cooptech-platform/1.0 (https://daocoop.tech)'

# Места, у которых нет адреса по определению.
NO_PLACE = {'Удалённо'}


class CoopGeoMixin(models.AbstractModel):
    """Адрес объявления и его точка на карте.

    Город у объявления был и остаётся: по нему отбирают. Адрес — улица и
    дом — уточняет, куда ехать, и ставит объявление точкой на карте
    каталога, как у досок объявлений, где ищут рядом с собой.
    """
    _name = 'coop.geo.mixin'
    _description = 'Адрес и точка на карте'

    coop_address = fields.Char(
        string='Адрес',
        help='Улица и дом. По адресу объявление встаёт точкой на карте; '
             'пусто — на карте его нет, только в списке и плиткой.')
    coop_lat = fields.Float(string='Широта', digits=(10, 6), copy=False)
    coop_lon = fields.Float(string='Долгота', digits=(10, 6), copy=False)

    # ── Координаты по адресу ─────────────────────────────────────────

    def _coop_geo_offline(self):
        """Без запросов наружу: автотесты и загрузка демо-данных."""
        if self.env.context.get('coop_geo_offline'):
            return True
        in_test = getattr(self.env.registry, 'in_test_mode', None)
        return bool(in_test and in_test())

    @api.model
    def _coop_geocode(self, address, city):
        """Широта и долгота адреса или `None`, если найти не удалось.

        Ошибка сети или пустой ответ не мешают сохранить объявление: оно
        просто останется без точки на карте.
        """
        if not address or not city or city in NO_PLACE or self._coop_geo_offline():
            return None
        try:
            response = requests.get(NOMINATIM, params={
                'q': f'{address}, {city}',
                'format': 'json',
                'limit': 1,
                'accept-language': 'ru',
            }, headers={'User-Agent': USER_AGENT}, timeout=5)
            response.raise_for_status()
            found = response.json()
        except (requests.RequestException, ValueError) as error:
            _logger.info('coop_geo: адрес «%s, %s» не найден: %s', address, city, error)
            return None
        if not found:
            return None
        return float(found[0]['lat']), float(found[0]['lon'])

    def _coop_geo_refresh(self):
        for record in self:
            point = self._coop_geocode(record.coop_address, record.city)
            lat, lon = point or (0.0, 0.0)
            # Своя запись — без повторного поиска.
            super(CoopGeoMixin, record).write({'coop_lat': lat, 'coop_lon': lon})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record, vals in zip(records, vals_list):
            if vals.get('coop_address') and 'coop_lat' not in vals:
                record._coop_geo_refresh()
        return records

    def write(self, vals):
        result = super().write(vals)
        # Сменили адрес или город, а точку не передали — ищем заново.
        # Точку передают загрузчики данных: им искать нечего.
        if ('coop_address' in vals or 'city' in vals) and 'coop_lat' not in vals:
            self.filtered('coop_address')._coop_geo_refresh()
            self.filtered(lambda r: not r.coop_address and r.coop_lat).with_context(
                coop_geo_offline=True)._coop_geo_refresh()
        return result

    # ── Наполнение ───────────────────────────────────────────────────

    @api.model
    def _coop_fill_demo_addresses(self):
        """Адреса объявлениям, у которых есть город, но нет адреса.

        Дома настоящие: выгрузка OpenStreetMap вокруг центра каждого
        города (`data/addresses.json`, © участники OpenStreetMap, ODbL).
        У каждого объявления свой дом; порядок выдачи постоянный, и
        повторный запуск ничего не меняет — берутся только записи без
        адреса. Пишем прямо в таблицы: запись через ORM искала бы каждую
        точку заново и меняла дату правки у тысяч объявлений.
        """
        path = get_module_path('coop_geo') + '/data/addresses.json'
        with open(path, encoding='utf-8') as handle:
            pool = json.load(handle)
        from .listings import LISTING_MODELS
        taken = {city: 0 for city in pool}
        cr = self.env.cr
        for name in LISTING_MODELS:
            model = self.env.get(name)
            if model is None:
                continue
            table = model._table
            # Занятые дома не выдаём второй раз.
            cr.execute(f'SELECT city, coop_address FROM {table} '
                       f"WHERE coop_address IS NOT NULL AND coop_address <> ''")
            used = set(cr.fetchall())
            cr.execute(f'SELECT id, city FROM {table} '
                       f"WHERE city = ANY(%s) AND (coop_address IS NULL OR coop_address = '') "
                       f'ORDER BY id', [list(pool)])
            rows = cr.fetchall()
            for record_id, city in rows:
                houses = pool[city]
                while True:
                    street, house, lat, lon = houses[taken[city] % len(houses)]
                    taken[city] += 1
                    address = f'{street}, {house}'
                    if (city, address) not in used or taken[city] > 2 * len(houses):
                        break
                used.add((city, address))
                cr.execute(f'UPDATE {table} SET coop_address = %s, coop_lat = %s, coop_lon = %s '
                           f'WHERE id = %s', [address, lat, lon, record_id])
            model.invalidate_model(['coop_address', 'coop_lat', 'coop_lon'])
            _logger.info('coop_geo: %s — адреса у %s записей', name, len(rows))
