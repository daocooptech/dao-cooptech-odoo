/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Колокол в шапке: сколько событий человек ещё не видел.
 *
 * Место и вид — из дизайн-макета: значок справа от поиска, число на
 * золотой плашке. Числа нет вовсе, когда считать нечего: нулевая плашка
 * сообщает ровно столько же, сколько её отсутствие, но тянет взгляд.
 *
 * Счётчик обновляется по таймеру, а не по шине сообщений. Шина дала бы
 * мгновенность, но потребовала бы своего канала на каждого участника и
 * живого соединения; минута задержки для извещения о чужом отклике —
 * цена, которой здесь можно заплатить.
 */
export class CoopBell extends Component {
    static template = "coop_theme.Bell";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.boot = useService("coopBoot");
        this.state = useState({ count: 0 });

        // Первое число — из общего запуска: при открытии страницы
        // колокольчик спрашивал сервер отдельно, впереди раздела.
        // Дальше опрашивает сам, раз в минуту.
        onWillStart(() => this.first());
        this.таймер = setInterval(() => this.refresh(), 60000);
        onWillUnmount(() => clearInterval(this.таймер));
    }

    async first() {
        try {
            this.state.count = (await this.boot.get()).unread || 0;
        } catch {
            this.state.count = 0;
        }
    }

    async refresh() {
        try {
            this.state.count = await this.orm.call(
                "coop.notification", "unread_count", []);
        } catch {
            // Колокол не имеет права уронить шапку: не сосчиталось —
            // значит, числа не будет, а платформа работает дальше.
            this.state.count = 0;
        }
    }

    // Имя латиницей намеренно: шаблонизатор OWL разбирает выражения
    // своим токенизатором, и кириллица в них не проходит вовсе —
    // «could not tokenize `() => this.открыть()`», после чего не
    // рисуется весь веб-клиент. В самом JavaScript русские имена
    // работают, и в остальном коде проекта они остаются; ограничение
    // касается только того, что вызывается из разметки.
    open() {
        // Со сбросом следа: извещения — самостоятельный раздел, и
        // приходят в него из любого места. Без сброса адрес копил
        // цепочку переходов и выглядел поломкой.
        this.action.doAction("coop_base.action_coop_notifications",
                             { clearBreadcrumbs: true });
        // Список прочитан не будет сам собой, но счётчик пересчитаем
        // после перехода: человек уже смотрит на события.
        setTimeout(() => this.refresh(), 1500);
    }
}

registry.category("systray").add(
    "coop_theme.bell", { Component: CoopBell }, { sequence: 20 });
