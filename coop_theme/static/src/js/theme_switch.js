/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import { Component, useState } from "@odoo/owl";

/**
 * Переключатель светлой и тёмной темы — тот же, что в прототипе.
 *
 * Штатным средством Odoo это не сделать: тёмный режим в сообществе
 * подключается отдельным пакетом стилей, который выбирается на сервере
 * при отрисовке страницы, а самих тёмных стилей в нём три файла. Наша
 * палитра целиком построена на переменных и лежит в обычном пакете,
 * поэтому тема меняется признаком на документе — без перезагрузки и без
 * похода на сервер.
 *
 * Признак берём тот же, что у Bootstrap (`data-bs-theme`): по нему
 * перекрашиваются и наши токены, и штатные компоненты движка. Свой класс
 * рядом — для правил, написанных до этого.
 */
const STORAGE_KEY = "coop-theme";

function preferredDark() {
    return Boolean(browser.matchMedia?.("(prefers-color-scheme: dark)")?.matches);
}

function readChoice() {
    // Хранилище может быть недоступно — в приватном окне или при запрете.
    // Тогда своего выбора просто нет, и тема идёт за системной.
    try {
        return browser.localStorage.getItem(STORAGE_KEY);
    } catch {
        return null;
    }
}

export function applyCoopTheme(dark) {
    const root = document.documentElement;
    root.setAttribute("data-bs-theme", dark ? "dark" : "light");
    document.body?.classList.toggle("o_dark_mode", dark);
}

/**
 * Ставится на этапе загрузки пакета, до отрисовки клиента: иначе
 * страница успевает мигнуть светлым, а потом перекраситься.
 */
function initCoopTheme() {
    const choice = readChoice();
    applyCoopTheme(choice ? choice === "dark" : preferredDark());

    // Пока своего выбора нет, идём за системной темой и переключаемся
    // вместе с ней на лету — как в прототипе.
    const media = browser.matchMedia?.("(prefers-color-scheme: dark)");
    media?.addEventListener?.("change", (event) => {
        if (!readChoice()) {
            applyCoopTheme(event.matches);
        }
    });
}

initCoopTheme();

export class CoopThemeSwitch extends Component {
    static template = "coop_theme.ThemeSwitch";
    static props = {};

    setup() {
        this.state = useState({
            dark: document.documentElement.getAttribute("data-bs-theme") === "dark",
        });
    }

    toggle() {
        this.state.dark = !this.state.dark;
        applyCoopTheme(this.state.dark);
        // С этого момента страница перестаёт следовать за системной темой:
        // человек выбрал сам, и переигрывать за него не нужно.
        try {
            browser.localStorage.setItem(STORAGE_KEY,
                                         this.state.dark ? "dark" : "light");
        } catch {
            // Не сохранилось — тема всё равно переключилась, просто
            // забудется до следующего захода.
        }
    }
}

// Порядок в шапке: правее поиска, левее переключателя режима и имени.
registry.category("systray").add(
    "coop_theme.theme_switch", { Component: CoopThemeSwitch }, { sequence: 8 }
);
