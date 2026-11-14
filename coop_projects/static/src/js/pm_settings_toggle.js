/** @odoo-module **/
/**
 * «Настройки проекта» в карточке управления проектом — по колёсику.
 *
 * Владелец 14.11.2026: «настройки проекта открываются только при нажатии
 * на иконку колесика, а так надо убрать из карточки». Блок скрыт стилем
 * (`coop_projects.scss`), колёсико ставит признак на `body` и прокручивает
 * к блоку; повторное нажатие закрывает.
 *
 * Признак на `body`, а не на самой форме: разметку формы перерисовывает
 * движок, и класс, поставленный руками на её элемент, мог бы слететь при
 * первом же сохранении поля. Переход на другую запись признак снимает —
 * настройки одного проекта не должны встречать на карточке другого.
 */
const OPEN = "o_coop_pm_settings_open";

function setOpen(open) {
    document.body.classList.toggle(OPEN, open);
    document.querySelectorAll(".o_coop_pm_gear").forEach((el) => {
        el.setAttribute("aria-expanded", open ? "true" : "false");
        el.classList.toggle("active", open);
    });
    if (open) {
        const block = document.getElementById("coop_pm_settings");
        block?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
}

function onActivate(ev) {
    const gear = ev.target.closest?.(".o_coop_pm_gear");
    if (!gear) {
        return;
    }
    if (ev.type === "keydown" && ev.key !== "Enter" && ev.key !== " ") {
        return;
    }
    ev.preventDefault();
    setOpen(!document.body.classList.contains(OPEN));
}

let lastPath = location.pathname;
function onNavigate() {
    if (location.pathname !== lastPath) {
        lastPath = location.pathname;
        setOpen(false);
    }
}

document.addEventListener("click", onActivate, true);
document.addEventListener("keydown", onActivate, true);
window.addEventListener("popstate", onNavigate);
// Движок меняет адрес через `history.pushState`, а он `popstate` не
// вызывает — путь сверяется после каждого нажатия: переход по записям
// всегда начинается с него.
document.addEventListener("click", () => setTimeout(onNavigate, 300));
