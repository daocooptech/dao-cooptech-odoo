/** @odoo-module **/

import { t } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/core/dialog/dialog";
import { WebClient } from "@web/webclient/webclient";

/**
 * Название платформы вместо «Odoo» — решение 442.
 *
 * Раньше это делал Rudoo-модуль web_debranding, у которого лицензия OPL-1:
 * пользоваться им можно только с купленной лицензией. Здесь — то, что из
 * него реально работало в Odoo 19 (замер на копии боевой 29.09): заголовок
 * вкладки и заголовок окон по умолчанию. Переводы — в models/ir_http.py.
 */
const PLATFORM_TITLE = "Социально-экономическая платформа";
const PLATFORM_NAME = "ДАО КООПТЕХ";

// Первая часть заголовка вкладки: «Социально-экономическая платформа -
// Вакансии». Без неё служба заголовка подставляет «Odoo», пока действие
// не загрузилось.
patch(WebClient.prototype, {
    setup() {
        super.setup();
        this.title.setParts({ zopenerp: PLATFORM_TITLE });
    },
});

// Окно без собственного заголовка называлось «Odoo».
//
// В 20 умолчаний props у окна больше нет (Owl 3): схема с умолчаниями
// лежит в статическом `propsSchema`, и окно читает её при создании
// (`props = useProps(this.constructor.propsSchema)`, web/core/dialog).
patch(Dialog, {
    propsSchema: { ...Dialog.propsSchema, title: t.string().optional(PLATFORM_NAME) },
});
