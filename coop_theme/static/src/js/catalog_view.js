/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { useState } from "@odoo/owl";

/**
 * Переключатель вида каталога: плиткой или строками.
 *
 * В макете у каталогов два вида в одном списке — плитка по умолчанию и
 * строка по кнопке, — и выбор запоминается на все каталоги сразу. В Odoo
 * второго канбана в одном действии не бывает, поэтому разметка карточки
 * одна, а вид переключается классом на корне — ровно как в прототипе,
 * где переключался класс `tile-mode`.
 *
 * Третий вид, список, даёт сам Odoo своим переключателем. Итого три:
 * плиткой, строками, списком.
 */
const STORAGE_KEY = "coop-catalog-view";

export class CoopCatalogKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.coopLayout = useState({ rows: this.readSavedLayout() === "rows" });
    }

    readSavedLayout() {
        // localStorage может быть недоступен — в приватном окне или при
        // запрете хранилища. Тогда просто плитка, как по умолчанию.
        try {
            return browser.localStorage.getItem(STORAGE_KEY);
        } catch {
            return null;
        }
    }

    setCoopLayout(rows) {
        this.coopLayout.rows = rows;
        try {
            browser.localStorage.setItem(STORAGE_KEY, rows ? "rows" : "tiles");
        } catch {
            // Не сохранилось — вид всё равно переключился, просто забудется.
        }
    }
}

CoopCatalogKanbanController.template = "coop_theme.CatalogKanbanView";

registry.category("views").add("coop_catalog_kanban", {
    ...kanbanView,
    Controller: CoopCatalogKanbanController,
});
