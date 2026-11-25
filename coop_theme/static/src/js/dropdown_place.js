/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { SelectMenu } from "@web/core/select_menu/select_menu";

/**
 * Меню и выпадающие списки — от кнопки, а не шторкой снизу страницы.
 *
 * Движок открывает их шторкой на любом устройстве с сенсорным экраном
 * (`hasTouch()`), в том числе на ноутбуке с сенсором во всю ширину:
 * владелец 26.11.2026 — «меню должно быть от кнопки, а не снизу страницы».
 * Шторка остаётся только узкому экрану телефона.
 */
function narrow() {
    return window.matchMedia("(max-width: 767.98px)").matches;
}

patch(Dropdown.prototype, {
    get isBottomSheet() {
        return super.isBottomSheet && narrow();
    },
});

patch(SelectMenu.prototype, {
    get isBottomSheet() {
        return super.isBottomSheet && narrow();
    },
});
