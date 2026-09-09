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
import { CoopShelves } from "@coop_theme/js/catalog_shelves";
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
    static components = { ...KanbanController.components, Pager, CoopFilters, CoopMap, CoopShelves };

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

    /** По какому полю раскладывать полки. Объявляется в действии
     *  каталога (`coop_shelf_field` в контексте), а не угадывается: у
     *  каждого раздела своя рубрикация, и промах здесь виден сразу всем.
     *  Не объявлено — полок нет, каталог работает как раньше. */
    get coopShelfField() {
        return this.props.context?.coop_shelf_field || false;
    }

    /** Полки только на чистом экране: без поиска, без отбора, без
     *  группировки и только в плитке. В списке витрина по рубрикам
     *  спорит с самим списком. */
    get coopShelvesVisible() {
        // Условие нарочно короткое: признак в действии и режим плитки.
        //
        // Раньше сюда входила ещё проверка «в поиске ничего не выбрано»
        // через searchModel.facets — и полки не появлялись вовсе. Проверять
        // это условие снаружи оказалось нечем: Owl не отдаёт внутренности
        // компонента, а консоль расширения до них не доходит. Значит либо
        // фасеты там не пусты по причине, которую отсюда не видно, либо
        // обращение к searchModel в этот момент роняет геттер. Поэтому
        // условие оставлено тем, что можно проверить глазами, а скрытие
        // полок при поиске сделано ниже — по строке запроса.
        return Boolean(this.coopShelfField) && this.coopLayout.mode === "tiles";
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
     * Строка вкладок нужна не только каталогам.
     *
     * Раньше она показывалась ровно там, где стоял признак каталога, и
     * это совпадало: разделы платформы были каталогами. С «Токеномикой»
     * совпадение кончилось — у неё четыре вкладки поверх обычных списков
     * и ни одного каталога, и вкладки просто не появились. Ошибки при
     * этом не было никакой: признака нет — рисовать нечего.
     *
     * Поэтому признак заведён свой: `coop_section` значит «экран раздела
     * платформы», а `coop_catalog` — «и вдобавок каталог с плитками и
     * переключателем вида». Второе по-прежнему включает первое, но
     * первое больше не требует второго.
     */
    get coopHasTabs() {
        const context = this.env.searchModel?.globalContext || {};
        return Boolean(context.coop_catalog || context.coop_section);
    },

    /**
     * Крошка одна — значит, возвращаться по ней некуда, а её текст
     * повторяет заголовок страницы прямо под ней. Считается по самим
     * крошкам, а не по признаку действия: так полоса пропадает везде,
     * где она пустая, а не только на «Моей странице».
     *
     * Каталог исключён, и это не мелочь. Признак вешает класс, который
     * снимает у полосы всё, чем она видна, — поля, границу, фон и
     * промежутки, причём через `!important`. Для пустой полосы это
     * верно, а у каталога в ней живут вкладки раздела, поиск, кнопка
     * добавления и переключатель вида: крошка там тоже одна, и все они
     * слипались в сплошную строку без единого промежутка. Отсюда шли
     * нули в замерах: вкладки вплотную к полю поиска, поле вплотную к
     * кнопке.
     */
    get coopSingleCrumb() {
        return !this.coopIsCatalog && (this.breadcrumbs?.length || 0) <= 1;
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
