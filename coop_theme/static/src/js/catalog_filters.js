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
            // Сколько найдётся, если применить набранное. Показывается
            // на кнопке: иначе «Показать результаты» — прыжок в темноту.
            preview: null,
            dirty: false,
            // Выбранный, но ещё не применённый порядок. Хранится здесь, а
            // не сразу в общем состоянии вида: порядок — такое же поле
            // панели, как остальные, и применяется той же кнопкой.
            order: null,
        });
        onWillStart(async () => {
            await this.load();
            await this.loadSaved();
            // Число на кнопке считается сразу, а не после первого
            // щелчка по полю: пустая «Показать результаты» над полным
            // каталогом читается как кнопка, которой нечего показать.
            await this.countNow();
        });
    }

    /** Порядок — такое же условие отбора, как остальные, и стоит там же.
     *  В панели управления он спорил за место с поиском и кнопкой
     *  добавления, а по смыслу принадлежит фильтру. */
    get sortOptions() {
        return coopSortOptionsFor(this.props.resModel);
    }

    get currentSort() {
        return this.state.order
            || coopSort.orders[this.props.resModel]
            || this.sortOptions[0][0];
    }

    /** Порядок запоминается, но не применяется сам.
     *
     *  Применялся сразу — и панель вела себя по-разному в соседних
     *  строках: список мгновенно перестраивался от «Сортировки» и не
     *  двигался от «Города», пока не нажмёшь кнопку. Со стороны это
     *  читается как поломка второго поля, а не как разница в цене
     *  запроса. */
    onSortChange(event) {
        this.state.order = event.target.value;
        this.state.dirty = true;
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
        // Порядок ставится первым: он меняет запрос представления, а не
        // условия отбора, и обе перезагрузки должны сойтись на одном
        // наборе, а не спорить за последнюю.
        if (this.state.order) {
            setCoopSort(this.props.resModel, this.state.order);
            this.state.order = null;
        }
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
        this.state.dirty = false;
        // Счётчики считаются по остальным условиям, значит после
        // применения они другие.
        await this.load();
    }

    onChange(code, value) {
        this.state.values[code] = value;
        this.previewCount();
    }

    toggleQuick(value) {
        const index = this.state.quick.indexOf(value);
        if (index === -1) {
            this.state.quick.push(value);
        } else {
            this.state.quick.splice(index, 1);
        }
        this.previewCount();
    }

    /**
     * Сколько найдётся с набранными условиями.
     *
     * Раньше каждое изменение поля применяло фильтр целиком: список
     * перезагружался, а счётчики у всех полей выбора пересчитывались
     * отдельным запросом на каждое поле. На рубрике с десятком
     * характеристик это десяток запросов на один щелчок, и каталог
     * заметно вставал.
     *
     * Теперь щелчок стоит один дешёвый подсчёт, да и тот не сразу:
     * пока человек щёлкает подряд, считать промежуточные наборы
     * незачем.
     */
    previewCount() {
        this.state.dirty = true;
        clearTimeout(this.previewTimer);
        this.previewTimer = setTimeout(() => this.countNow(), 400);
    }

    /** Пересчитать число на кнопке немедленно. */
    async countNow() {
        try {
            this.state.preview = await this.orm.searchCount(
                this.props.resModel, this.domain);
        } catch {
            this.state.preview = null;
        }
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

    async reset() {
        // Рубрика сбрасывается вместе с остальным: в отличие от макета,
        // где она навигация, здесь это такое же поле панели.
        clearTimeout(this.previewTimer);
        this.state.values = {};
        this.state.quick = [];
        // Порядок сбрасывается вместе с полями: он такое же поле панели,
        // и «Сбросить», оставляющее половину набранного, — обман.
        this.state.order = this.sortOptions[0][0];
        await this.apply();
        // Число на кнопке после сброса — это весь каталог, а не прочерк:
        // сброс тем и делают, чтобы увидеть всё.
        await this.countNow();
    }

    /** Применить набранное и, на узком экране, свернуть панель. */
    async showResults() {
        clearTimeout(this.previewTimer);
        await this.apply();
        if (this.state.open) {
            this.state.open = false;
        }
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
        // Условие приходит с сервера уже разобранным списком. Раньше оно
        // приходило записью Python и чинилось здесь заменой апострофов на
        // кавычки: на первом же значении с апострофом внутри, на `True`
        // или на `None` такой разбор ломался, и поиск молча не применялся.
        const domain = saved.domain;
        if (!Array.isArray(domain)) {
            this.notification.add("Не удалось прочитать сохранённый поиск",
                                  { type: "warning" });
            return;
        }
        const search = this.env.searchModel;
        if (this.groupId) {
            search.deactivateGroup(this.groupId);
        }
        this.groupId = search.nextGroupId;
        // Условие сохранённого поиска показывается в строке поиска, в
        // отличие от условий панели: полей панели оно не заполняет, и без
        // видимой отметки выдача менялась молча — снять её было нечем.
        search.createNewFilters([{ description: saved.name, domain }]);
        await this.load();
        await this.countNow();
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
