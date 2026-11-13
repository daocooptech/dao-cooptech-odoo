/** @odoo-module **/

/*
 * Буфер обмена на странице по http.
 *
 * Боевая открывается по IP без https (домен не отвечает с 12.10.2026), а
 * браузер даёт `navigator.clipboard` только защищённым страницам. Кнопки
 * «Скопировать» движка (окно ошибки, поле с копированием) падали
 * «Cannot read properties of undefined (reading 'writeText')» — владелец
 * 13.11.2026 увидел это поверх настоящей ошибки сервера.
 *
 * Где буфер есть — не трогаем. Где нет — копируем старым способом через
 * скрытое поле и `execCommand('copy')`.
 */

function copyByTextarea(text) {
    const area = document.createElement("textarea");
    area.value = String(text ?? "");
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-1000px";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    let done = false;
    try {
        done = document.execCommand("copy");
    } finally {
        area.remove();
    }
    return done ? Promise.resolve() : Promise.reject(new Error("copy failed"));
}

if (typeof navigator !== "undefined" && !navigator.clipboard) {
    try {
        Object.defineProperty(navigator, "clipboard", {
            configurable: true,
            value: {
                writeText: copyByTextarea,
                write: () => Promise.reject(new Error("clipboard unavailable")),
                readText: () => Promise.reject(new Error("clipboard unavailable")),
            },
        });
    } catch {
        // Браузер не дал определить свойство — остаётся как было.
    }
}
