/** @odoo-module **/

import { Component, onMounted, onWillUnmount, proxy, signal, t, useProps } from "@odoo/owl";
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

/**
 * Экран открылся с отбором или группировкой по умолчанию
 * (`search_default_*` в действии или в вызове из кода): «Членство» —
 * действующие, «Строки выписок» — нераспознанные, задачи проекта —
 * открытые. Снять такой отбор можно только крестиком на его фишке, а фишка
 * живёт в строке поиска. Без строки отбор становился вечным — владелец
 * 17.11.2026 выбрал «вернуть там поиск» (решение 688).
 *
 * По признаку движка, а не списком экранов: такие отборы ставит и код
 * (заметки, предложения проекта), список бы отстал. `isDefault` остаётся
 * на пункте и после того, как человек снял отбор, — строка не пропадает
 * у него из-под руки.
 */
export function coopHasDefaultFilter(env) {
    const items = env?.searchModel?.searchItems || {};
    return Object.values(items).some((item) => item.isDefault && item.type !== "favorite");
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
    // Отбор на экране нужен, а по умолчанию он не задан — поиск просит само
    // действие (`coop_search`): у «Заметок» отбирают по пространству (№ 353).
    if (env.searchModel?.globalContext?.coop_search) {
        return false;
    }
    return !coopIsCatalogScreen(env) && !coopHasDefaultFilter(env);
}

/**
 * Лента — карточки вне каталогов («Уведомления» и подобные). Владелец
 * 17.11.2026: «лента должна подгружаться» — без пагинатора, следующая
 * порция приходит, когда человек долистал до конца (решение 688).
 * Таблицам и каталогам пагинатор снизу остаётся (решение 687).
 */
export function coopIsFeed(env) {
    return env?.config?.viewType === "kanban" && !coopIsCatalogScreen(env);
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
/**
 * Догрузка ленты. Хвост под последней карточкой: показался на экране —
 * просим у представления ту же первую страницу, только длиннее на порцию.
 * Через `onUpdate` пагинатора, а не своим запросом: счётчик и записи
 * остаются у представления одни, как если бы человек вписал в пагинатор
 * «1-160». Без второго аргумента (`hasNavigated`) — иначе представление
 * сочтёт это сменой страницы и вернёт прокрутку наверх.
 */
export class CoopFeedLoader extends Component {
    static template = "coop_theme.FeedLoader";
    props = useProps({
        // Тот же объект, что у пагинатора (`env.config.pagerProps`):
        // `offset`, `limit`, `total`, `onUpdate`.
        pager: t.object(),
    });

    setup() {
        this.state = proxy({ loading: false });
        this.tail = signal.ref();
        // Порция — размер первой страницы действия (у ленты 80).
        this.step = this.props.pager.limit || 80;
        onMounted(() => {
            this.observer = new IntersectionObserver((entries) => {
                if (entries.some((entry) => entry.isIntersecting)) {
                    this.loadMore();
                }
            });
            this.observer.observe(this.tail());
        });
        onWillUnmount(() => this.observer?.disconnect());
    }

    get hasMore() {
        const { offset = 0, limit = 0, total = 0 } = this.props.pager;
        return offset + limit < total;
    }

    async loadMore() {
        if (this.state.loading || !this.hasMore) {
            return;
        }
        const { offset = 0, limit = 0, onUpdate } = this.props.pager;
        this.state.loading = true;
        try {
            await onUpdate({ offset, limit: limit + this.step });
        } finally {
            this.state.loading = false;
        }
        // Хвост всё ещё на экране (карточки короткие, окно высокое) —
        // наблюдатель второй раз сам не сработает: состояние «виден» не
        // менялось. Переподписка заставляет его сообщить заново.
        const tail = this.tail();
        if (tail && this.observer) {
            this.observer.unobserve(tail);
            this.observer.observe(tail);
        }
    }
}

Layout.components = { ...(Layout.components || {}), Pager, CoopFeedLoader };
patch(Layout.prototype, {
    /** Общее для пагинатора и догрузки: экран листается, и листать его — нам. */
    get coopPagesBelow() {
        if (!this.props.display?.controlPanel || this.env.coopOwnPager) {
            return false;
        }
        return coopPagerBelow(this.env);
    },
    get coopBottomPager() {
        if (!this.coopPagesBelow || coopIsFeed(this.env)) {
            return false;
        }
        return (this.env.config.pagerProps.total || 0) > 1;
    },
    get coopFeedLoader() {
        return this.coopPagesBelow && coopIsFeed(this.env)
            && (this.env.config.pagerProps.total || 0) > 0;
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
