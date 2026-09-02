/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * Переключатель административных полномочий в правом верхнем углу.
 *
 * Показывается только тому, кому полномочия выданы решением команды.
 * Остальные его не видят вовсе: неактивный переключатель у человека без
 * полномочий сообщал бы, что такая кнопка вообще бывает, и порождал бы
 * вопрос «а почему у меня не работает».
 *
 * После переключения страница перезагружается. Состав групп читается один
 * раз при входе — без перезагрузки меню и права остались бы прежними, и
 * человек решил бы, что переключатель сломан.
 */
export class CoopAdminSwitch extends Component {
    static template = "coop_admin.AdminSwitch";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.state = useState({ granted: false, active: false, busy: false });
        onWillStart(async () => {
            const result = await this.orm.call("res.users", "coop_admin_state", []);
            Object.assign(this.state, result);
        });
    }

    async toggle() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        await this.orm.call("res.users", "coop_admin_toggle", []);
        browser.location.reload();
    }
}

registry.category("systray").add(
    "coop_admin.switch",
    { Component: CoopAdminSwitch },
    // Левее прочих значков: это не уведомление, а режим работы, и стоять
    // он должен там, где его видно всегда.
    { sequence: 1 }
);
