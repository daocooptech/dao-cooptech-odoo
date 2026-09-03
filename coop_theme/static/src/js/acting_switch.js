/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * Выбор, от чьего имени человек действует, — в меню под аватаром.
 *
 * Раньше это был отдельный список в боковом меню, а рядом, в шапке,
 * движок показывал название компании. Два списка организаций в разных
 * углах экрана отвечали на один вопрос разными словами, и понять, чем
 * они отличаются, было нельзя.
 *
 * Теперь выбор один и лежит там, где его ищут, — под своим аватаром,
 * рядом с выходом и настройками. Строки — с фотографией и названием:
 * человека и кооператив различают в лицо, а не по строчке текста.
 */
export class CoopActingMenu extends Component {
    static template = "coop_theme.ActingMenu";
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
            // Права или сеть — выбора просто не будет, меню от этого не
            // ломается.
            this.state.actors = [];
        }
    }

    avatar(actor) {
        return `/web/image/res.partner/${actor.id}/avatar_128`;
    }

    async select(actor) {
        if (actor.id === this.state.acting) {
            return;
        }
        await this.orm.call("coop.shell", "set_acting", [actor.id]);
        // Перезагрузка целиком: от имени зависит почти всё на экране —
        // своя страница, кошелёк, каталоги «мои». Досчитывать это по
        // кусочкам значило бы держать вторую копию тех же правил.
        window.location.reload();
    }
}

// Первым в меню: это ответ на вопрос «кто я сейчас», а он предшествует
// всему остальному — настройкам, справке и выходу.
registry.category("user_menuitems").add("coop_theme.acting", () => ({
    type: "component",
    contentComponent: CoopActingMenu,
    sequence: 1,
}));

// Переключатель компаний движка убран: он отвечает на тот же вопрос
// «от чьего имени я работаю», но словами учётной системы, и рядом с
// нашим выглядел вторым, непонятно чем отличающимся списком.
registry.category("systray").remove("SwitchCompanyMenu");
