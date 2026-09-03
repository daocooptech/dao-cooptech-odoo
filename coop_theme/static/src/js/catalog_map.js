/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * Каталог на карте: схематичная карта России с метками по городам.
 *
 * Настоящая картографическая подложка потребовала бы внешнего сервиса
 * тайлов и координат у каждого объявления. Ни того, ни другого у нас
 * нет: платформа показывается без выхода в интернет, а место у
 * объявления указано городом, а не точкой. Схема отвечает ровно на тот
 * вопрос, на который есть данные, — где чего сколько.
 *
 * Так же сделано и в прототипе (`resources.html`), метки и координаты
 * городов оттуда же.
 */
const CITY_POS = {
    "Санкт-Петербург": [8, 20], "Москва": [18, 32], "Вологда": [17, 24],
    "Воронеж": [20, 42], "Ростов-на-Дону": [18, 54], "Краснодар": [15, 58],
    "Сочи": [16, 64], "Дербент": [24, 68], "Волгоград": [24, 52],
    "Самара": [30, 42], "Казань": [32, 34], "Уфа": [38, 38],
    "Пермь": [40, 28], "Екатеринбург": [44, 32], "Челябинск": [44, 38],
    "Тюмень": [50, 30], "Омск": [56, 36], "Алтайский край": [60, 46],
    "Новосибирск": [62, 38], "Красноярск": [70, 34], "Иркутск": [80, 42],
    "Нижний Новгород": [24, 30], "Нижний Тагил": [42, 28],
    "Хабаровск": [92, 46], "Владивосток": [90, 54], "Калининград": [3, 18],
    "Архангельск": [22, 12], "Магнитогорск": [42, 42],
};

export class CoopMap extends Component {
    static template = "coop_theme.CatalogMap";
    static props = { resModel: String, domain: { type: Array, optional: true } };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ pins: [], other: 0, loading: true });
        onWillStart(() => this.load());
    }

    async load() {
        // Считаем на сервере группировкой, а не по загруженной странице:
        // на карте нужен весь отбор целиком, а страница — это два десятка
        // записей, и метки по ней врали бы в разы.
        let groups = [];
        try {
            groups = await this.orm.call(
                this.props.resModel, "formatted_read_group",
                [this.props.domain || [], ["city"], ["__count"]]
            );
        } catch {
            this.state.loading = false;
            return;
        }
        const pins = [];
        let other = 0;
        for (const group of groups) {
            const city = group.city;
            const count = group.__count || 0;
            const pos = city && CITY_POS[city];
            if (!pos) {
                other += count;
                continue;
            }
            pins.push({
                city,
                count,
                left: pos[0],
                top: pos[1],
                // Размер метки — сколько объявлений в городе, но с
                // потолком: без него Москва закрыла бы половину карты.
                size: Math.min(28, 12 + count * 1.5),
            });
        }
        this.state.pins = pins;
        this.state.other = other;
        this.state.loading = false;
    }

    /** Щелчок по метке отбирает город — как в прототипе. */
    selectCity(city) {
        const search = this.env.searchModel;
        if (this.groupId) {
            search.deactivateGroup(this.groupId);
        }
        this.groupId = search.nextGroupId;
        search.createNewFilters([{
            description: city, domain: [["city", "=", city]],
        }]);
    }
}
