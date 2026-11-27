/** @odoo-module **/

import { Spreadsheet } from "@odoo/o-spreadsheet";
import { onMounted, onWillUnmount, useLayoutEffect } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";

/**
 * Дашборд — часть страницы, а не страница в странице.
 *
 * Движок держит таблицу дашборда в окне заданной высоты со своими
 * прокрутками, а лист шире места рядом со списком дашбордов. Владелец
 * 27.11.2026: «вид как будто страница в странице, куча прокруток».
 *
 * Здесь лист вписывается по ширине масштабом (не крупнее 100 %), а окну
 * дана высота всего листа — прокрутка остаётся одна, у страницы.
 */
const SpreadsheetDashboard = Spreadsheet.components.SpreadsheetDashboard;
const MIN_ZOOM = 0.5;

patch(SpreadsheetDashboard.prototype, {
    setup() {
        super.setup();
        const fit = () => this.coopFit();
        let observer;
        onMounted(() => {
            const host = this.gridRef()?.closest(".o_renderer");
            if (host && window.ResizeObserver) {
                observer = new ResizeObserver(fit);
                observer.observe(host);
            }
            fit();
        });
        onWillUnmount(() => observer?.disconnect());
        useLayoutEffect(fit);
    },

    coopFit() {
        const grid = this.gridRef();
        const host = grid?.closest(".o_renderer");
        if (!host || host.closest(".o_mobile_dashboard")) {
            return;
        }
        const getters = this.env.model.getters;
        const sheetId = this.viewStore.displayedSheetId;
        const { bottom } = getters.getSheetZone(sheetId);
        const sheetHeight = getters.getRowDimensions(sheetId, bottom).end;
        const sheetWidth = this.getMaxSheetWidth();
        // Полоса прокрутки движка (15 точек) занимает место всегда — без
        // её ширины лист не помещался на 15 точек и внизу была прокрутка.
        const scrollbar = this.zoomStore.scrollBarWidth || 15;
        const zoom = Math.max(MIN_ZOOM, Math.min(1, (host.clientWidth - scrollbar - 1) / sheetWidth));
        if (Math.abs(zoom - this.zoomStore.zoomLevel) > 0.005) {
            this.zoomStore.setZoom(Math.round(zoom * 1000) / 1000);
        }
        // Запас под полосу прокрутки движка: без него она появляется ровно
        // на последних точках листа.
        const height = `${Math.ceil(sheetHeight * zoom) + 24}px`;
        if (host.style.height !== height) {
            host.style.height = height;
        }
    },
});
