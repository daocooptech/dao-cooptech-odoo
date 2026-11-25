/**
 * Подбор на трудовую потребность (№ 474, решения 692, 697).
 *
 * `coop_need_match` — число подходящих в строке сметы: видит тот, кто
 * ведёт потребность; щелчок открывает окно.
 * `coop_need_matches` — само окно: вкладки «Люди» и «Организации»,
 * карточки предложений, «Пригласить» — извещение хозяину.
 */
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { CoopIcon } from "@coop_theme/js/icons";

export class CoopNeedMatch extends Component {
    static template = "coop_projects.NeedMatch";
    props = useProps(standardFieldProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
    }

    get visible() {
        const data = this.props.record.data;
        return Boolean(data.need_can_decide) && data.state === "published";
    }

    get label() {
        const data = this.props.record.data;
        return data.need_specialization_id ? String(data[this.props.name] || 0) : "указать";
    }

    async open(ev) {
        ev.stopPropagation();
        ev.preventDefault();
        const action = await this.orm.call(
            "coop.resource", "action_open_need_matches", [[this.props.record.resId]]);
        await this.action.doAction(action);
    }
}

registry.category("fields").add("coop_need_match", {
    component: CoopNeedMatch,
    supportedTypes: ["integer"],
    fieldDependencies: [
        { name: "need_can_decide", type: "boolean" },
        { name: "need_specialization_id", type: "many2one", relation: "coop.specialization" },
        { name: "state", type: "selection" },
    ],
});

export class CoopNeedMatches extends Component {
    static template = "coop_projects.NeedMatches";
    static components = { CoopIcon };
    props = useProps(standardFieldProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ tab: null, busy: false, specs: [] });
        onWillStart(async () => {
            this.state.specs = await this.orm.searchRead(
                "coop.specialization", [], ["name"], { order: "name" });
        });
    }

    get data() {
        return this.props.record.data[this.props.name] || { offers: [], can_invite: false };
    }

    get spec() {
        const value = this.props.record.data.need_specialization_id;
        return value ? value.id : 0;
    }

    get people() {
        return this.data.offers.filter((o) => !o.is_company);
    }

    get orgs() {
        return this.data.offers.filter((o) => o.is_company);
    }

    get tab() {
        return this.state.tab || (!this.people.length && this.orgs.length ? "orgs" : "people");
    }

    get offers() {
        return this.tab === "orgs" ? this.orgs : this.people;
    }

    meta(offer) {
        const parts = [offer.name];
        if (offer.city) { parts.push(offer.city); }
        if (offer.experience && offer.experience !== "нет") {
            parts.push("опыт " + offer.experience);
        }
        return parts.join(" · ");
    }

    async run(method, arg) {
        if (this.state.busy) { return; }
        this.state.busy = true;
        try {
            await this.orm.call("coop.resource", method, [[this.props.record.resId], arg]);
            await this.props.record.load();
        } finally {
            this.state.busy = false;
        }
    }

    async setSpec(ev) {
        this.state.tab = null;
        await this.run("action_need_set_specialization", Number(ev.target.value) || false);
    }

    invite(offer) {
        return this.run("action_invite_offer", offer.id);
    }

    openOffer(offer) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "coop.skill.offer",
            res_id: offer.id, views: [[false, "form"]],
        });
    }
}

registry.category("fields").add("coop_need_matches", {
    component: CoopNeedMatches,
    supportedTypes: ["json"],
    fieldDependencies: [
        { name: "need_specialization_id", type: "many2one", relation: "coop.specialization" },
    ],
});
