/** @odoo-module **/

import { GraphRenderer } from "@web/views/graph/graph_renderer";
import { PivotRenderer } from "@web/views/pivot/pivot_renderer";
import { patch } from "@web/core/utils/patch";

/**
 * Меры — видимыми переключателями, а не спрятанным списком «Измерения»
 * (владелец 27.11.2026: «сделай по всем правилам UX/UI»). Порядок
 * постоянный: деньги по смыслу (сумма → оплачено → осталось), затем
 * количество; на графике мера одна, в сводной — до трёх, последнюю не
 * снять.
 */
const ORDER = ["amount", "amount_total", "amount_paid", "amount_residual", "__count"];
export const MAX_MEASURES = 3;

function rank(name) {
    const i = ORDER.indexOf(name);
    return i === -1 ? ORDER.length - 1 : i;
}

export function sortMeasures(names) {
    return [...names].sort((a, b) => rank(a) - rank(b));
}

const chips = {
    coopMeasureList() {
        const { measures } = this.model.metaData;
        return sortMeasures(Object.keys(measures || {})).map((name) => ({
            name,
            label: name === "__count" ? "Количество" : measures[name].string,
        }));
    },
};

patch(GraphRenderer.prototype, {
    ...chips,
    coopMeasureActive(name) {
        return this.model.metaData.measure === name;
    },
    coopMeasureDisabled() {
        return false;
    },
    coopToggleMeasure(name) {
        if (!this.coopMeasureActive(name)) {
            this.onMeasureSelected({ measure: name });
        }
    },
});

patch(PivotRenderer.prototype, {
    ...chips,
    coopMeasureActive(name) {
        return this.model.metaData.activeMeasures.includes(name);
    },
    coopMeasureDisabled(name) {
        const active = this.model.metaData.activeMeasures;
        const on = active.includes(name);
        return (on && active.length === 1) || (!on && active.length >= MAX_MEASURES);
    },
    coopToggleMeasure(name) {
        if (!this.coopMeasureDisabled(name)) {
            this.onMeasureSelected({ measure: name });
        }
    },
});
