/** @odoo-module **/

import { components } from "@odoo/o-spreadsheet";
import { patch } from "@web/core/utils/patch";
import { restyle } from "@coop_analytics/js/chart_style";

// Графики дашбордов — по образцам дизайн-системы (js/chart_style.js).
patch(components.ChartJsComponent.prototype, {
    createChart(chartData) {
        if (this.env.model.getters.isDashboard() && chartData?.chartJsConfig) {
            restyle(chartData.chartJsConfig, { pieToBars: true });
        }
        super.createChart(chartData);
    },
    updateChartJs(chartData) {
        if (this.env.model.getters.isDashboard() && chartData?.chartJsConfig) {
            restyle(chartData.chartJsConfig, { pieToBars: true });
        }
        super.updateChartJs(chartData);
    },
});
