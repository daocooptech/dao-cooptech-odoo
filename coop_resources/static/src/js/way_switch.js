/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, proxy, useProps } from "@odoo/owl";

/**
 * Способ передачи на витрине ресурса — переключателем `Segmented`.
 *
 * Эталон — `ResourcePage` (решение 625): у каждого способа своя цена, свои
 * условия и своя подпись отклика, и всё это меняется вместе с выбранным
 * способом — человек видит, что именно произойдёт по нажатию. Раньше
 * подпись была одна на объявление, а способы стояли метками рядом.
 *
 * Ставится на `way_cards` (собирает сервер: цена, условия, подпись).
 * Отклик уходит с выбранным способом — окно открывается уже на нём.
 */
export class CoopWaySwitch extends Component {
    static template = "coop_resources.WaySwitch";
    props = useProps(standardFieldProps);

    setup() {
        this.action = useService("action");
        this.state = proxy({ id: false });
    }

    get data() {
        return this.props.record.data;
    }

    get cards() {
        return this.data.way_cards || [];
    }

    get current() {
        return this.cards.find((card) => card.id === this.state.id) || this.cards[0] || false;
    }

    // Как кнопка формы `type="object"`: через `call_button`, который сам
    // дополняет окно видами. Голый `orm.call` вернул бы окно без них.
    call(name, context = {}) {
        return this.action.doActionButton({
            type: "object",
            name,
            resModel: "coop.resource",
            resId: this.props.record.resId,
            context,
            onClose: () => this.props.record.load(),
        });
    }

    respond() {
        return this.call("action_respond", { coop_method_id: this.current.id });
    }

    message() {
        return this.call("action_message_owner");
    }
}

registry.category("fields").add("coop_way_switch", {
    component: CoopWaySwitch,
    supportedTypes: ["json"],
    fieldDependencies: [
        { name: "bargain", type: "boolean" },
        { name: "can_respond", type: "boolean" },
        { name: "price_display", type: "char" },
    ],
});
