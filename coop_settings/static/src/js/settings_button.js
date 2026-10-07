/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, usePlugin, useProps } from "@odoo/owl";
import { ActionPlugin } from "@web/webclient/actions/action_plugin";

/**
 * Шестерёнка настроек в шапке.
 *
 * В макете она там и стоит — и стоит на всех 66 страницах, рядом с
 * поиском и колоколом. На движке её не было вовсе: настройки участника
 * было попросту неоткуда открыть, и владелец 16 сентября 2026 сказал, что
 * страницы настроек в макете нет, — он искал её в боковом меню.
 *
 * Со сбросом следа: настройки — не углубление в раздел, откуда пришли, а
 * выход из него. Иначе путь копит цепочку «каталог → запись → настройки».
 */
export class CoopSettingsButton extends Component {
    static template = "coop_settings.Button";
    props = useProps();

    setup() {
        this.action = usePlugin(ActionPlugin);
    }

    open() {
        return this.action.doAction("coop_settings.action_coop_settings", {
            clearBreadcrumbs: true,
        });
    }
}

registry.category("systray").add(
    "coop_settings.button",
    { Component: CoopSettingsButton },
    // Рядом с колоколом и тумблером темы: это органы управления собой, а
    // не уведомления о чужих действиях.
    { sequence: 14 }
);
