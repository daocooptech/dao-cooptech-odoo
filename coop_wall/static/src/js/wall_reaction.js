/** @odoo-module **/

import { QuickReactionMenu } from "@mail/core/common/quick_reaction_menu";
import { patch } from "@web/core/utils/patch";

/**
 * Поиск в окне смайликов набирал «Unidentified» сам.
 *
 * Меню быстрых реакций движка ловит любое нажатие клавиши, пока открыто,
 * и открывает полное окно смайликов, подставляя в поиск `ev.key` как
 * есть. Для буквы это удобно — начал печатать, и поиск уже идёт. Но
 * `ev.key` бывает и названием клавиши: «Tab», «ArrowDown», «Escape», а у
 * клавиш, которых браузер не распознал (переключение раскладки,
 * клавиши ноутбука, экранная клавиатура), — «Unidentified». Это слово и
 * стояло в поиске на снимке владельца 24 сентября 2026.
 *
 * Поиск подставляется только знаком — одной буквой, цифрой или символом.
 * Прочие клавиши окна не открывают. Щелчок по кнопке зовёт метод без
 * строки и проходит как раньше.
 */
patch(QuickReactionMenu.prototype, {
    togglePicker(initialSearchTerm) {
        if (typeof initialSearchTerm === "string" && [...initialSearchTerm].length !== 1) {
            return;
        }
        return super.togglePicker(...arguments);
    },
});
