/** @odoo-module **/

import { useDropdownState } from "@web/core/dropdown/dropdown_hooks";
import { patch } from "@web/core/utils/patch";
import { FormCompiler } from "@web/views/form/form_compiler";
import { StatusBarButtons } from "@web/views/form/status_bar_buttons/status_bar_buttons";
import { toStringExpression } from "@web/views/utils";

/**
 * Меню «⋯» в полосе управления записью — шапка записи по дизайн-системе
 * (`RecordHeader`, 27.10.2026).
 *
 * Эталон: справа одно главное действие, рядом одно-два обычных, а
 * необратимое и редкое — в меню «⋯» красным, с пояснением последствий.
 * До того «Завершить», «Заморозить» и «Отменить» стояли тремя серыми
 * кнопками одного веса, и необратимая «Отменить» — рядом с обычными.
 *
 * Какая кнопка необратимая, решает разметка, а не список здесь: кнопка
 * `<header>` с подтверждением (`confirm`), если она не главная. Пояснение
 * под строкой меню — из `help` кнопки. Компилятор помечает такие слоты, а
 * `StatusBarButtons` раскладывает слоты на кнопки и меню
 * (`record_header.xml`).
 */
patch(FormCompiler.prototype, {
    compileHeader(el, params) {
        const statusBar = super.compileHeader(el, params);
        const box = [...statusBar.children].find((node) => node.tagName === "StatusBarButtons");
        for (const slot of box ? [...box.children] : []) {
            const button = slot.firstElementChild;
            if (!button || button.tagName !== "ViewButton") {
                continue;
            }
            let clickParams = {};
            let attrs = {};
            try {
                clickParams = JSON.parse(button.getAttribute("clickParams") || "{}");
                attrs = JSON.parse(button.getAttribute("attrs") || "{}");
            } catch {
                continue;
            }
            const primary = (button.getAttribute("className") || "").includes("btn-primary");
            if (!clickParams.confirm || primary) {
                continue;
            }
            slot.setAttribute("coopMore", "true");
            slot.setAttribute("coopNote", toStringExpression(clickParams.help || attrs.help || ""));
        }
        return statusBar;
    },
});

patch(StatusBarButtons.prototype, {
    setup() {
        super.setup();
        // Меню закрывается само: кнопка записи гасит щелчок, и пункт
        // меню о выборе не узнаёт — окно подтверждения открывалось
        // поверх раскрытого меню.
        this.coopMoreState = useDropdownState();
    },
    get coopMainSlots() {
        return this.visibleSlotNames.filter((name) => !this.props.slots[name].coopMore);
    },
    get coopMoreSlots() {
        return this.visibleSlotNames.filter((name) => this.props.slots[name].coopMore);
    },
});
