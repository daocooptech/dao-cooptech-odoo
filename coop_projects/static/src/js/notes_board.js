/** @odoo-module **/

import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { CoopCatalogKanbanController } from "@coop_theme/js/catalog_view";

/**
 * Доска заметок с платформенной панелью «Фильтр» (владелец 26.11.2026:
 * «фильтры на платформе имеют другой вид»). Как у каталога расширений:
 * поведение каталога — отбор, подпись кнопки, — а разметка штатная, без
 * полок и переключателя «плиткой / на карте».
 */
export class CoopNotesKanbanController extends CoopCatalogKanbanController {}
CoopNotesKanbanController.template = "coop_projects.NotesKanbanView";

registry.category("views").add("coop_notes_kanban", {
    ...kanbanView,
    Controller: CoopNotesKanbanController,
});
