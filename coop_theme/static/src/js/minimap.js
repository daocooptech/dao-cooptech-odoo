/** @odoo-module **/

import { registry } from "@web/core/registry";
import { loadCSS, loadJS } from "@web/core/assets";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onMounted, onWillStart, onWillUnmount, signal, useProps } from "@odoo/owl";

/**
 * Мини-карта на витрине записи — точка адреса под самим адресом.
 *
 * Эталон — `MiniMap` дизайн-системы (`ResourcePage`, `SkillPage`,
 * `VacancyPage`): полоса высотой 120 px с меткой и подписью адреса.
 * Владелец 10.11.2026: «мини-карта в „Где забрать“ после адреса». Карта
 * настоящая — те же Leaflet и тайлы OpenStreetMap, что у карты каталога;
 * точку даёт `coop_geo` по адресу. Карта неподвижна: она показывает, где
 * это, а нажатие открывает место на openstreetmap.org в новой вкладке.
 *
 * Ставится на `coop_lat`; без точки (адрес не нашёлся) не показывается.
 */
const LEAFLET = "/coop_theme/static/lib/leaflet/leaflet";
const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILES_CREDIT = "© участники OpenStreetMap";
const ZOOM = 15;

export class CoopMiniMap extends Component {
    static template = "coop_theme.MiniMap";
    props = useProps(standardFieldProps);

    setup() {
        this.canvas = signal.ref();
        onWillStart(() => Promise.all([loadJS(`${LEAFLET}.js`), loadCSS(`${LEAFLET}.css`)]));
        onMounted(() => this.mountMap());
        onWillUnmount(() => this.map?.remove());
    }

    get data() {
        return this.props.record.data;
    }

    get point() {
        return [this.data.coop_lat, this.data.coop_lon];
    }

    get label() {
        return [this.data.city, this.data.coop_address].filter(Boolean).join(", ");
    }

    get href() {
        const [lat, lon] = this.point;
        return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=17/${lat}/${lon}`;
    }

    mountMap() {
        const L = window.L;
        const el = this.canvas();
        if (!L || !el || !this.data.coop_lat) {
            return;
        }
        this.map = L.map(el, {
            center: this.point, zoom: ZOOM,
            zoomControl: false, dragging: false, scrollWheelZoom: false,
            doubleClickZoom: false, boxZoom: false, keyboard: false, touchZoom: false,
        });
        this.map.attributionControl.setPrefix(false);
        L.tileLayer(TILES, { maxZoom: 19, attribution: TILES_CREDIT }).addTo(this.map);
        // Метка — каплей, как в эталоне; кончик капли стоит на точке.
        L.marker(this.point, {
            interactive: false,
            keyboard: false,
            icon: L.divIcon({
                className: "coop-minimap_pin",
                iconSize: [30, 30],
                iconAnchor: [15, 34],
                html: "<span></span>",
            }),
        }).addTo(this.map);
    }
}

registry.category("fields").add("coop_minimap", {
    component: CoopMiniMap,
    supportedTypes: ["float"],
    fieldDependencies: [
        { name: "coop_lon", type: "float" },
        { name: "coop_address", type: "char" },
        { name: "city", type: "char" },
    ],
});
