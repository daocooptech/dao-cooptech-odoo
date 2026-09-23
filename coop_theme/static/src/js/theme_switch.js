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
    // Тогда своего выбора просто нет, и открывается светлая.
    try {
        return browser.localStorage.getItem(STORAGE_KEY);
    } catch {
        return null;
    }
}

/**
 * Тёмная ли тема при таком выборе.
 *
 * Пустой выбор — светлая, и это решение владельца от 3 сентября 2026:
 * «без явного выбора пользователя платформа всегда открывается в светлой
 * теме, слежение за системной убрано». В макете оно исполнено, на движок
 * не переносилось — там тема до сих пор шла за настройкой устройства, и
 * владелец 22 сентября увидел тёмную: «по умолчанию грузится тёмная
 * тема, а надо чтобы была светлая».
 *
 * Почему светлая, а не системная: платформу показывают людям, и первое,
 * что они видят, должно быть одинаковым. Тёмная тема — выбор, а не
 * случайность настройки чужого телефона.
 */
function darkFor(choice) {
    if (choice === "dark") {
        return true;
    }
    if (choice === "system") {
        return preferredDark();
    }
    return false;
}

export function applyCoopTheme(dark) {
    const root = document.documentElement;
    root.setAttribute("data-bs-theme", dark ? "dark" : "light");
    document.body?.classList.toggle("o_dark_mode", dark);
}

/**
 * Выбор темы: "system", "light" или "dark".
 *
 * Хранится в браузере, а не в учётной записи, и в этом суть: на рабочем
 * столе человек сидит в светлой, на ночном телефоне — в тёмной, и общая
 * настройка на обоих устройствах была бы неверной ровно в половине
 * случаев. Так же и в макете: «Применяется сразу, сохранять не нужно».
 */
export function readCoopThemeChoice() {
    // Пустой выбор показывается в настройках как «Светлая»: она и
    // открывается. Показать здесь «Системная» значило бы обещать то,
    // чего платформа не делает.
    return readChoice() || "light";
}

export function setCoopThemeChoice(choice) {
    try {
        // «Системная» сохраняется наравне с остальными, а не стиранием
        // ключа. Прежде её стирали — и после перезагрузки выбор пропадал
        // вместе с ключом: человек выбрал «следовать за устройством», а
        // платформа об этом не помнила. Настройка, которая молча не
        // работает, хуже отсутствующей.
        browser.localStorage.setItem(STORAGE_KEY, choice);
    } catch {
        // Не сохранилось — тема всё равно переключится, просто забудется.
    }
    applyCoopTheme(darkFor(choice));
}

/**
 * Ставится на этапе загрузки пакета, до отрисовки клиента: иначе
 * страница успевает мигнуть светлым, а потом перекраситься.
 */
function initCoopTheme() {
    applyCoopTheme(darkFor(readChoice()));

    // За системной темой идём только там, где человек это выбрал сам.
    const media = browser.matchMedia?.("(prefers-color-scheme: dark)");
    media?.addEventListener?.("change", (event) => {
        if (readChoice() === "system") {
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

// Порядок в шапке: последним из своих — правее колокола и шестерёнки,
// левее переключателя режима и имени.
//
// Так же он стоит в дизайн-макете: там тумблер вставляется в конец
// `topbar-right`, после колокола, настроек и выхода. Причина не в
// привычке: тумблер — единственный в ряду переключатель, а не кнопка, и
// среди одинаковых клеток со значками он спотыкал ряд посередине. С
// краю он читается как отдельный орган, каким и является.
registry.category("systray").add(
    "coop_theme.theme_switch", { Component: CoopThemeSwitch }, { sequence: 12 }
);
