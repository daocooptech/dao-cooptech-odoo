/**
 * Разбор заявок в «Управлении проектом» (образец OffersReviewPage, задача
 * 395, владелец 14.11.2026): слева потребности со счётчиками, справа
 * карточки заявок выбранной. «Принять» и «Отклонить» — прежние действия
 * вклада (`action_accept`, `action_decline`): права и извещения те же.
 */
import { Component, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { CoopIcon } from "@coop_theme/js/icons";

/** Сортировка заявок — кнопкой со списком, без подписи (владелец 14.11.2026). */
const SORT_OPTIONS = [
    { id: "new", label: "Новые", hint: "сначала свежие заявки" },
    { id: "value", label: "Оценка", hint: "сначала с большей оценкой вклада" },
    { id: "trust", label: "Доверие", hint: "сначала с большим доверием" },
];

export class CoopOffersReview extends Component {
    static template = "coop_projects.OffersReview";
    static components = { Dropdown, DropdownItem, CoopIcon };
    sortOptions = SORT_OPTIONS;
    props = useProps(standardFieldProps);

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.state = proxy({ need: null, filter: "all", sort: "new", busy: false });
    }

    get data() {
        return this.props.record.data[this.props.name] || { needs: [], offers: [] };
    }

    get needs() {
        return this.data.needs;
    }

    get currentNeed() {
        const needs = this.needs;
        return needs.find((n) => n.id === this.state.need)
            || needs.find((n) => n.new) || needs.find((n) => n.total) || needs[0];
    }

    get offersOfNeed() {
        const need = this.currentNeed;
        return need ? this.data.offers.filter((o) => o.need_id === need.id) : [];
    }

    get counts() {
        const list = this.offersOfNeed;
        return {
            all: list.length,
            new: list.filter((o) => o.state === "offered").length,
            declined: list.filter((o) => o.state === "declined").length,
        };
    }

    get sortLabel() {
        return (SORT_OPTIONS.find((o) => o.id === this.state.sort) || SORT_OPTIONS[0]).label;
    }

    get offers() {
        let list = this.offersOfNeed;
        if (this.state.filter === "new") {
            list = list.filter((o) => o.state === "offered");
        } else if (this.state.filter === "declined") {
            list = list.filter((o) => o.state === "declined");
        }
        const by = this.state.sort;
        return [...list].sort((a, b) => {
            if (by === "value") { return b.value - a.value; }
            if (by === "trust") { return b.trust - a.trust; }
            return (a.state !== "offered") - (b.state !== "offered") || b.id - a.id;
        });
    }

    money(value, symbol) {
        return value.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
            + " " + (symbol || "");
    }

    day(iso) {
        if (!iso) { return ""; }
        return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
    }

    diffClass(offer) {
        if (!offer.need_price) { return "text-muted"; }
        return offer.diff > 0 ? "text-danger" : "text-success";
    }

    pick(id) {
        this.state.need = id;
    }

    async act(offer, method) {
        if (this.state.busy) { return; }
        this.state.busy = true;
        try {
            await this.orm.call("coop.project.contribution", method, [[offer.id]]);
            await this.props.record.load();
        } finally {
            this.state.busy = false;
        }
    }

    accept(offer) {
        this.dialog.add(ConfirmationDialog, {
            title: "Принять предложение?",
            body: "Потребность закроется, остальные предложения по ней отклонятся сразу, откликнувшиеся получат извещение.",
            confirmLabel: "Принять",
            confirm: () => this.act(offer, "action_accept"),
            cancel: () => {},
        });
    }

    decline(offer) {
        return this.act(offer, "action_decline");
    }
}

registry.category("fields").add("coop_offers_review", {
    component: CoopOffersReview,
    supportedTypes: ["json"],
});
