/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { Pager } from "@web/core/pager/pager";
import { CoopTabs } from "@coop_theme/js/shell";
import { CoopFilters } from "@coop_theme/js/catalog_filters";
import { CoopMap } from "@coop_theme/js/catalog_map";
import { coopSort, parseOrder } from "@coop_theme/js/catalog_sort";
import { reactive, useEffect, useState } from "@odoo/owl";

/**
 * Виды каталога в одном переключателе: плиткой, списком, на карте — три
 * из макета — и таблица движка четвёртой.
 *
 * Таблица — отдельное представление Odoo, и его кнопка в переключателе
 * уже есть. Плитка и список — одно представление с разной раскладкой
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
const MODES = ["tiles", "rows", "map"];

export const coopLayout = reactive({
    mode: MODES.includes(readSavedLayout()) ? readSavedLayout() : "tiles",
});

export function setCoopLayout(mode) {
    coopLayout.mode = mode;
    try {
        browser.localStorage.setItem(STORAGE_KEY, mode);
    } catch {
        // Не сохранилось — вид всё равно переключился, просто забудется.
    }
}

export class CoopCatalogKanbanController extends KanbanController {
    // Постраничная навигация рисуется внизу списка, как в макете, а не в
    // панели сверху. Данные берутся те же, что у штатной: представление
    // уже сложило их в настройку экрана, и считать их второй раз значило
    // бы завести второй счётчик, который разойдётся с первым.
    static components = { ...KanbanController.components, Pager, CoopFilters, CoopMap };

    // Кнопка создания подписывается по разделу: «Добавить ресурс»,
    // «Добавить проект». Штатное «Новое» ничего не говорит о том, что
    // именно заводится, а в макете подпись у каждого каталога своя.
    get coopCreateLabel() {
        return this.props.context?.coop_create_label || "Добавить";
    }

    /** Вернуться к плиткам. Нужна карте: выбрав город, человек хочет
     *  увидеть тамошние записи, а не карту с одной оставшейся меткой.
     *  Передаётся карте свойством — своей ссылки на переключатель вида у
     *  неё нет намеренно, иначе модули ссылались бы друг на друга. */
    coopShowTiles() {
        setCoopLayout("tiles");
    }

    setup() {
        super.setup();
        this.coopLayout = useState(coopLayout);
        this.coopSort = useState(coopSort);
        // Перезагружаем список, когда сменили признак сортировки. Через
        // общее состояние, а не через событие: порядок выбирают в панели
        // управления, а перезагружает представление — прямой ссылки
        // между ними у Odoo нет.
        useEffect(
            () => {
                const order = this.coopSort.orders[this.props.resModel];
                if (order) {
                    this.model.load({ orderBy: parseOrder(order) });
                }
            },
            () => [this.coopSort.orders[this.props.resModel]]
        );
    }
}

CoopCatalogKanbanController.template = "coop_theme.CatalogKanbanView";

registry.category("views").add("coop_catalog_kanban", {
    ...kanbanView,
    Controller: CoopCatalogKanbanController,
});

// Вкладки раздела рисуются самой панелью: только так они попадают в одну
// строку с переключателем вида, а поиск с кнопкой добавления — в
// следующую. Отдельным блоком над панелью этого не собрать.
ControlPanel.components = { ...ControlPanel.components, CoopTabs };

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
     * Крошка одна — значит, возвращаться по ней некуда, а её текст
     * повторяет заголовок страницы прямо под ней. Считается по самим
     * крошкам, а не по признаку действия: так полоса пропадает везде,
     * где она пустая, а не только на «Моей странице».
     */
    get coopSingleCrumb() {
        return (this.breadcrumbs?.length || 0) <= 1;
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
            if (entry.type === "list") {
                // «Списком» в макете называется вид карточками во всю
                // ширину, а не таблица движка. Оставить у таблицы то же
                // слово значит поставить в один ряд две кнопки с одной
                // подписью.
                return [{ ...entry, name: "Таблицей", icon: "fa fa-table" }];
            }
            if (entry.type !== "kanban") {
                return [entry];
            }
            return [
                {
                    ...entry,
                    type: "coop_tiles",
                    name: "Плиткой",
                    icon: "oi oi-view-kanban",
                    active: entry.active && coopLayout.mode === "tiles",
                },
                {
                    ...entry,
                    name: "Списком",
                    icon: "fa fa-align-justify",
                    active: entry.active && coopLayout.mode === "rows",
                },
                {
                    ...entry,
                    type: "coop_map",
                    name: "На карте",
                    icon: "fa fa-map-marker",
                    active: entry.active && coopLayout.mode === "map",
                },
            ];
        });
    },

    switchView(viewType, isMiddleClick) {
        const layouts = { coop_tiles: "tiles", kanban: "rows", coop_map: "map" };
        if (this.coopIsCatalog && viewType in layouts) {
            setCoopLayout(layouts[viewType]);
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

// Строка поиска каталога: без штатного выпадающего меню и со своей
// подсказкой. Признак каталога тот же, что у панели управления, — из
// контекста действия.
patch(SearchBar.prototype, {
    get coopIsCatalog() {
        return Boolean(this.env.searchModel?.globalContext?.coop_catalog);
    },

    get coopPlaceholder() {
        return this.coopIsCatalog ? "Начните вводить название" : "Поиск...";
    },
});
