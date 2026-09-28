/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { router, startRouter } from "@web/core/browser/router";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";

/**
 * Имя узла в адресной строке: /nn1/my-page вместо /odoo/my-page.
 *
 * Владелец 28.09.2026: «что бы видно было еще в адресной строке на каком
 * узле ведется учет». Имя приходит с сервера (`coop_node_path` в
 * odoo.conf, по умолчанию nn1) — у второго узла будет своё.
 *
 * Роутер движка знает только /odoo, и переписывать его нельзя: при
 * обновлении движка всё вернулось бы. Зато преобразования «состояние ↔
 * адрес» он сам разрешает подменять («can be patched if needed in a custom
 * webclient»). Подмена двусторонняя: наружу — /nn1, внутрь движку — /odoo.
 * Всё остальное в роутере остаётся движковым.
 *
 * Сервер переадресует старые /odoo-ссылки (из писем, закладок, переадресаций
 * после входа) на адрес узла — `controllers/node_path.py`.
 */

export const NODE_PREFIX = "/" + (session.coop_node_path || "nn1");

function isEnginePath(pathname) {
    return pathname === "/odoo" || pathname.startsWith("/odoo/");
}

export function isNodePath(pathname) {
    return pathname === NODE_PREFIX || pathname.startsWith(NODE_PREFIX + "/");
}

/** Первый кусок адреса после префикса узла или движка: «/nn1/projects/4» → «projects/4». */
export function pathAfterPrefix(pathname) {
    for (const prefix of [NODE_PREFIX, "/odoo"]) {
        if (pathname === prefix || pathname.startsWith(prefix + "/")) {
            return pathname.slice(prefix.length + 1);
        }
    }
    return null;
}

patch(router, {
    stateToUrl(state) {
        return super.stateToUrl(state).replace(/^\/odoo(?=[/?#]|$)/, NODE_PREFIX);
    },
    urlToState(urlObj) {
        if (!isNodePath(urlObj.pathname)) {
            return super.urlToState(urlObj);
        }
        const engine = new URL(urlObj.href);
        engine.pathname = "/odoo" + urlObj.pathname.slice(NODE_PREFIX.length);
        return super.urlToState(engine);
    },
});

// Роутер разобрал адрес при своей загрузке — раньше, чем подключилась эта
// подмена, и /nn1/… для него был чужим: открылась бы стартовая страница
// вместо записи. Разбираем заново. Служебные ключи роутера на этот момент
// ещё никто не зарегистрировал — это делает служба действий при запуске.
if (isNodePath(browser.location.pathname)) {
    startRouter();
}

/**
 * Внутренние ссылки — без перезагрузки страницы.
 *
 * Движок перехватывает клик по ссылке, только если текущий адрес начинается
 * с /odoo; на /nn1 он молча уступает, и каждая ссылка перезагружала бы
 * страницу. Делаем то же, что он: кладём новый адрес в историю и отдаём его
 * роутеру тем же путём, каким тот принимает «назад» и «вперёд», — событием
 * popstate без готового состояния: роутер разбирает адрес сам.
 */
browser.addEventListener("click", (ev) => {
    if (ev.defaultPrevented || ev.button !== 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey
            || ev.altKey || ev.target.closest?.("[contenteditable]")) {
        return;
    }
    const a = ev.target.closest?.("a");
    const href = a?.getAttribute("href");
    if (!href || href.startsWith("#") || a.target === "_blank" || a.hasAttribute("download")) {
        return;
    }
    let url;
    try {
        url = new URL(a.href);
    } catch {
        return;
    }
    if (url.host !== browser.location.host || !isNodePath(browser.location.pathname)) {
        return;
    }
    if (!isNodePath(url.pathname) && !isEnginePath(url.pathname) && url.pathname !== "/web") {
        return;
    }
    ev.preventDefault();
    if (isEnginePath(url.pathname)) {
        url.pathname = NODE_PREFIX + url.pathname.slice("/odoo".length);
    }
    browser.history.pushState({}, "", url.href);
    browser.dispatchEvent(new PopStateEvent("popstate", { state: {} }));
});
