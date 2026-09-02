/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { Pager } from "@web/core/pager/pager";
import { CoopTabs } from "@coop_theme/js/shell";
import { reactive, useEffect, useState } from "@odoo/owl";

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

/**
 * Порядок в каталоге.
 *
 * По умолчанию — сначала новые. Раньше проекты шли по готовности убыв., и
 * первая страница была сплошь стопроцентная: со стороны это выглядело
 * так, будто полоса готовности сломана и всегда полная.
 *
 * Признаки перечислены по разделам: у проекта осмысленна готовность, у
 * сообщества — число участников, у ресурса — цена. Общий список из
 * «названия и даты» не дал бы найти ни самый собранный проект, ни самое
 * людное сообщество.
 */
const SORT_OPTIONS = {
    "coop.project": [
        ["id desc", "Сначала новые"],
        ["name asc", "По названию"],
        ["city asc", "По городу"],
        ["readiness desc", "Сначала собранные"],
        ["readiness asc", "Сначала те, где нужна помощь"],
    ],
    "coop.community": [
        ["id desc", "Сначала новые"],
        ["name asc", "По названию"],
        ["city asc", "По городу"],
        ["member_count desc", "Сначала людные"],
    ],
    "coop.resource": [
        ["id desc", "Сначала новые"],
        ["name asc", "По названию"],
        ["city asc", "По городу"],
    ],
    "coop.skill.offer": [
        ["id desc", "Сначала новые"],
        ["name asc", "По названию"],
        ["city asc", "По городу"],
    ],
    "coop.vacancy": [
        ["id desc", "Сначала новые"],
        ["name asc", "По названию"],
        ["city asc", "По городу"],
    ],
    "coop.deal": [
        ["id desc", "Сначала новые"],
        ["name asc", "По номеру"],
    ],
    "res.partner": [
        ["id desc", "Сначала новые"],
        ["name asc", "По имени"],
        ["city asc", "По городу"],
    ],
};

const DEFAULT_SORT = [["id desc", "Сначала новые"], ["name asc", "По названию"]];

export function coopSortOptionsFor(resModel) {
    return SORT_OPTIONS[resModel] || DEFAULT_SORT;
}

// Выбранный порядок — по разделу: возвращаясь в каталог, человек
// рассчитывает увидеть тот же порядок, а не сброшенный.
export const coopSort = reactive({ orders: {} });

export function setCoopSort(resModel, order) {
    coopSort.orders = { ...coopSort.orders, [resModel]: order };
}

export function parseOrder(order) {
    return order.split(",").map((part) => {
        const [name, direction] = part.trim().split(/\s+/);
        return { name, asc: direction !== "desc" };
    });
}

export class CoopCatalogKanbanController extends KanbanController {
    // Постраничная навигация рисуется внизу списка, как в макете, а не в
    // панели сверху. Данные берутся те же, что у штатной: представление
    // уже сложило их в настройку экрана, и считать их второй раз значило
    // бы завести второй счётчик, который разойдётся с первым.
    static components = { ...KanbanController.components, Pager };

    // Кнопка создания подписывается по разделу: «Добавить ресурс»,
    // «Добавить проект». Штатное «Новое» ничего не говорит о том, что
    // именно заводится, а в макете подпись у каждого каталога своя.
    get coopCreateLabel() {
        return this.props.context?.coop_create_label || "Добавить";
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

    get coopSortOptions() {
        return coopSortOptionsFor(this.env.searchModel?.resModel);
    },

    get coopCurrentSort() {
        const resModel = this.env.searchModel?.resModel;
        return coopSort.orders[resModel] || this.coopSortOptions[0][0];
    },

    onCoopSortChange(event) {
        setCoopSort(this.env.searchModel?.resModel, event.target.value);
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
