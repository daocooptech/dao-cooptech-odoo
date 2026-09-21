/** @odoo-module **/

import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban/kanban_view";
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
export class CoopExtensionKanbanController extends CoopCatalogKanbanController {}

CoopExtensionKanbanController.template = "coop_extensions.ExtensionKanbanView";

registry.category("views").add("coop_extension_kanban", {
    ...kanbanView,
    Controller: CoopExtensionKanbanController,
});
