/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CoopSidebar } from "@coop_theme/js/shell";
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
        this.boot = useService("coopBoot");
        this.state = useState({ granted: false, active: false, busy: false });
        onWillStart(async () => {
            // Из общего запуска оболочки, а не своим вызовом.
            const result = (await this.boot.get()).admin || {};
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
    { sequence: 10 }
);

// Тот же переключатель — в выдвижном меню разделов.
//
// В шапке он есть только на широком экране: на 375 точках на органы
// управления остаётся 256, и переключатель оттуда убран вместе с тремя
// значками движка. Но справочники и прочие административные пункты
// появляются как раз по нему, и без него с телефона до них не добраться
// вовсе. Владелец 16 сентября 2026: «в мобильной версии переключатель
// администратора встрой в выпадающее меню».
//
// Стоит он прямо над блоком «Администрирование»: включил — и пункты
// появились тут же, под пальцем, не закрывая меню. На широком экране
// строка скрыта стилями, иначе переключатель был бы на экране дважды.
//
// Компонент один и тот же, состояние он читает из общего запуска
// оболочки, поэтому две его копии не спорят между собой: обе показывают
// одно и то же, а нажатие в любой из них перезагружает страницу.
CoopSidebar.components = { ...(CoopSidebar.components || {}), CoopAdminSwitch };
