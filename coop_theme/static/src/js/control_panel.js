/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Pager } from "@web/core/pager/pager";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { Layout } from "@web/search/layout";
import { coopIsPlatformModel, coopModelOf } from "@coop_theme/js/platform_page";

/**
 * Нижний поиск и пагинатор — решение 687 (владелец 17.11.2026, снимок
 * «Уведомлений»: «нижний поиск убрать, слайдер страниц везде снизу»; на
 * вопрос, где убирать, — «везде, кроме каталогов»).
 *
 * «Нижний» — штатная строка поиска Odoo под заголовком экрана, под шапкой
 * с поиском по платформе. В каталогах и на экранах с панелью «Фильтр» она
 * остаётся: там это поиск по каталогу (решение 213).
 *
 * Признаки считаются здесь одной функцией на всех: панель решает, что
 * прятать сверху, а `Layout` — что рисовать снизу. Посчитай они это
 * по-разному, на экране оказалось бы два пагинатора или ни одного.
 */

// Виды, у которых в ячейке поиска панели нет ничего, кроме самого поиска
// (`control-panel-actions` в шаблонах контроллеров движка). У клиентских
// действий — отчётов, сводок — там свои кнопки, и прятать её целиком нельзя.
const COOP_SEARCH_ONLY_VIEWS = ["list", "kanban", "calendar", "pivot", "graph"];

// Виды со страницами списка. У формы «3 / 139» — переход между записями,
// а не страницы, он остаётся наверху.
const COOP_PAGED_VIEWS = ["list", "kanban"];

/** Каталог или экран с панелью «Фильтр» — свой поиск по разделу. */
export function coopIsCatalogScreen(env) {
    const context = env?.searchModel?.globalContext || {};
    return Boolean(context.coop_catalog || context.coop_filters);
}

/** Прятать ли штатный поиск в панели экрана. */
export function coopHideSearch(env) {
    // В окне выбора записи («Найти ещё…») поиск — единственный способ
    // найти нужную, а в режиме отладки он нужен администратору.
    // `odoo.debug`, не `env.debug`: в 20 обращение к `env.debug` бросает
    // исключение (режим отладки стал плагином) и роняет отрисовку панели
    // на каждом экране — проверено на стенде 17.11.2026.
    if (!env || env.inDialog || globalThis.odoo?.debug) {
        return false;
    }
    if (!COOP_SEARCH_ONLY_VIEWS.includes(env.config?.viewType)) {
        return false;
    }
    return !coopIsCatalogScreen(env);
}

/** Стоит ли пагинатор этого экрана под списком, а не в панели. */
export function coopPagerBelow(env) {
    return Boolean(
        env?.config?.pagerProps && COOP_PAGED_VIEWS.includes(env.config.viewType)
    );
}

patch(ControlPanel.prototype, {
    get coopHideSearch() {
        return coopHideSearch(this.env);
    },
    get coopPagerBelow() {
        return coopPagerBelow(this.env);
    },
});

// Пагинатор под списком рисует обёртка экрана: она одна у всех видов, и
// ставить его в каждый контроллер по отдельности значило бы забыть
// какой-нибудь. Каталог в плитке рисует свой — с условиями полок и карты
// (`CoopCatalogKanbanController`, `coopOwnPager`), — здесь его пропускаем.
Layout.components = { ...(Layout.components || {}), Pager };
patch(Layout.prototype, {
    get coopBottomPager() {
        if (!this.props.display?.controlPanel || this.env.coopOwnPager) {
            return false;
        }
        if (!coopPagerBelow(this.env)) {
            return false;
        }
        return (this.env.config.pagerProps.total || 0) > 1;
    },
});

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
