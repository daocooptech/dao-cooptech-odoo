/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";

/**
 * Плашка «Вы вошли как …» (решение 450, вход за любого).
 *
 * Пока администратор смотрит площадку глазами другого человека, это
 * должно быть видно всегда: иначе через минуту забываешь, под кем сидишь,
 * и пишешь сообщение или подтверждаешь акт от чужого имени. Возврат —
 * обычной ссылкой: сервер сам вернёт того, кто входил.
 */
export class CoopLoginAsBadge extends Component {
    static template = "coop_admin.LoginAsBadge";
    props = useProps();

    setup() {
        this.boot = useService("coopBoot");
        this.state = proxy({ info: null });
        onWillStart(async () => {
            this.state.info = (await this.boot.get()).login_as || null;
        });
    }
}

registry.category("systray").add(
    "coop_admin.login_as",
    { Component: CoopLoginAsBadge },
    // Левее переключателя администратора: это главное, что нужно помнить.
    { sequence: 5 }
);
