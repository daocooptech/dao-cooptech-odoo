/** @odoo-module **/

import { GraphRenderer } from "@web/views/graph/graph_renderer";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { restyle } from "@coop_analytics/js/chart_style";
import { coopViewSwitch } from "@coop_analytics/js/view_switch";

const nf = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const STEP_NOUN = { day: "день", week: "неделя", month: "месяц", quarter: "квартал", year: "год" };

/**
 * Вид «График» (отчёты «Аналитики» и любые другие) — по образцам
 * дизайн-системы: график (js/chart_style.js) и панель (xml/graph_panel.xml,
 * образец «Сделки»: мера и переключатель вида в одном ряду, над графиком
 * итог и шаг, под графиком — что показано).
 */
patch(GraphRenderer.prototype, {
    setup() {
        super.setup();
        this.coopAction = useService("action");
        this.coopSteps = [
            { id: "week", label: "Недели" },
            { id: "month", label: "Месяцы" },
            { id: "year", label: "Годы" },
        ];
    },

    getChartConfig() {
        return restyle(super.getChartConfig());
    },

    ...coopViewSwitch,

    // ── итог и шаг ────────────────────────────────────────────────────
    coopMeasure() {
        const { measure, measures, fields } = this.model.metaData;
        const field = (measures && measures[measure]) || fields?.[measure] || {};
        return { name: measure, label: field.string || "", type: fields?.[measure]?.type };
    },
    coopTotalLabel() {
        const m = this.coopMeasure();
        const label = m.name === "__count" ? "Количество" : m.label;
        return `${label} за период`;
    },
    coopTotal() {
        const datasets = (this.model.data?.datasets || []).filter((ds) => ds.type !== "line");
        let total = 0;
        for (const ds of datasets) {
            for (const v of ds.data || []) {
                total += typeof v === "number" ? v : v?.y || 0;
            }
        }
        if (this.model.metaData.cumulated) {
            // С нарастающим итогом сумма столбцов — не итог; итог — последний.
            total = datasets.reduce((sum, ds) => sum + (ds.data?.at(-1) || 0), 0);
        }
        const suffix = this.coopMeasure().type === "monetary" ? " ₽" : "";
        return nf.format(total) + suffix;
    },
    coopDateGroup() {
        return (this.model.metaData.groupBy || []).find((gb) => gb.interval) || null;
    },
    async coopSetStep(interval) {
        const groupBy = this.model.metaData.groupBy.map((gb) =>
            gb.interval ? `${gb.fieldName}:${interval}` : gb.spec || gb.fieldName
        );
        this.model.initialGroupBy = groupBy;
        await this.model.load({ ...this.model.searchParams, groupBy: [] });
        this.model.notify();
    },
    coopCaption() {
        const date = this.coopDateGroup();
        const field = date && this.model.metaData.fields?.[date.fieldName];
        const parts = [];
        if (date) {
            let text = "Столбец — " + (STEP_NOUN[date.interval] || date.interval);
            if (field) {
                text += ", по полю «" + field.string + "»";
            }
            parts.push(text);
        }
        const second = (this.model.metaData.groupBy || []).find((gb) => !gb.interval);
        if (second) {
            const f = this.model.metaData.fields?.[second.fieldName];
            parts.push(`разбивка — «${f?.string || second.fieldName}»`);
        }
        parts.push("точные значения — в подсказке и в «Сводной»");
        const text = parts.join("; ") + ".";
        return text.charAt(0).toUpperCase() + text.slice(1);
    },
});
