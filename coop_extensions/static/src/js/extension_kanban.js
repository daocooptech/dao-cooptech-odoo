/** @odoo-module **/

import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { CoopCatalogKanbanController } from "@coop_theme/js/catalog_view";

/**
 * Каталог расширений с панелью отбора.
 *
 * Панель — общая, платформенная: поля объявляет сама модель
 * (`_coop_catalog_filters`), а рисует и считает по ним тема. Отдельный
 * вид нужен затем, что общий вид каталога везёт с собой ещё и
 * переключатель «плиткой / списком / на карте», полки по рубрикам и
 * плиточную геометрию карточки в 200 точек. Расширениям из этого нужен
 * только отбор: карты у модуля нет и быть не может, полки заменяет
 * порядок по разделу, а карточка у каталога своя — со значком слева,
 * собранная неделю назад по остальным плиткам.
 *
 * Поэтому берётся поведение общего каталога (отбор, порядок, домен
 * раздела, подпись кнопки создания), а разметка — своя: штатная
 * канбановая плюс панель сбоку.
 */
// Кнопки, после которых меняется боковое меню. Страница при этом не
// перезагружается: каталог перечитывает карточку сам и сохраняет отбор, а
// меню перечитывается по событию (владелец 19.10.2026: фильтры сбрасывались).
const MENU_BUTTONS = ["action_coop_connect", "action_coop_disconnect"];

function refreshMenu(env, clickParams) {
    if (MENU_BUTTONS.includes(clickParams?.name)) {
        env.bus.trigger("COOP_SIDEBAR_CHANGED");
    }
}

export class CoopExtensionKanbanController extends CoopCatalogKanbanController {
    async afterExecuteActionButton(clickParams) {
        await super.afterExecuteActionButton(clickParams);
        refreshMenu(this.env, clickParams);
    }
}

export class CoopExtensionFormController extends FormController {
    async afterExecuteActionButton(clickParams) {
        await super.afterExecuteActionButton(clickParams);
        refreshMenu(this.env, clickParams);
    }
}

CoopExtensionKanbanController.template = "coop_extensions.ExtensionKanbanView";

registry.category("views").add("coop_extension_kanban", {
    ...kanbanView,
    Controller: CoopExtensionKanbanController,
});

registry.category("views").add("coop_extension_form", {
    ...formView,
    Controller: CoopExtensionFormController,
});
