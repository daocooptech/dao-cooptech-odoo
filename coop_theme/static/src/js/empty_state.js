/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ActionHelper } from "@web/views/action_helper";

/**
 * «Ничего не нашли» вместо «пока пусто».
 *
 * Движок на любой пустой выдаче показывает справку действия — «В каталоге
 * пока пусто…», — даже когда каталог полон, а пусто только под запросом
 * участника. Сверка дизайна 20.10: поиск «щщщ» в ресурсах отвечал, что
 * ресурсов нет. Когда задан поиск по строке или условия панели «Фильтр»
 * (группа «Фильтр каталога», `catalog_filters.js`), говорим про запрос:
 * что искали и что сделать — эталон `Empty`, значок в круге, без картинок.
 */
patch(ActionHelper.prototype, {
    get coopQuery() {
        const sm = this.env.searchModel;
        if (!sm || !sm.query) {
            return null;
        }
        const terms = [];
        let filtered = false;
        for (const q of sm.query) {
            const item = sm.searchItems[q.searchItemId];
            if (!item) {
                continue;
            }
            if (item.type === "field" && q.autocompleteValue) {
                terms.push(q.autocompleteValue.label || String(q.autocompleteValue.value));
            } else if (item.description === "Фильтр каталога") {
                filtered = true;
            }
        }
        return terms.length || filtered ? { terms, filtered } : null;
    },
});
