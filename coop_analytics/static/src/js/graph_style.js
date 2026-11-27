/** @odoo-module **/

import { GraphRenderer } from "@web/views/graph/graph_renderer";
import { patch } from "@web/core/utils/patch";
import { restyle } from "@coop_analytics/js/chart_style";

// Вид «График» (отчёты «Аналитики» и любые другие) — по образцам
// дизайн-системы (js/chart_style.js), как и дашборды.
patch(GraphRenderer.prototype, {
    getChartConfig() {
        return restyle(super.getChartConfig());
    },
});
