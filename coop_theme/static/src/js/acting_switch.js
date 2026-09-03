/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * «Действую от имени» — в шапке, рядом с аватаром.
 *
 * Раньше он стоял в боковом меню, а в шапке движок показывал название
 * компании. Получалось два списка организаций в разных углах экрана, и
 * было непонятно, чем они отличаются и который из них главный.
 *
 * Остаётся один, и стоит он там, где у любого сайта стоит «кто я
 * сейчас»: у аватара. Компания движка оттуда убрана — на платформе
 * человек действует от своего имени или от имени организации, в которой
 * состоит, а не «переключает компанию» в учётной системе.
 */
export class CoopActingSwitch extends Component {
    static template = "coop_theme.ActingSwitch";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.state = useState({ actors: [], acting: null });
        onWillStart(() => this.load());
    }

    async load() {
        try {
            const info = await this.orm.call("coop.shell", "acting_options", []);
            this.state.actors = info.options || [];
            this.state.acting = info.current || null;
        } catch {
            // Права или сеть — переключатель просто не показывается,
            // страница от этого не ломается.
            this.state.actors = [];
        }
    }

    /** Имя того, от кого человек действует сейчас. */
    get currentName() {
        const actor = this.state.actors.find((one) => one.id === this.state.acting);
        return actor ? actor.name : "";
    }

    async setActing(value) {
        const id = Number(value);
        if (!id || id === this.state.acting) {
            return;
        }
        await this.orm.call("coop.shell", "set_acting", [id]);
        // Перезагрузка целиком: от имени зависит почти всё на экране —
        // своя страница, кошелёк, каталоги «мои». Досчитывать это по
        // кусочкам значило бы держать вторую копию тех же правил.
        window.location.reload();
    }
}

// Правее переключателя темы и поиска, левее аватара — на месте, где
// движок показывал компанию.
registry.category("systray").add(
    "coop_theme.acting_switch", { Component: CoopActingSwitch }, { sequence: 1 }
);

// Переключатель компаний движка убран: он отвечает на тот же вопрос
// «от чьего имени я работаю», но словами учётной системы, и рядом с
// нашим выглядел вторым, непонятно чем отличающимся списком.
registry.category("systray").remove("SwitchCompanyMenu");
