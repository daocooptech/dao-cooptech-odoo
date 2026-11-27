/** @odoo-module **/

import { PivotRenderer } from "@web/views/pivot/pivot_renderer";
import { patch } from "@web/core/utils/patch";
import { toneFor } from "@coop_analytics/js/chart_style";

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
patch(PivotRenderer.prototype, {
    coopSimple() {
        const t = this.table;
        return Boolean(
            t && this.model.metaData.activeMeasures.length === 1 && t.headers.length === 3 &&
            t.rows.length > 1 && t.rows.every((r) => r.indent <= 1)
        );
    },
    coopColumns() {
        return this.table.headers[1].map((cell) => ({
            title: cell.title,
            tone: toneFor(cell.title),
        }));
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
        const name = gb.split(":")[0];
        const interval = gb.split(":")[1];
        if (interval === "month") {
            return "Месяц";
        }
        return this.model.metaData.fields?.[name]?.string || "";
    },
    coopValue(cell) {
        if (cell.value === undefined || cell.value === null) {
            return "—";
        }
        const measure = this.model.metaData.measures[cell.measure];
        const money = measure?.type === "monetary";
        return nf.format(cell.value) + (money ? " ₽" : "");
    },
});
