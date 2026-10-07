/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { WebClient } from "@web/webclient/webclient";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";

/**
 * Полоса «Вы вошли как …» под шапкой (решение 450, вход за любого).
 *
 * Пока администратор смотрит площадку глазами другого человека, это
 * должно быть видно всегда: иначе через минуту забываешь, под кем сидишь,
 * и пишешь сообщение или подтверждаешь акт от чужого имени. Сначала она
 * стояла значком в шапке, но там тесно: шапка не сжимается, и полное имя
 * выдавливало страницу вбок. Владелец 07.10.2026: «если там мало места
 * можно разместить эту надпись под шапкой».
 */
export class CoopLoginAsBar extends Component {
    static template = "coop_admin.LoginAsBar";
    props = useProps();

    setup() {
        this.boot = useService("coopBoot");
        this.state = proxy({ info: null });
        onWillStart(async () => {
            this.state.info = (await this.boot.get()).login_as || null;
        });
    }
}

patch(WebClient, {
    components: { ...WebClient.components, CoopLoginAsBar },
});
