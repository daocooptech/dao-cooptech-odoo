/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, proxy, useProps } from "@odoo/owl";
import { CoopIcon } from "@coop_theme/js/icons";

/**
 * «Показать номер» в карточке владельца (эталон `OwnerCard`, владелец
 * 10.11.2026). Номер приходит с сервера по нажатию и встаёт на место
 * кнопки ссылкой `tel:` — на телефоне по ней сразу звонят.
 *
 * Ставится на `owner_has_phone`; без номера или при «Только сообщения»
 * поле ложно, и кнопку скрывает вид.
 */
export class CoopPhoneReveal extends Component {
    static template = "coop_resources.PhoneReveal";
    static components = { CoopIcon };
    props = useProps(standardFieldProps);

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ phone: false, loading: false });
    }

    get tel() {
        return "tel:" + (this.state.phone || "").replace(/[^\d+]/g, "");
    }

    async reveal() {
        this.state.loading = true;
        try {
            this.state.phone = await this.orm.call(
                this.props.record.resModel, "coop_owner_phone", [[this.props.record.resId]]);
        } finally {
            this.state.loading = false;
        }
    }
}

registry.category("fields").add("coop_phone_reveal", {
    component: CoopPhoneReveal,
    supportedTypes: ["boolean"],
});
