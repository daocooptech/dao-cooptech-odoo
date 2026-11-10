/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { Component, proxy } from "@odoo/owl";

/**
 * Режим покупателя над каталогом: «как частное лицо» / «как организация».
 *
 * Решение 634 (владелец 10.11.2026, «как Ozon и WB»): оптовые условия —
 * для организации. В WB это отдельный режим, а не фильтр, потому что
 * меняется вся витрина: у организации на карточке видна оптовая цена и
 * значок «оптом дешевле», у частного лица — розничная.
 *
 * Режим только переключает класс на `body`; что показывать, решает
 * разметка карточки (`o_coop_res_ws`). Запоминается в браузере, а не на
 * сервере: это вид витрины, а не свойство человека — один и тот же
 * человек смотрит и как частное лицо, и от имени организации.
 */
const KEY = "coop_buyer_mode";
const CLASS = "o_coop_buyer_org";

function stored() {
    try {
        return browser.localStorage.getItem(KEY) === "org" ? "org" : "person";
    } catch {
        return "person";
    }
}

function apply(mode) {
    document.body.classList.toggle(CLASS, mode === "org");
}

export class CoopBuyerMode extends Component {
    static template = "coop_theme.BuyerMode";

    setup() {
        this.state = proxy({ mode: stored() });
        apply(this.state.mode);
    }

    set(mode) {
        this.state.mode = mode;
        apply(mode);
        try {
            browser.localStorage.setItem(KEY, mode);
        } catch {
            // Не сохранилось — режим всё равно переключился.
        }
    }
}
