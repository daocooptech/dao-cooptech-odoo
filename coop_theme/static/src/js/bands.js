/** @odoo-module **/

import { browser } from "@web/core/browser/browser";

/**
 * Полосы страницы: сворачиваются и листаются стрелками.
 *
 * В макете у каждой полосы стрелка в правом углу, а плитки листаются
 * кнопками ‹ › по краям ряда. Ни того, ни другого в разметке формы нет:
 * полосы там — обычные блоки с канбаном внутри, и добавлять в каждую по
 * паре кнопок значило бы десять раз повторить одно и то же в
 * представлении, а потом ещё раз в карточке организации.
 *
 * Поэтому кнопки навешиваются на готовую разметку здесь. Наблюдатель, а
 * не разовый проход: полосы перерисовываются при каждой правке записи, и
 * кнопки, поставленные однажды, исчезли бы после первого же сохранения.
 */
const STORAGE_KEY = "coop-bands-closed";

function readClosed() {
    // Хранилище может быть недоступно — в приватном окне или при
    // запрете. Тогда все полосы просто раскрыты, как и по умолчанию.
    try {
        return new Set(JSON.parse(browser.localStorage.getItem(STORAGE_KEY) || "[]"));
    } catch {
        return new Set();
    }
}

function saveClosed(closed) {
    try {
        browser.localStorage.setItem(STORAGE_KEY, JSON.stringify([...closed]));
    } catch {
        // Не сохранилось — полоса всё равно свернулась, просто забудется.
    }
}

/** Название полосы — по нему запоминается, свёрнута она или нет. */
function bandName(band) {
    return band.querySelector(".o_coop_band_head span")?.textContent.trim() || "";
}

function setupBand(band) {
    if (band.dataset.coopBand) {
        return;
    }
    band.dataset.coopBand = "1";

    const head = band.querySelector(".o_coop_band_head");
    const body = band.querySelector(".o_coop_band_body");
    if (!head || !body) {
        return;
    }

    // ── Сворачивание ───────────────────────────────────────────────────
    //
    // По умолчанию раскрыто: человек заходит на страницу, чтобы её
    // прочитать, а не чтобы сначала всё пораскрывать.
    const name = bandName(band);
    const closed = readClosed();

    const arrow = document.createElement("button");
    arrow.type = "button";
    arrow.className = "o_coop_band_arrow";
    arrow.setAttribute("aria-label", "Свернуть или раскрыть");
    head.appendChild(arrow);

    const apply = (isClosed) => {
        band.classList.toggle("o_coop_band_closed", isClosed);
        arrow.textContent = isClosed ? "▼" : "▲";
        arrow.setAttribute("aria-expanded", isClosed ? "false" : "true");
    };
    apply(closed.has(name));

    head.addEventListener("click", (event) => {
        // Переходы в шапке («смотреть все») открывают каталог, а не
        // сворачивают полосу.
        if (event.target.closest("button:not(.o_coop_band_arrow)")) {
            return;
        }
        const now = readClosed();
        if (now.has(name)) {
            now.delete(name);
        } else {
            now.add(name);
        }
        saveClosed(now);
        apply(now.has(name));
    });

    // ── Листание ───────────────────────────────────────────────────────
    //
    // Стрелки по краям ряда, как в макете. Прячутся, когда листать
    // нечего: стрелка, которая ничего не делает, читается как поломка.
    const track = body.querySelector(".o_kanban_renderer") || body;

    const nav = (dir, label) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `o_coop_band_nav o_coop_band_nav_${dir > 0 ? "next" : "prev"}`;
        btn.textContent = label;
        btn.setAttribute("aria-label", dir > 0 ? "Дальше" : "Назад");
        btn.addEventListener("click", () => {
            track.scrollBy({ left: dir * track.clientWidth * 0.8, behavior: "smooth" });
        });
        body.appendChild(btn);
        return btn;
    };

    const prev = nav(-1, "‹");
    const next = nav(1, "›");

    // Показ стрелок меняет ширину ряда, а изменение ширины будит
    // наблюдателя размера — и тот снова трогает стрелки. Без проверки
    // «изменилось ли на самом деле» это замкнутый круг: страница
    // подвисает намертво, без единой ошибки в журнале.
    let shown = null;
    const refresh = () => {
        const scrollable = track.scrollWidth - track.clientWidth > 4;
        const state = [
            !scrollable || track.scrollLeft <= 2,
            !scrollable || track.scrollLeft >= track.scrollWidth - track.clientWidth - 2,
        ].join();
        if (state === shown) {
            return;
        }
        shown = state;
        const [hidePrev, hideNext] = state.split(",");
        prev.classList.toggle("o_coop_hidden", hidePrev === "true");
        next.classList.toggle("o_coop_hidden", hideNext === "true");
    };
    track.addEventListener("scroll", refresh);
    // Через кадр отрисовки: наблюдатель размера не любит правок разметки
    // прямо в своём обработчике и ругается «loop completed».
    const observer = new ResizeObserver(() => {
        browser.requestAnimationFrame(refresh);
    });
    observer.observe(track);
    refresh();
}

function scan(root) {
    for (const band of root.querySelectorAll(".o_coop_band")) {
        setupBand(band);
    }
}

// Наблюдатель по всему документу: форма перерисовывается целиком при
// сохранении записи, и полосы каждый раз новые.
//
// После готовности разметки, а не сразу: скрипты пакета выполняются из
// `<head>`, когда `document.body` ещё не создан, и наблюдатель падал на
// первой же строке. Модуль при этом не просто не работал — он ронял
// загрузку всего клиента, и страница оставалась пустой.
function start() {
    new MutationObserver((records) => {
        for (const record of records) {
            for (const node of record.addedNodes) {
                if (node.nodeType !== 1) {
                    continue;
                }
                if (node.classList?.contains("o_coop_band")) {
                    setupBand(node);
                } else {
                    scan(node);
                }
            }
        }
    }).observe(document.body, { childList: true, subtree: true });

    scan(document.body);
}

if (document.body) {
    start();
} else {
    document.addEventListener("DOMContentLoaded", start, { once: true });
}
