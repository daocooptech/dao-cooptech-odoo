/** @odoo-module **/

import { PivotRenderer } from "@web/views/pivot/pivot_renderer";
import { patch } from "@web/core/utils/patch";
import { toneFor } from "@coop_analytics/js/chart_style";
import { MAX_MEASURES as LIMIT, sortMeasures } from "@coop_analytics/js/measure_chips";

const nf = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const MONTHS = {
    января: "Январь", февраля: "Февраль", марта: "Март", апреля: "Апрель",
    мая: "Май", июня: "Июнь", июля: "Июль", августа: "Август",
    сентября: "Сентябрь", октября: "Октябрь", ноября: "Ноябрь", декабря: "Декабрь",
};

/**
 * «Сводная» — таблицей Table дизайн-системы, когда она простая: одна мера,
 * строки и столбцы — по одному полю (владелец 27.11.2026: «как этим
 * пользоваться вообще»). Шапка в одну строку с цветом состояния, как на
 * графике; месяцы в именительном; суммы без копеек, пустое — прочерк;
 * итог — строкой внизу. Сложную сводную
 * (несколько мер, вложенные разбивки) рисует движок (xml/graph_panel.xml).
 */
const MAX_MEASURES = LIMIT;

patch(PivotRenderer.prototype, {
    coopN() {
        return this.model.metaData.activeMeasures.length;
    },
    coopSimple() {
        const t = this.table;
        const n = this.coopN();
        return Boolean(
            t && n >= 1 && n <= MAX_MEASURES && t.headers.length === 3 &&
            t.headers[1].every((c) => c.width === n) &&
            t.rows.length > 1 && t.rows.every((r) => r.indent <= 1)
        );
    },
    coopColumns() {
        return this.table.headers[1].map((cell) => ({
            title: cell.title,
            tone: toneFor(cell.title),
        }));
    },
    // Порядок мер в клетке — постоянный (сумма → оплачено → осталось →
    // количество), а не порядок щелчков.
    coopOrder() {
        const active = this.model.metaData.activeMeasures;
        return sortMeasures(active).map((m) => active.indexOf(m));
    },
    coopMeasureLabels() {
        const { activeMeasures, measures } = this.model.metaData;
        return sortMeasures(activeMeasures).map((m) => (m === "__count" ? "Количество" : measures[m]?.string || m));
    },
    // Клетки строки — по состоянию (и «Всего»), в каждой — все меры.
    coopCells(row) {
        const n = this.coopN();
        const out = [];
        for (let i = 0; i < row.subGroupMeasurements.length; i += n) {
            const chunk = row.subGroupMeasurements.slice(i, i + n);
            out.push(this.coopOrder().map((k) => chunk[k]));
        }
        return out;
    },
    coopRows() {
        return this.table.rows.slice(1);
    },
    coopTotalRow() {
        return this.table.rows[0];
    },
    coopRowTitle(row) {
        const text = String(row.title || "");
        const m = text.match(/^(\S+)\s+(\d{4})$/);
        if (m && MONTHS[m[1].toLowerCase()]) {
            return `${MONTHS[m[1].toLowerCase()]} ${m[2]}`;
        }
        return text.charAt(0).toUpperCase() + text.slice(1);
    },
    coopRowLabel() {
        const gb = this.model.metaData.rowGroupBys?.[0] || "";
        const [name, interval] = gb.split(":");
        if (interval === "month") {
            return "Месяц";
        }
        return this.model.metaData.fields?.[name]?.string || "";
    },
    coopValue(cell) {
        if (cell?.value === undefined || cell?.value === null) {
            return "—";
        }
        const measure = this.model.metaData.measures[cell.measure];
        const money = measure?.type === "monetary";
        return nf.format(cell.value) + (money ? " ₽" : "");
    },
    // Заливка по величине первой меры — крупные клетки видно без чтения
    // цифр. Самая крупная клетка месяцев — 14 % чернильного.
    coopHeat(group, isTotal) {
        const v = group[0]?.value;
        if (isTotal || !v || v <= 0) {
            return "";
        }
        if (this.__coopMax === undefined || this.__coopMaxTable !== this.table) {
            let max = 0;
            for (const row of this.coopRows()) {
                const cells = this.coopCells(row);
                cells.slice(0, -1).forEach((g) => (max = Math.max(max, g[0]?.value || 0)));
            }
            this.__coopMax = max || 1;
            this.__coopMaxTable = this.table;
        }
        const pct = Math.round((v / this.__coopMax) * 14 * 10) / 10;
        return `background: color-mix(in srgb, var(--coop-ink) ${pct}%, transparent)`;
    },
});
