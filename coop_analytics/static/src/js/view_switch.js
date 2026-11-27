/** @odoo-module **/

import { PivotRenderer } from "@web/views/pivot/pivot_renderer";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

/**
 * Переключатель «График · Сводная · Список» с подписями (ViewSwitch
 * дизайн-системы) — в ряду с мерой, у графика и у сводной
 * (xml/graph_panel.xml).
 */
export const coopViewSwitch = {
    coopViews() {
        return this.env.config?.viewSwitcherEntries || [];
    },
    coopViewName(view) {
        // В образце — «Сводная», без «таблицы».
        return view.type === "pivot" ? "Сводная" : view.name;
    },
    coopSwitchView(type) {
        if (!this.coopViews().find((v) => v.type === type)?.active) {
            this.coopAction.switchView(type);
        }
    },
};

patch(PivotRenderer.prototype, {
    setup() {
        super.setup();
        this.coopAction = useService("action");
    },
    ...coopViewSwitch,
});
