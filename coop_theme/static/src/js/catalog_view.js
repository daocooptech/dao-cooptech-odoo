/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { reactive, useState } from "@odoo/owl";

/**
 * Три вида каталога в одном переключателе: плиткой, канбаном, списком.
 *
 * Список — отдельное представление Odoo, и его кнопка в переключателе уже
 * есть. Плитка и канбан — одно представление с разной раскладкой
 * карточки: второго канбана в одном действии Odoo не допускает, а
 * дублировать разметку незачем — в прототипе она тоже одна, и
 * переключается класс на списке.
 *
 * Поэтому кнопка «плиткой» подставляется в штатный переключатель рядом с
 * канбаном и списком. Своей группы кнопок нет намеренно: два
 * переключателя на одном экране заставляют гадать, чем они отличаются.
 */
const STORAGE_KEY = "coop-catalog-view";

function readSavedLayout() {
    // localStorage может быть недоступен — в приватном окне или при
    // запрете хранилища. Тогда просто плитка, как по умолчанию.
    try {
        return browser.localStorage.getItem(STORAGE_KEY);
    } catch {
        return null;
    }
}

// Общее состояние вида: его читает и панель управления, чтобы подсветить
// нужную кнопку, и представление, чтобы поставить класс на корень.
export const coopLayout = reactive({ rows: readSavedLayout() === "rows" });

export function setCoopLayout(rows) {
    coopLayout.rows = rows;
    try {
        browser.localStorage.setItem(STORAGE_KEY, rows ? "rows" : "tiles");
    } catch {
        // Не сохранилось — вид всё равно переключился, просто забудется.
    }
}

export class CoopCatalogKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.coopLayout = useState(coopLayout);
    }
}

CoopCatalogKanbanController.template = "coop_theme.CatalogKanbanView";

registry.category("views").add("coop_catalog_kanban", {
    ...kanbanView,
    Controller: CoopCatalogKanbanController,
});

patch(ControlPanel.prototype, {
    /**
     * Каталог платформы узнаётся по признаку в контексте действия. Признак
     * стоит на самом действии, поэтому виден и в канбане, и в списке — в
     * отличие от класса представления, который в списке недоступен.
     */
    get coopIsCatalog() {
        return Boolean(this.env.searchModel?.globalContext?.coop_catalog);
    },

    /**
     * Кнопки переключателя. У каталога канбан раздваивается на «плиткой» и
     * «канбаном»: это одно представление в двух раскладках.
     */
    get coopViewEntries() {
        const entries = this.env.config.viewSwitcherEntries || [];
        if (!this.coopIsCatalog) {
            return entries;
        }
        return entries.flatMap((entry) => {
            if (entry.type !== "kanban") {
                return [entry];
            }
            return [
                {
                    ...entry,
                    type: "coop_tiles",
                    name: "Плиткой",
                    icon: "oi oi-view-kanban",
                    active: entry.active && !coopLayout.rows,
                },
                {
                    ...entry,
                    name: "Канбаном",
                    icon: "fa fa-align-justify",
                    active: entry.active && coopLayout.rows,
                },
            ];
        });
    },

    switchView(viewType, isMiddleClick) {
        if (this.coopIsCatalog && (viewType === "coop_tiles" || viewType === "kanban")) {
            setCoopLayout(viewType === "kanban");
            const active = this.env.config.viewSwitcherEntries?.find((view) => view.active);
            if (active?.type === "kanban") {
                // Уже в канбане — меняется только раскладка, перезагружать
                // представление незачем.
                return;
            }
            return super.switchView("kanban", isMiddleClick);
        }
        return super.switchView(viewType, isMiddleClick);
    },
});
