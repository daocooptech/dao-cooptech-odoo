/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

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
    static props = {
        resModel: String,
        domain: { type: Array, optional: true },
        // Куда вернуться после выбора города. Передаётся представлением, а
        // не берётся из состояния вида: карта и переключатель вида тогда
        // ссылались бы друг на друга, и модуль загружался бы наполовину
        // собранным.
        showTiles: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ pins: [], other: 0, loading: true, failed: false });
        onWillStart(() => this.load(this.props.domain));
        // Отбор меняется, пока карта на экране: сняли город, поставили
        // цену. Без этого метки остались бы от первого захода, а подпись
        // под картой обещает «с учётом текущего отбора» — и врала бы.
        onWillUpdateProps((next) => {
            if (JSON.stringify(next.domain) !== JSON.stringify(this.props.domain)) {
                return this.load(next.domain);
            }
        });
    }

    async load(domain) {
        // Считаем на сервере группировкой, а не по загруженной странице:
        // на карте нужен весь отбор целиком, а страница — это два десятка
        // записей, и метки по ней врали бы в разы.
        let groups = [];
        let total = 0;
        this.state.loading = true;
        this.state.failed = false;
        try {
            // Группируем только по городам, у которых на схеме есть место,
            // а «в остальных» получаем вычитанием из общего числа.
            //
            // Раньше группировка шла по всему отбору без ограничений. Город
            // у объявления — свободная строка, и на большом каталоге разных
            // её написаний становятся тысячи: сервер собирал бы и слал
            // тысячи групп ради одного числа под картой, а показывались бы
            // из них те же двадцать восемь.
            const known = Object.keys(CITY_POS);
            [groups, total] = await Promise.all([
                this.orm.call(
                    this.props.resModel, "formatted_read_group",
                    [[...(domain || []), ["city", "in", known]],
                     ["city"], ["__count"]]
                ),
                this.orm.searchCount(this.props.resModel, domain || []),
            ]);
        } catch {
            // Пустая карта и «нет подходящих городов» — разные вещи, и
            // сказать первое вторым значит соврать: отбор человек менял,
            // а не связь.
            this.state.pins = [];
            this.state.other = 0;
            this.state.failed = true;
            this.state.loading = false;
            return;
        }
        const pins = [];
        let shown = 0;
        for (const group of groups) {
            const city = group.city;
            const count = group.__count || 0;
            const pos = city && CITY_POS[city];
            if (!pos) {
                continue;
            }
            shown += count;
            pins.push({ city, count, left: pos[0], top: pos[1], size: 12 });
        }
        // Всё, что не попало на схему: города без места на ней и
        // объявления вовсе без города.
        const other = Math.max(0, total - shown);
        // Размер метки — доля от самого людного города, а не само число.
        // Считали от числа с потолком в 28 — и на каталоге в двести
        // записей все метки упирались в потолок и выходили одинаковыми,
        // хотя подпись под картой обещает, что размер о чём-то говорит.
        const largest = pins.reduce((top, pin) => Math.max(top, pin.count), 0);
        for (const pin of pins) {
            pin.size = largest
                ? Math.round(10 + 18 * Math.sqrt(pin.count / largest))
                : 10;
        }
        this.state.pins = pins;
        this.state.other = other;
        this.state.loading = false;
    }

    /** Щелчок по метке отбирает город и возвращает к плиткам.
     *
     *  Возврат — как в прототипе: нажав на город, человек хочет увидеть
     *  тамошние объявления. Раньше он оставался на карте, где после
     *  отбора оставалась одна метка, и происшедшее выглядело так, будто
     *  карта опустела. */
    selectCity(city) {
        const search = this.env.searchModel;
        if (this.groupId) {
            search.deactivateGroup(this.groupId);
        }
        this.groupId = search.nextGroupId;
        search.createNewFilters([{
            description: city, domain: [["city", "=", city]],
        }]);
        this.props.showTiles?.();
    }
}
