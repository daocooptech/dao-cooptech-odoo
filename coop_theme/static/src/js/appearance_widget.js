/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { readCoopThemeChoice, setCoopThemeChoice } from "@coop_theme/js/theme_switch";
import { coopLayout, setCoopLayout } from "@coop_theme/js/catalog_view";

/**
 * Оформление: тема и вид каталогов.
 *
 * Не поля записи, а виджет представления: и то и другое живёт в
 * браузере, на каждом устройстве своё. Перенести их в учётную запись
 * значило бы, что выбранная на ночном телефоне тёмная тема встречает
 * человека утром за рабочим столом.
 *
 * Поэтому и «Сохранить» здесь нет: выбранное применяется сразу — как в
 * макете (`settings.html`, вкладка «Оформление»).
 */
export class CoopAppearance extends Component {
    static template = "coop_theme.Appearance";
    static props = { "*": true };

    setup() {
        this.ui = useState({
            theme: readCoopThemeChoice(),
            layout: coopLayout.mode,
        });
    }

    get themes() {
        return [
            ["system", "Системная", "платформа следует за настройкой устройства"],
            ["light", "Светлая", ""],
            ["dark", "Тёмная", ""],
        ];
    }

    get layouts() {
        return [
            ["tiles", "Плитками", "с фотографиями"],
            ["rows", "Списком", "компактно, больше строк на экран"],
        ];
    }

    pickTheme(choice) {
        this.ui.theme = choice;
        setCoopThemeChoice(choice);
    }

    pickLayout(mode) {
        this.ui.layout = mode;
        setCoopLayout(mode);
    }
}

export const coopAppearance = { component: CoopAppearance };

registry.category("view_widgets").add("coop_appearance", coopAppearance);
