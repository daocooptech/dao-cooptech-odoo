/**
 * Отклики на потребность в смете проекта (задача 421, владелец 12.11.2026).
 *
 * Тому, кто разбирает заявки (инициатор, ответственный за потребность,
 * уполномоченный организации), — «новых(всего)», «4(8)». Есть новые —
 * число красное и слева глаз. Клик по числу или по глазу ведёт на разбор
 * заявок проекта: отдельной кнопки на своей странице проекта не видно.
 *
 * Остальным — одно число новых откликов, как было: разбирать им нечего.
 *
 * Клик гасится в строке: иначе список потребностей открыл бы саму
 * потребность поверх перехода.
 */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class CoopOfferCounter extends Component {
    static template = "coop_projects.OfferCounter";
    props = useProps(standardFieldProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
    }

    get data() {
        return this.props.record.data;
    }

    get fresh() {
        return this.data[this.props.name] || 0;
    }

    get total() {
        return this.data.need_offer_total || 0;
    }

    get canDecide() {
        return Boolean(this.data.need_can_decide);
    }

    async open(ev) {
        ev.stopPropagation();
        ev.preventDefault();
        const action = await this.orm.call(
            this.props.record.resModel, "action_open_need_offers",
            [[this.props.record.resId]]);
        await this.action.doAction(action);
    }
}

registry.category("fields").add("coop_offer_counter", {
    component: CoopOfferCounter,
    supportedTypes: ["integer"],
    fieldDependencies: [
        { name: "need_offer_total", type: "integer" },
        { name: "need_can_decide", type: "boolean" },
    ],
});
