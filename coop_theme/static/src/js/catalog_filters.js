/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { coopSort, coopSortOptionsFor, setCoopSort } from "@coop_theme/js/catalog_sort";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * Панель фильтров каталога — та же, что в макете.
 *
 * Штатная панель Odoo сюда не годится: она берёт фиксированный список
 * полей из разметки и умеет только ссылки и списки значений. Здесь нужны
 * диапазон цены, свободный ввод города и набор полей, зависящий от
 * раздела, — а дальше и от выбранной рубрики.
 *
 * Условия складываются в отдельную часть общего запроса, а не подменяют
 * его целиком: поиск по строке и фильтры должны работать вместе, а не
 * отменять друг друга.
 */
export class CoopFilters extends Component {
    static template = "coop_theme.CatalogFilters";
    static props = { resModel: String };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.groupId = null;
        this.state = useState({
            blocks: [],
            values: {},
            quick: [],
            saved: [],
            savedOpen: false,
            open: false,
        });
        onWillStart(async () => {
            await this.load();
            await this.loadSaved();
        });
    }

    /** Порядок — такое же условие отбора, как остальные, и стоит там же.
     *  В панели управления он спорил за место с поиском и кнопкой
     *  добавления, а по смыслу принадлежит фильтру. */
    get sortOptions() {
        return coopSortOptionsFor(this.props.resModel);
    }

    get currentSort() {
        return coopSort.orders[this.props.resModel] || this.sortOptions[0][0];
    }

    onSortChange(event) {
        setCoopSort(this.props.resModel, event.target.value);
    }

    async load() {
        this.state.blocks = await this.orm.call(
            "coop.catalog", "catalog_filters", [this.props.resModel, this.domain]
        );
    }

    async loadSaved() {
        this.state.saved = await this.orm.call(
            "coop.catalog", "coop_saved_searches", [this.props.resModel]
        );
    }

    /** Домен из всего, что человек выбрал. */
    get domain() {
        const domain = [];
        for (const block of this.state.blocks) {
            const value = this.state.values[block.code];
            if (block.widget === "select" && value) {
                // Условие сравнения задаёт сам блок: у метки значений у
                // записи несколько, и равенство списку не сработает.
                domain.push([block.field, block.operator || "=",
                             this.cast(block, value)]);
            } else if (block.widget === "text" && value) {
                domain.push([block.field, block.operator || "ilike", value]);
            } else if (block.widget === "suggest" && value) {
                domain.push([`${block.field}.name`, "ilike", value]);
            } else if (block.widget === "range") {
                const from = this.state.values[`${block.code}_from`];
                const to = this.state.values[`${block.code}_to`];
                if (from) {
                    domain.push([block.field, ">=", Number(from)]);
                }
                if (to) {
                    domain.push([block.field, "<=", Number(to)]);
                }
            }
        }
        for (const block of this.state.blocks) {
            if (block.widget !== "quick") {
                continue;
            }
            for (const option of block.options) {
                if (this.state.quick.includes(option.value)) {
                    domain.push(...option.domain);
                }
            }
        }
        return domain;
    }

    cast(block, value) {
        // Ссылка приходит из поля выбора строкой; сравнивать её со
        // строкой нельзя — домен по ссылке ждёт число.
        return block.field.endsWith("_id") ? Number(value) : value;
    }

    async apply() {
        // Условия панели живут отдельной группой в штатной модели
        // поиска: так они складываются с поиском по строке, а не
        // заменяют его. Прежнюю группу перед этим снимаем — иначе с
        // каждым щелчком условия копятся.
        const search = this.env.searchModel;
        if (this.groupId) {
            search.deactivateGroup(this.groupId);
            this.groupId = null;
        }
        const domain = this.domain;
        if (domain.length) {
            this.groupId = search.nextGroupId;
            search.createNewFilters([{
                description: "Фильтр каталога",
                domain,
                // Условие уже показано самой панелью; вторая его копия
                // в строке поиска сбивала бы с толку и снималась бы
                // мимо панели, оставляя её в рассогласованном виде.
                invisible: "True",
            }]);
        }
        // Счётчики считаются по остальным условиям, значит после
        // применения они другие.
        await this.load();
    }

    onChange(code, value) {
        this.state.values[code] = value;
        this.apply();
    }

    toggleQuick(value) {
        const index = this.state.quick.indexOf(value);
        if (index === -1) {
            this.state.quick.push(value);
        } else {
            this.state.quick.splice(index, 1);
        }
        this.apply();
    }

    isQuick(value) {
        return this.state.quick.includes(value);
    }

    /** Выбрано ли значение. Сравнение строками: ссылка приходит из поля
     *  выбора текстом, а в состоянии лежит числом.
     *
     *  Отдельным методом, а не выражением в шаблоне: глобального
     *  `String` в шаблонах OWL нет, и вызов из разметки падал. */
    isSelected(block, option) {
        const value = this.state.values[block.code];
        return value !== undefined && `${value}` === `${option.value}`;
    }

    reset() {
        // Рубрика сбрасывается вместе с остальным: в отличие от макета,
        // где она навигация, здесь это такое же поле панели.
        this.state.values = {};
        this.state.quick = [];
        this.apply();
    }

    async saveSearch() {
        const name = window.prompt("Название поиска");
        if (!name) {
            return;
        }
        await this.orm.call("coop.catalog", "coop_save_search",
                            [this.props.resModel, name, this.domain]);
        await this.loadSaved();
        this.notification.add(`Поиск «${name}» сохранён`, { type: "success" });
    }

    async applySaved(saved) {
        this.state.savedOpen = false;
        let domain = [];
        try {
            domain = JSON.parse(saved.domain.replace(/'/g, '"'));
        } catch {
            this.notification.add("Не удалось прочитать сохранённый поиск",
                                  { type: "warning" });
            return;
        }
        const search = this.env.searchModel;
        if (this.groupId) {
            search.deactivateGroup(this.groupId);
        }
        this.groupId = search.nextGroupId;
        search.createNewFilters([{
            description: saved.name, domain, invisible: "True",
        }]);
        await this.load();
    }

    async dropSaved(saved) {
        await this.orm.call("coop.catalog", "coop_drop_search", [saved.id]);
        await this.loadSaved();
    }

    toggleSaved() {
        this.state.savedOpen = !this.state.savedOpen;
    }

    toggleOpen() {
        this.state.open = !this.state.open;
    }
}
