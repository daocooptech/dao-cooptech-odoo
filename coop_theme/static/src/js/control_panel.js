/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { coopIsPlatformModel, coopModelOf } from "@coop_theme/js/platform_page";

/**
 * Шестерёнка «Действия» на телефоне.
 *
 * Штатное меню записи убрано со страниц платформы ещё 21 сентября 2026
 * (решение 349), но убрано оно было в шаблоне крошки — `breadcrumb.xml`,
 * обе ветки `web.Breadcrumb.Actions`. На узком экране панель управления
 * до этого шаблона не доходит: там своя ветка (`control_panel.xml`,
 * `t-elif="env.isSmall"`), и меню она рисует сама, прямо в
 * `section.o_control_panel_breadcrumbs_actions`.
 *
 * Отсюда и вышло, что на большом экране шестерёнки нет, а на телефоне
 * она стоит над карточкой — владелец 23 сентября 2026 прислал снимок
 * своей страницы с ней и тремя пунктами: «Отправить SMS», «Загрузить
 * (vCard)», «Предоставить доступ к порталу». Это действия над строкой
 * таблицы, а не над человеком.
 *
 * Правило то же, что у крошки, и считается тем же способом: страница
 * записи (вид формы) модели платформы. Разные ветки одного экрана не
 * должны решать это по-разному — отсюда общий признак, а не своё
 * условие в каждой.
 */
patch(ControlPanel.prototype, {
    get coopHideActions() {
        try {
            if (this.env.config?.viewType !== "form") {
                return false;
            }
            return coopIsPlatformModel(coopModelOf(this));
        } catch (error) {
            // Признак зовётся на каждой отрисовке панели, а панель стоит
            // на каждом экране: брошенное отсюда исключение — это не
            // «шестерёнка осталась», а сорванная отрисовка страницы.
            console.warn("[панель] не удалось решить, прятать ли меню:", error);
            return false;
        }
    },
});
