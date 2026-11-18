/** @odoo-module **/

import { onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { uniqueId } from "@web/core/utils/functions";
import { useService } from "@web/core/utils/hooks";
import { CharField, charField } from "@web/views/fields/char/char_field";

/**
 * Поле «Город» с подсказкой: штатное текстовое поле плюс список городов,
 * которые уже есть на платформе, — как в фильтре «Город» каталогов.
 *
 * Владелец 18.11.2026 про подписку на задачи: «город не находится когда я
 * начинаю вводить». Ввод остаётся свободным: город, которого ещё нет в
 * списке, вписывается как есть.
 *
 * Список — один запрос на сессию страницы, а не на каждое поле: в форме
 * их бывает несколько, а города меняются редко.
 */
let citiesPromise = null;

export class CoopCityField extends CharField {
    static template = "coop_theme.CityField";

    setup() {
        super.setup();
        this.coopListId = uniqueId("coop-city-");
        this.coopCities = [];
        const orm = useService("orm");
        onWillStart(async () => {
            citiesPromise ||= orm.call("res.partner", "coop_city_suggestions", []);
            try {
                this.coopCities = await citiesPromise;
            } catch {
                // Без подсказки поле остаётся обычным вводом; следующая
                // форма попробует ещё раз.
                citiesPromise = null;
            }
        });
    }
}

registry.category("fields").add("coop_city", { ...charField, component: CoopCityField });
