/**
 * Переключатель валюты вкладки «Фиат» — образец `CurrencySwitch` из
 * дизайн-системы (задача 400).
 *
 * Положение «Все» и валюты, где у участника есть счета или операции;
 * остальные — под «Ещё N» со списком и поиском по коду и стране. Подписи —
 * коды, не знаки: у BYN и ETB знак один. Выбор не сохраняется между
 * сеансами: на входе всегда «Все».
 *
 * Поле-виджет над строкой: значение — «all» или код валюты. Список валют
 * приходит в соседнем поле «<имя>_items» строкой JSON:
 * [{"code": "CNY", "country": "Китай", "shown": true}, …].
 */
import { Component, onMounted, onPatched, proxy, signal, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export const ALL = "all";

export class CoopCurrencySwitch extends Component {
    static template = "coop_wallet.CurrencySwitch";
    props = useProps(standardFieldProps);

    setup() {
        this.state = proxy({ open: false, query: "", cursor: 0, pinned: [] });
        this.scroller = signal.ref();
        this.moreButton = signal.ref();
        this.search = signal.ref();
        this.needFocus = false;
        onMounted(() => this.syncScroll());
        onPatched(() => this.syncScroll());
    }

    get items() {
        // Список валют — в соседнем поле с суффиксом `_items`.
        const raw = this.props.record.data[this.props.name + "_items"];
        try {
            const list = JSON.parse(raw || "[]");
            return Array.isArray(list) ? list : [];
        } catch {
            return [];
        }
    }

    get value() {
        return this.props.record.data[this.props.name] || ALL;
    }

    /** Ряд: у кого есть счета или операции, закреплённые из «Ещё» и выбранная. */
    get row() {
        return this.items.filter(
            (item) =>
                item.shown ||
                this.state.pinned.includes(item.code) ||
                item.code === this.value
        );
    }

    get rest() {
        const inRow = new Set(this.row.map((item) => item.code));
        return this.items.filter((item) => !inRow.has(item.code));
    }

    get found() {
        const needle = this.state.query.trim().toLowerCase();
        return this.rest.filter(
            (item) =>
                !needle ||
                item.code.toLowerCase().includes(needle) ||
                (item.country || "").toLowerCase().includes(needle)
        );
    }

    get tabs() {
        return [{ code: ALL, label: "Все" }].concat(
            this.row.map((item) => ({ code: item.code, label: item.code }))
        );
    }

    async pick(code) {
        await this.props.record.update({ [this.props.name]: code });
    }

    toggleMore() {
        this.state.open = !this.state.open;
        this.state.cursor = 0;
        this.state.query = "";
        this.needFocus = this.state.open;
    }

    onSearch(ev) {
        this.state.query = ev.target.value;
        this.state.cursor = 0;
    }

    async choose(item) {
        if (!this.state.pinned.includes(item.code)) {
            this.state.pinned = this.state.pinned.concat(item.code);
        }
        this.state.open = false;
        this.state.query = "";
        await this.pick(item.code);
        this.moreButton()?.focus();
    }

    onKeydown(ev) {
        const count = this.found.length;
        if (ev.key === "Escape") {
            this.state.open = false;
            this.moreButton()?.focus();
        } else if (ev.key === "ArrowDown") {
            ev.preventDefault();
            this.state.cursor = Math.min(this.state.cursor + 1, count - 1);
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            this.state.cursor = Math.max(this.state.cursor - 1, 0);
        } else if (ev.key === "Enter" && this.found[this.state.cursor]) {
            ev.preventDefault();
            this.choose(this.found[this.state.cursor]);
        }
    }

    /** Активное положение — в видимую область, затухание — только у скрытых краёв. */
    syncScroll() {
        if (this.needFocus && this.search()) {
            this.search().focus();
            this.needFocus = false;
        }
        const el = this.scroller();
        if (!el) {
            return;
        }
        el.querySelector(".o_coop_cursw_on")?.scrollIntoView({
            inline: "nearest",
            block: "nearest",
        });
        el.style.setProperty("--cs-l", el.scrollLeft > 4 ? "18px" : "0px");
        el.style.setProperty(
            "--cs-r",
            el.scrollLeft + el.clientWidth < el.scrollWidth - 4 ? "18px" : "0px"
        );
    }
}

registry.category("fields").add("coop_currency_switch", {
    component: CoopCurrencySwitch,
    supportedTypes: ["char"],
});
