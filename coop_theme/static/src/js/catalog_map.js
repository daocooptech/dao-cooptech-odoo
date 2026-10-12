/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { loadCSS, loadJS } from "@web/core/assets";
import { ActionPlugin } from "@web/webclient/actions/action_plugin";
import {
    Component, onMounted, onWillStart, onWillUnmount, onWillUpdateProps, proxy, signal, t, usePlugin,
    useProps,
} from "@odoo/owl";

/**
 * Каталог на карте: настоящая карта (OpenStreetMap) с метками по городам.
 *
 * Место у объявления указано городом, а не точкой, поэтому метка стоит в
 * центре города, а размер её — сколько там записей с учётом отбора.
 * Подложка — тайлы OpenStreetMap: карту выбрал владелец 12.10.2026
 * («карта настоящая») вместо прежней схемы на сетке. Библиотека Leaflet
 * лежит в теме (`static/lib/leaflet`, BSD-2) и грузится, только когда
 * открывают карту. Без сети тайлы не придут — метки останутся на сетке.
 */
const LEAFLET = "/coop_theme/static/lib/leaflet/leaflet";
const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILES_CREDIT =
    '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">участники OpenStreetMap</a>';

// Широта и долгота центров городов, которые встречаются в каталогах.
// «Алтайский край» — краевой центр, Барнаул. Города нет в списке — запись
// уходит в «без города или вне карты» под картой.
const CITY_COORDS = {
    "Москва": [55.756, 37.617], "Санкт-Петербург": [59.939, 30.316],
    "Пермь": [58.010, 56.229], "Казань": [55.796, 49.106],
    "Екатеринбург": [56.838, 60.597], "Новосибирск": [55.030, 82.920],
    "Кемерово": [55.354, 86.087], "Краснодар": [45.035, 38.975],
    "Волгоград": [48.708, 44.513], "Хабаровск": [48.480, 135.072],
    "Вологда": [59.220, 39.891], "Омск": [54.989, 73.369],
    "Архангельск": [64.539, 40.516], "Красноярск": [56.010, 92.852],
    "Ростов-на-Дону": [47.222, 39.720], "Тюмень": [57.153, 65.534],
    "Самара": [53.195, 50.101], "Воронеж": [51.661, 39.200],
    "Нижний Новгород": [56.327, 44.006], "Челябинск": [55.160, 61.403],
    "Тобольск": [58.198, 68.254], "Дербент": [42.058, 48.290],
    "Ишим": [56.113, 69.490], "Сочи": [43.585, 39.720],
    "Калининград": [54.710, 20.452], "Уфа": [54.735, 55.958],
    "Владивосток": [43.116, 131.882], "Ярославль": [57.626, 39.894],
    "Магнитогорск": [53.407, 58.980], "Нижний Тагил": [57.910, 59.981],
    "Иркутск": [52.287, 104.305], "Тула": [54.193, 37.618],
    "Курск": [51.730, 36.193], "Псков": [57.819, 28.332],
    "Ижевск": [56.853, 53.212], "Братск": [56.151, 101.634],
    "Алтайский край": [53.348, 83.779], "Саяногорск": [53.088, 91.400],
    "Мурманск": [68.970, 33.075], "Кострома": [57.768, 40.927],
    "Киров": [58.604, 49.668], "Тверь": [56.859, 35.912],
    "Сургут": [61.254, 73.396], "Калуга": [54.514, 36.261],
    "Рязань": [54.629, 39.736], "Абакан": [53.721, 91.442],
    "Нижневартовск": [60.939, 76.569],
    "Минск": [53.904, 27.562], "Ереван": [40.177, 44.513],
    "Тбилиси": [41.716, 44.783], "Ташкент": [41.299, 69.240],
    "Алматы": [43.238, 76.946], "Астана": [51.169, 71.449],
    "Рига": [56.950, 24.105], "Хельсинки": [60.170, 24.938],
    "Белград": [44.787, 20.457], "Берлин": [52.520, 13.405],
    "Стамбул": [41.008, 28.978], "Дубай": [25.205, 55.271],
    "Бангалор": [12.972, 77.594], "Пхукет": [7.880, 98.392],
    "Хошимин": [10.823, 106.630], "Шанхай": [31.230, 121.474],
    "Нью-Йорк": [40.713, -74.006],
};

// Первый взгляд — на Россию и соседей: шесть записей в Нью-Йорке не
// должны отдалять карту до целого света, на котором русские города
// слипаются в одно пятно. Отдалить карту человек может сам.
function nearHome([lat, lon]) {
    return lat > 38 && lon > 19;
}

// Объявления с адресом стоят каждое своей точкой (`coop_geo`, владелец
// 12.10.2026: «почему не показывает точный адрес каждого объявления? …
// смотри как сделано на авито»). Близкие точки при отдалении собираются
// в кружок с числом, нажатие приближает; у точки — карточка с фото,
// ценой и адресом. Каталоги без адресов (люди, организации) остаются
// с метками по городам.
const POINT_LIMIT = 5000;
const PRICE_FIELDS = ["price", "current_price", "main_price", "rate"];
const IMAGE_FIELDS = ["image_512", "image_1920"];

function formatPrice(value) {
    return `${Math.round(value).toLocaleString("ru-RU")} ₽`;
}

// Названия городов — с этого приближения; дальше метки слишком тесны, и
// подписи легли бы друг на друга. Число в кружке видно всегда.
const NAMES_FROM_ZOOM = 5;

function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);
}

export class CoopMap extends Component {
    static template = "coop_theme.CatalogMap";
    props = useProps({
        resModel: t.string(),
        domain: t.array().optional(),
        // Куда вернуться после выбора города. Передаётся представлением, а
        // не берётся из состояния вида: карта и переключатель вида тогда
        // ссылались бы друг на друга, и модуль загружался бы наполовину
        // собранным.
        showTiles: t.function().optional(),
        // Поля модели: есть ли у объявлений адрес, цена и фото.
        fields: t.object().optional(),
    });

    setup() {
        this.orm = useService("orm");
        this.action = usePlugin(ActionPlugin);
        this.state = proxy({ pins: [], shown: 0, other: 0, loading: true, failed: false });
        this.points = [];
        this.canvas = signal.ref();
        onWillStart(() => Promise.all([
            // Объединение точек — дополнение к Leaflet и грузится после него.
            loadJS(`${LEAFLET}.js`).then(() => loadJS(`${LEAFLET}.markercluster.js`)),
            loadCSS(`${LEAFLET}.css`),
            loadCSS("/coop_theme/static/lib/leaflet/markercluster.css"),
            this.load(this.props.domain),
        ]));
        onMounted(() => this.mountMap());
        onWillUnmount(() => {
            this.resize?.disconnect();
            this.map?.remove();
        });
        // Отбор меняется, пока карта на экране: сняли город, поставили
        // цену. Без этого метки остались бы от первого захода, а подпись
        // под картой обещает «с учётом текущего отбора» — и врала бы.
        onWillUpdateProps((next) => {
            if (JSON.stringify(next.domain) !== JSON.stringify(this.props.domain)) {
                return this.load(next.domain);
            }
        });
    }

    /** Есть ли у объявлений этого каталога адрес и точка. */
    get byPoint() {
        return Boolean(this.props.fields?.coop_lat);
    }

    load(domain) {
        return this.byPoint ? this.loadPoints(domain) : this.loadCities(domain);
    }

    async loadPoints(domain) {
        const fields = this.props.fields;
        this.priceField = PRICE_FIELDS.find((name) => fields[name]) || null;
        this.imageField = IMAGE_FIELDS.find((name) => fields[name]) || null;
        this.state.loading = true;
        this.state.failed = false;
        let rows = [];
        let total = 0;
        try {
            [rows, total] = await Promise.all([
                this.orm.searchRead(
                    this.props.resModel, [...(domain || []), ["coop_lat", "!=", 0]],
                    ["display_name", "coop_address", "city", "coop_lat", "coop_lon",
                     ...(this.priceField ? [this.priceField] : [])],
                    { limit: POINT_LIMIT }),
                this.orm.searchCount(this.props.resModel, domain || []),
            ]);
        } catch {
            this.points = [];
            this.state.shown = 0;
            this.state.other = 0;
            this.state.failed = true;
            this.state.loading = false;
            return;
        }
        this.points = rows.map((row) => ({
            id: row.id,
            name: row.display_name,
            address: row.coop_address || "",
            city: row.city || "",
            pos: [row.coop_lat, row.coop_lon],
            price: this.priceField ? row[this.priceField] : null,
        }));
        this.state.shown = this.points.length;
        this.state.other = Math.max(0, total - this.points.length);
        this.state.loading = false;
        this.drawPins();
    }

    async loadCities(domain) {
        // Считаем на сервере группировкой, а не по загруженной странице:
        // на карте нужен весь отбор целиком, а страница — это два десятка
        // записей, и метки по ней врали бы в разы.
        let groups = [];
        let total = 0;
        this.state.loading = true;
        this.state.failed = false;
        try {
            // Группируем только по городам, у которых на карте есть место,
            // а «в остальных» получаем вычитанием из общего числа.
            //
            // Раньше группировка шла по всему отбору без ограничений. Город
            // у объявления — свободная строка, и на большом каталоге разных
            // её написаний становятся тысячи: сервер собирал бы и слал
            // тысячи групп ради одного числа под картой, а показывались бы
            // из них те же шесть десятков.
            const known = Object.keys(CITY_COORDS);
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
            const pos = city && CITY_COORDS[city];
            if (!pos) {
                continue;
            }
            shown += count;
            pins.push({ city, count, pos, size: 22 });
        }
        // Всё, что не попало на карту: города без места на ней и
        // объявления вовсе без города.
        const other = Math.max(0, total - shown);
        // Размер метки — доля от самого людного города, а не само число.
        // Считали от числа с потолком в 28 — и на каталоге в двести
        // записей все метки упирались в потолок и выходили одинаковыми,
        // хотя подпись под картой обещает, что размер о чём-то говорит.
        const largest = pins.reduce((top, pin) => Math.max(top, pin.count), 0);
        // Внутри кружка — число, поэтому меньше 22 точек он не бывает.
        for (const pin of pins) {
            pin.size = largest
                ? Math.round(22 + 18 * Math.sqrt(pin.count / largest))
                : 22;
        }
        this.state.pins = pins;
        this.state.shown = pins.length;
        this.state.other = other;
        this.state.loading = false;
        this.drawPins();
    }

    mountMap() {
        const L = window.L;
        const el = this.canvas();
        if (!L || !el) {
            return;
        }
        this.map = L.map(el, {
            center: [58, 70], zoom: 3, minZoom: 2, maxZoom: 12,
            worldCopyJump: true, zoomSnap: 0.5,
        });
        // Без флажка и ссылки на саму библиотеку: подпись про данные
        // OpenStreetMap лицензия требует, про Leaflet — нет.
        this.map.attributionControl.setPrefix(false);
        L.tileLayer(TILES, { maxZoom: 19, attribution: TILES_CREDIT }).addTo(this.map);
        this.layer = L.layerGroup().addTo(this.map);
        // Кнопка в карточке точки — разметкой Leaflet, а не шаблоном,
        // поэтому нажатие ловим при каждом открытии карточки.
        this.map.on("popupopen", ({ popup }) => {
            const button = popup.getElement()?.querySelector(".o_coop_lpop_open");
            button?.addEventListener("click", () => this.openRecord(Number(button.dataset.id)));
        });
        this.map.on("zoomend", () => this.showNames());
        // Планку развернули, окно сузили — карта пересчитывает свой размер,
        // иначе справа остаётся серая полоса без тайлов.
        this.resize = new ResizeObserver(() => this.map.invalidateSize());
        this.resize.observe(el);
        this.drawPins();
    }

    drawPins() {
        const L = window.L;
        if (!this.map || !L) {
            return;
        }
        this.layer.clearLayers();
        if (this.byPoint) {
            this.drawPoints();
            return;
        }
        for (const pin of this.state.pins) {
            const city = escapeHtml(pin.city);
            const icon = L.divIcon({
                className: "o_coop_lpin",
                iconSize: [pin.size, pin.size],
                iconAnchor: [pin.size / 2, pin.size / 2],
                html: `<span class="o_coop_lpin_dot">${pin.count}</span>`
                    + `<span class="o_coop_lpin_label">${city} · <b>${pin.count}</b></span>`,
            });
            L.marker(pin.pos, {
                icon,
                title: `${pin.city}: ${pin.count}. Показать записи из этого города`,
                riseOnHover: true,
            }).on("click", () => this.selectCity(pin.city)).addTo(this.layer);
        }
        const points = this.state.pins.map((pin) => pin.pos);
        const home = points.filter(nearHome);
        const view = home.length ? home : points;
        if (view.length) {
            this.map.fitBounds(view, { padding: [36, 36], maxZoom: 6 });
        }
        this.showNames();
    }

    drawPoints() {
        const L = window.L;
        const dot = L.divIcon({
            className: "o_coop_lpin o_coop_lpoint",
            iconSize: [16, 16],
            iconAnchor: [8, 8],
            html: '<span class="o_coop_lpin_dot"></span>',
        });
        const group = L.markerClusterGroup({
            showCoverageOnHover: false,
            maxClusterRadius: 48,
            chunkedLoading: true,
            iconCreateFunction: (cluster) => {
                const count = cluster.getChildCount();
                const size = count < 10 ? 30 : count < 100 ? 36 : count < 1000 ? 44 : 52;
                return L.divIcon({
                    className: "o_coop_lpin",
                    iconSize: [size, size],
                    html: `<span class="o_coop_lpin_dot">${count}</span>`,
                });
            },
        });
        for (const point of this.points) {
            group.addLayer(L.marker(point.pos, { icon: dot, title: point.name })
                .bindPopup(() => this.popupHtml(point), { minWidth: 220, maxWidth: 260 }));
        }
        this.layer.addLayer(group);
        const spots = this.points.map((point) => point.pos);
        const home = spots.filter(nearHome);
        const view = home.length ? home : spots;
        if (view.length) {
            this.map.fitBounds(view, { padding: [36, 36], maxZoom: 14 });
        }
    }

    /** Карточка у точки — как на доске объявлений: фото, название,
     *  цена, адрес и переход к самому объявлению. */
    popupHtml(point) {
        const image = this.imageField
            ? `<img class="o_coop_lpop_img" loading="lazy" alt=""
                    src="/web/image/${this.props.resModel}/${point.id}/${this.imageField}"/>`
            : "";
        const price = point.price
            ? `<div class="o_coop_lpop_price">${formatPrice(point.price)}</div>` : "";
        const place = [point.city, point.address].filter(Boolean).map(escapeHtml).join(", ");
        return `<div class="o_coop_lpop">${image}`
            + `<div class="o_coop_lpop_name">${escapeHtml(point.name)}</div>${price}`
            + `<div class="o_coop_lpop_addr">${place}</div>`
            + `<button type="button" class="btn btn-primary btn-sm o_coop_lpop_open"`
            + ` data-id="${point.id}">Открыть объявление</button></div>`;
    }

    /** Открыть объявление его страницей, как из плитки. */
    async openRecord(id) {
        let action = null;
        try {
            action = await this.orm.call(this.props.resModel, "action_coop_open_page", [[id]]);
        } catch {
            action = null;
        }
        this.action.doAction(action || {
            type: "ir.actions.act_window",
            res_model: this.props.resModel,
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    showNames() {
        if (!this.map) {
            return;
        }
        this.canvas()?.classList.toggle(
            "o_coop_map_names", this.map.getZoom() >= NAMES_FROM_ZOOM);
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
