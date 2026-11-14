/**
 * Разбор заявок в «Управлении проектом» (образец OffersReviewPage, задача
 * 395, владелец 14.11.2026): слева потребности со счётчиками, справа
 * карточки заявок выбранной. «Принять» и «Отклонить» — прежние действия
 * вклада (`action_accept`, `action_decline`): права и извещения те же.
 */
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
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
        this.action = useService("action");
        this.state = proxy({ need: null, filter: "all", sort: "new", busy: false, resources: {} });
        onWillStart(() => this.loadResources());
    }

    /** Ресурс заявки — карточкой с фото (владелец 14.11.2026): связь
     *  `resource_id` берём у вклада, в JSON проекта её нет. */
    async loadResources() {
        const ids = this.data.offers.map((o) => o.id);
        if (!ids.length) { return; }
        const rows = await this.orm.read("coop.project.contribution", ids, ["resource_id"]);
        const map = {};
        for (const r of rows) {
            if (r.resource_id) {
                const [id, name] = Array.isArray(r.resource_id)
                    ? r.resource_id : [r.resource_id.id, r.resource_id.display_name];
                map[r.id] = { id, name };
            }
        }
        this.state.resources = map;
    }

    openResource(id) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "coop.resource",
            res_id: id, views: [[false, "form"]],
        });
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

    /** «сегодня», «вчера», «3 дня назад»; старше месяца — числом. */
    ago(iso) {
        if (!iso) { return ""; }
        const then = new Date(iso + "T00:00:00");
        const now = new Date();
        now.setHours(0, 0, 0, 0);
        const days = Math.round((now - then) / 86400000);
        if (days <= 0) { return "сегодня"; }
        if (days === 1) { return "вчера"; }
        if (days > 30) {
            return then.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
        }
        const n10 = days % 10, n100 = days % 100;
        const word = n10 === 1 && n100 !== 11 ? "день"
            : n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14) ? "дня" : "дней";
        return `${days} ${word} назад`;
    }

    /** Свежая заявка — точка у даты, как в образце: не старше трёх дней. */
    fresh(offer) {
        if (offer.state !== "offered" || !offer.offered_on) { return false; }
        return (Date.now() - new Date(offer.offered_on + "T00:00:00")) < 4 * 86400000;
    }

    pct(value) {
        return String(value).replace(".", ",");
    }

    stars(rating) {
        const on = Math.round(rating || 0);
        return [1, 2, 3, 4, 5].map((i) => i <= on);
    }

    diffText(offer) {
        if (!offer.need_price) { return offer.diff_label; }
        return Math.round(offer.diff) === 0 ? "как в потребности" : offer.diff_label;
    }

    diffClass(offer) {
        if (!offer.need_price || Math.round(offer.diff) === 0) { return ""; }
        return offer.diff > 0 ? "up" : "dn";
    }

    /** «Написать» — личный чат с откликнувшимся, тот же, что из карточки человека. */
    async write(offer) {
        const store = this.env.services["mail.store"];
        if (store) {
            await store.openChat({ partnerId: offer.partner_id });
        }
    }

    openPartner(offer) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "res.partner",
            res_id: offer.partner_id, views: [[false, "form"]],
        });
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
            await this.loadResources();
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
