/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useRef, useState } from "@odoo/owl";

/**
 * Поиск по платформе в шапке.
 *
 * Ищет по всем каталогам сразу и показывает по нескольку строк из
 * каждого: это навигатор «куда идти», а не список всего найденного. За
 * полным списком — переход в сам каталог с тем же запросом.
 *
 * Запрос уходит с задержкой: без неё на каждую нажатую букву уходит
 * восемь запросов к базе, и выдача мигает быстрее, чем читается.
 */
const DEBOUNCE = 250;

export class CoopSearch extends Component {
    static template = "coop_search.TopbarSearch";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.inputRef = useRef("input");
        this.state = useState({
            term: "",
            open: false,
            busy: false,
            tooShort: false,
            groups: [],
            more: [],
            total: 0,
        });
        this.timer = null;
    }

    onInput(ev) {
        this.state.term = ev.target.value;
        this.state.open = true;
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.lookup(), DEBOUNCE);
    }

    async lookup() {
        const term = this.state.term;
        if (term.trim().length < 3) {
            Object.assign(this.state, {
                tooShort: true, groups: [], more: [], total: 0,
            });
            return;
        }
        this.state.busy = true;
        const result = await this.orm.call("coop.search", "coop_lookup", [term]);
        this.state.busy = false;
        // Пока ходили за ответом, человек мог продолжить печатать —
        // тогда этот ответ уже не про то, что в поле.
        if (result.term !== this.state.term.trim()) {
            return;
        }
        Object.assign(this.state, {
            tooShort: result.tooShort,
            groups: result.groups,
            more: result.more,
            total: result.total || 0,
        });
    }

    async openRecord(row) {
        this.close();
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: row.model,
            res_id: row.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openCatalog(group) {
        this.close();
        const action = await this.orm.call(
            "coop.search", "coop_open_catalog", [group.action, this.state.term]
        );
        await this.action.doAction(action);
    }

    close() {
        this.state.open = false;
    }

    onBlur() {
        // С задержкой: клик по строке выдачи снимает фокус с поля раньше,
        // чем срабатывает сам клик.
        setTimeout(() => this.close(), 150);
    }

    onKeydown(ev) {
        if (ev.key === "Escape") {
            this.close();
        }
    }
}

registry.category("systray").add(
    "coop_search.topbar",
    { Component: CoopSearch },
    // Правее переключателя полномочий и левее значков: в макете поиск
    // стоит первым в правой части шапки.
        // Левее всех остальных: поиск по платформе — первое, зачем
    // человек тянется к шапке, и он не должен стоять за значками
    // чужих модулей.
    { sequence: 100 }
);
