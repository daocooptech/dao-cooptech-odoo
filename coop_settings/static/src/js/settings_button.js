/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * «Настройки» — пунктом в меню под аватаром.
 *
 * Прежде это была шестерёнка в шапке, как в макете. Владелец 12.10.2026:
 * «убрать иконку настроек из верхнего меню и добавить как пункт в меню,
 * которое при нажатии на аватар». Так и в эталоне (`AccountMenu`): под
 * аватаром — от чьего имени действую, «Настройки», «О платформе»,
 * «Выйти».
 *
 * Со сбросом следа: настройки — не углубление в раздел, откуда пришли, а
 * выход из него. Иначе путь копит цепочку «каталог → запись → настройки».
 */
export function coopSettingsItem() {
    const action = useService("action");
    return {
        type: "item",
        id: "coop_settings",
        description: "Настройки",
        callback: () => action.doAction("coop_settings.action_coop_settings", {
            clearBreadcrumbs: true,
        }),
        sequence: 50,
    };
}

const items = registry.category("user_menuitems");
items.add("coop_settings", coopSettingsItem);

// Пункты движка, которых в меню платформы нет (эталон `AccountMenu`):
// «Shortcuts» — палитра команд по Ctrl+K, по-английски и для знающих
// движок изнутри (сама палитра по Ctrl+K работает); «Мои предпочтения» —
// окно учётной системы, которое повторяет «Настройки»; «В сети» — выбор
// статуса переписки (статус и так ставится сам: в сети, отошёл);
// «Установить приложение» — предложение браузера, не пункт меню.
for (const name of ["shortcuts", "preferences", "im_status", "install_pwa"]) {
    if (items.contains(name)) {
        items.remove(name);
    }
}
