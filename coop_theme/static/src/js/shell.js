/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, proxy, signal, usePlugin, useProps } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";
import { Domain } from "@web/core/domain";
import { user } from "@web/core/user";
import { COOP_FAVORITE_CATALOGS } from "@coop_theme/js/favorite";
import { pathAfterPrefix } from "@coop_theme/js/node_path";
import { router, routerBus } from "@web/core/browser/router";
import { ActionPlugin } from "@web/webclient/actions/action_plugin";
import { WebClient } from "@web/webclient/webclient";
import { NavBar } from "@web/webclient/navbar/navbar";
import { CoopIcon } from "@coop_theme/js/icons";
import { render } from "@web/owl2/utils";

/**
 * Боковое меню и подвал — как в прототипе.
 *
 * У Odoo разделы живут в верхней панели приложений: чтобы перейти в
 * другой каталог, надо открыть список приложений. В прототипе разделы
 * постоянно на виду слева, и это не косметика, а другая навигация:
 * платформа устроена как одно пространство, а не как набор приложений.
 *
 * Состав и порядок меню хранятся на сервере, у каждого участника свои
 * (`coop.sidebar.item`): разделы до «Расширений» есть у всех и убрать их
 * нельзя, порядок и набор расширений — личное дело.
 */
/**
 * Вкладки раздела — в строке панели, над поиском, как в макете.
 *
 * Приложение определяется по текущему действию, а не спрашивается у
 * службы меню. Служба считает текущим последнее выбранное через её
 * собственное меню, а по разделам платформы ходят слева, минуя её, — и
 * на «Навыках» вкладки показывали подразделы «Ресурсов».
 */
export class CoopTabs extends Component {
    static template = "coop_theme.Tabs";
    props = useProps();

    setup() {
        this.menus = useService("menu");
        this.action = usePlugin(ActionPlugin);
        this.orm = useService("orm");
        this.state = proxy({ tabs: [], current: null, label: null, fav: null, section: null, known: false });
        useBus(this.env.bus, "COOP_FAVORITE_CHANGED", () => this.refreshFav());
        // Строка вкладок рисуется раньше, чем открывается сам каталог, и
        // первый расчёт вкладки «Избранное» не находил действия — вкладка
        // не появлялась вовсе (найдено глазами 24 сентября 2026). Считаем
        // ещё раз, когда экран дорисован, и когда сама строка на месте.
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => this.refreshFav());
        onMounted(() => this.refreshFav());
        this.lastActionId = null;
        this.refresh();
        // Какое действие открыто, панель управления знает не всегда: у
        // неё своя настройка экрана, и в момент первой отрисовки она
        // пуста. Поэтому слушаем ещё и общее событие о смене экрана —
        // так же, как боковое меню.
        this.env.bus.addEventListener("ACTION_MANAGER:UPDATE", ({ detail }) => {
            const action = this._actionFromEvent(detail);
            if (action?.id) {
                this.lastActionId = action.id;
            }
            this.refresh();
        });
    }

    /**
     * Какое действие открыто сейчас.
     *
     * Раньше оно приходило прямо в событии — `detail.componentProps.action`.
     * В Odoo 19 в `componentProps` этого ключа больше нет вовсе: там
     * `context`, `domain`, `resModel` и прочее устройство представления.
     * Событие приходит, действие в нём не приходит, слушатель выходит
     * первой же строкой — и подсветка открытого раздела пропадает
     * целиком, без единой ошибки в журнале.
     *
     * Спрашиваем службу действий: она знает открытый экран независимо от
     * того, что положили в событие. Прежний путь оставлен запасным —
     * если в следующей версии ключ вернётся, ничего чинить не придётся.
     */
    _actionFromEvent(detail) {
        return (this.action?.currentController?.action
                || detail?.componentProps?.action
                || null);
    }

    get actionId() {
        return (this.env.config?.actionId || this.lastActionId
                || this.action?.currentController?.action?.id || null);
    }

    /**
     * Имя выборки, если человек пришёл не в раздел, а в свой список.
     *
     * «Смотреть все» у полки страницы открывает тот же раздел с узким
     * отбором — мои друзья, мои ресурсы. Вкладки при этом показывали
     * подразделы раздела («Каталог людей»), и человек читал их как
     * название того, на что смотрит. Владелец 20 сентября 2026: «вместо
     * каталога людей тут должно быть мои друзья».
     */
    get screenLabel() {
        // Спрашиваем в трёх местах: контекст действия доходит до клиента
        // (проверено по ответу сервера), но до самой панели добирается
        // по-разному на разных экранах.
        const fromContext = (context) => (context && context.coop_screen_label) || null;
        const label = fromContext(this.env.searchModel?.globalContext)
            || fromContext(this.env.searchModel?.context)
            || fromContext(this.env.config?.context)
            || fromContext(this.action?.currentController?.action?.context);
        if (label) {
            return label;
        }
        // Запасной признак: у выборки собственное имя, а у самого
        // раздела оно совпадает с названием действия в базе.
        const action = this.action?.currentController?.action;
        if (action?.name && action?.display_name
                && action.name !== action.display_name) {
            return action.name;
        }
        return null;
    }

    refresh() {
        const label = this.screenLabel;
        if (label) {
            // Вкладок нет: показывать подразделы раздела рядом с именем
            // выборки значит предлагать уйти туда, откуда человек только
            // что пришёл своим путём.
            this.state.tabs = [];
            this.state.current = null;
            this.state.label = label;
            // Только по своему пункту меню: «последнее выбранное
            // приложение» движка показало бы над выборкой чужой раздел.
            const ownApp = this.menus.getAll().find((menu) => menu.actionID === this.actionId);
            this.state.section = ownApp ? this.menus.getMenu(ownApp.appID)?.name || null : null;
            return;
        }
        this.state.label = null;
        const actionId = this.actionId;
        const own = this.menus.getAll().find((menu) => menu.actionID === actionId);
        // Меню, которого нет у участника в браузере, здесь не
        // перечитывается — и это осознанно.
        //
        // Соблазн был: после переноса раздела на движок меню в браузере
        // остаётся прежним, новых пунктов в нём нет, и вкладки не
        // появляются. Перезагрузка меню это чинила — но срабатывала на
        // любом экране, у которого нет своего пункта: условие выполнялось
        // каждый раз, и раздел переставал подгружаться. Так поймали
        // переписку — тогда её действие и пункт меню расходились
        // (16 сентября 2026 их свели), но защита нужна не из-за неё: экран
        // без своего пункта меню на платформе появится снова.
        //
        // Устаревшее меню лечится обычным обновлением страницы — ценой
        // одного нажатия у одного участника один раз. Поломка переписки
        // стоит дороже.
        const appId = own ? own.appID : this.menus.getCurrentApp()?.id;
        if (!appId) {
            this.state.tabs = [];
            this.state.section = null;
            return;
        }
        this.state.section = own ? this.menus.getMenu(appId)?.name || null : null;
        this.state.known = Boolean(own);
        const children = this.menus.getMenuAsTree(appId).childrenTree || [];
        // Вкладка показывается даже одна: она называет раздел, а
        // названия раздела в панели больше нет — оно дублировало её.
        this.state.tabs = children;
        // Активную ищем среди самих вкладок, а не по всему меню: у
        // корневого пункта раздела и у первой вкладки одно и то же
        // действие, и по общему списку находился корневой — он в
        // строке вкладок не показан, и подсвечивать было нечего.
        const active = children.find((tab) => tab.actionID === actionId);
        this.state.current = active ? active.id : (children[0] || {}).id;
        this.refreshFav();
    }

    /**
     * Вкладка «Избранное N» — как в макете (`people.html?tab=favorites`),
     * решение 408. Не отдельный экран, а тот же каталог, суженный до
     * отмеченных карточек: отбор, сортировка и вид остаются прежними.
     * Сам отбор каталога запоминается в контексте, чтобы число и
     * повторное нажатие считались от каталога, а не от уже суженного.
     */
    async refreshFav() {
        const action = this.action?.currentController?.action;
        const model = action?.res_model;
        if (action?.type !== "ir.actions.act_window" || !COOP_FAVORITE_CATALOGS.includes(model)
                || this.state.label) {
            this.state.fav = null;
            return;
        }
        const on = Boolean(action.context?.coop_fav_tab);
        const base = on ? action.context.coop_fav_base_domain || [] : action.domain || [];
        try {
            const ids = await this.orm.call("coop.favorite", "coop_ids_for", [model]);
            const domain = Domain.and([base, [["id", "in", ids]]]).toList({ ...user.context });
            const count = await this.orm.searchCount(model, domain);
            this.state.fav = { on, count, action, base, domain };
            if (on) {
                this.state.current = null;
            }
        } catch {
            // Избранное не имеет права ронять строку вкладок.
            this.state.fav = null;
        }
    }

    openFav() {
        const fav = this.state.fav;
        if (!fav || fav.on) {
            return;
        }
        const { action } = fav;
        this.action.doAction({
            ...action,
            id: undefined,
            domain: fav.domain,
            context: { ...(action.context || {}), coop_fav_tab: true, coop_fav_base_domain: fav.base },
        }, { stackPosition: "replaceCurrentAction" });
    }

    /**
     * Заголовок экрана (дизайн-система, `PageHeader`): название подраздела
     * крупно, над ним — раздел. Вкладки на большом экране ушли в меню
     * слева, и лист остался без имени — владелец 12.10.2026: «я не вижу в
     * рабочем поле названия разделов».
     *
     * Имя выборки («Мои друзья») важнее подраздела: оно называет то, на
     * что человек смотрит. «Избранное» — тоже выборка.
     */
    get pageTitle() {
        if (this.state.label) {
            return this.state.label;
        }
        if (this.state.fav?.on) {
            return "Избранное";
        }
        const tab = this.state.known
            ? this.state.tabs.find((t) => t.id === this.state.current) : null;
        return tab?.name || this.state.section
            || this.action?.currentController?.action?.name || null;
    }

    /** Раздел над заголовком — когда он не повторяет сам заголовок. */
    get pageSection() {
        const section = this.state.section;
        return section && section !== this.pageTitle ? section : null;
    }

    open(tab) {
        this.menus.selectMenu(tab);
    }
}

/**
 * Значок подраздела — по названию пункта меню (дизайн-система, `Sidebar`).
 * В коде у пунктов меню значков нет; один смысл — один значок во всех
 * разделах, поэтому опознаём по началу названия, а не по разделу.
 */
const SUBNAV_ICONS = [
    ["Мои отклики", "send"],
    ["Мой кошелёк", "wallet"],
    ["Мои сделки", "contract"],
    ["Каталог", "layout-grid"],
    ["Общий каталог", "layout-grid"],
    ["Мои", "user"],
    ["Мой", "user"],
    ["Лента", "news"],
    ["Избранное", "bookmark"],
    ["Продвижение", "speakerphone"],
    ["Взаиморасчёты", "arrows-exchange"],
    ["Линии взаимного кредита", "credit-card"],
    ["Взаимозачёты", "repeat"],
    ["Паевые счета", "coins"],
    ["Номинальный счёт", "building-bank"],
    ["Отзывы", "star"],
    ["Уступки требований", "transfer"],
    ["Установленные", "puzzle"],
];

export function subnavIcon(name) {
    const found = SUBNAV_ICONS.find(([prefix]) => (name || "").startsWith(prefix));
    return found ? found[1] : "layout-list";
}

/**
 * Меню подразделов — дизайн-система, решение 459 (`Sidebar`): подразделы
 * открытого раздела слева от листа, а не вкладками над поиском. Состав и
 * правила те же, что у вкладок (`CoopTabs`): пункты меню модуля,
 * «Избранное N» последним, имя выборки вместо подразделов не ставится —
 * подразделы видны, но ни один не выделен.
 *
 * Только на большом экране; на узком остаются вкладки (этап 7 переноса).
 */
const NO_SUBNAV_APPS = ["mail.menu_root_discuss"];

export class CoopSubnav extends CoopTabs {
    static template = "coop_theme.Subnav";
    static components = { CoopIcon };

    setup() {
        super.setup();
        this.ui = proxy(coopShellUi);
        this.orm2 = useService("orm");
        useBus(this.env.bus, "COOP_SHELL_UI", () => render(this));
        // Событие о смене экрана приходит раньше, чем служба действий
        // узнаёт новое действие, — меню отставало на шаг (стенд,
        // 12.10.2026). Вкладкам это не мешало: они рождаются заново с
        // каждым экраном, а меню живёт в оболочке. Пересчитываем, когда
        // экран уже дорисован.
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => this.refresh());
    }

    /** Открытое действие — у службы действий, а не из события. */
    get actionId() {
        return this.action?.currentController?.action?.id || null;
    }

    /**
     * Пункт меню открытого экрана.
     *
     * Сначала по действию, потом по адресу у роутера: кошелёк открывается
     * карточкой (`/wallet/1`), и действия карточки среди пунктов меню нет,
     * а первый кусок адреса — `wallet` — у пункта «Мой кошелёк» есть.
     * «Последнее выбранное приложение» движка не годится: по разделам
     * ходят планкой, минуя его, и на «Моей странице» висели подразделы
     * «Ресурсов» (стенд, 12.10.2026). Не опознали — меню не показываем.
     */
    ownMenu() {
        const all = this.menus.getAll();
        const actionId = this.actionId;
        let own = actionId ? all.find((menu) => menu.actionID === actionId) : null;
        if (!own) {
            const route = router.current?.action;
            if (route !== undefined && route !== null) {
                own = all.find((menu) => menu.actionPath && menu.actionPath === String(route))
                    || all.find((menu) => menu.actionID && menu.actionID === Number(route));
            }
        }
        return own || null;
    }

    refresh() {
        const own = this.ownMenu();
        const app = own ? this.menus.getMenu(own.appID) : null;
        // У «Сообщений» подразделов нет (дизайн-система): пункты меню
        // переписки движка — каналы, звонки, настройка — участнику не
        // разделы платформы.
        if (!app || NO_SUBNAV_APPS.includes(app.xmlid)) {
            this.state.tabs = [];
            this.state.current = null;
            this.state.fav = null;
            this.state.title = "";
            return;
        }
        const children = this.menus.getMenuAsTree(app.id).childrenTree || [];
        this.state.tabs = children;
        this.state.title = app.name;
        // Выборка («Мои друзья») — подразделы видны, ни один не выделен.
        const active = this.screenLabel ? null : children.find((tab) => tab.actionID === own.actionID);
        this.state.current = active ? active.id : null;
        this.state.label = null;
        this.refreshFav();
    }

    /** Раздел без подразделов («Моя страница», «Сообщения») меню не
     *  получает: лист начинается сразу за планкой. */
    get visible() {
        // Один подраздел — это сам раздел; «Избранное» к нему меню не
        // делает: у «Моей страницы» выходило «Моя страница · Избранное».
        return this.state.tabs.length > 1;
    }

    icon(name) {
        return subnavIcon(name);
    }

    toggleCollapsed() {
        this.ui.subCollapsed = !this.ui.subCollapsed;
        coopSaveMenuState(this.orm2, { sub_collapsed: this.ui.subCollapsed });
        coopShellChanged(this.env);
    }
}

/**
 * Открыто ли выдвижное меню разделов.
 *
 * Состояние общее, потому что кнопка и само меню живут в разных местах
 * разметки: кнопка — в шапке движка (`coop_theme.NavBar`), меню — в
 * рабочей области (`coop_theme.Sidebar`). Через общий реактивный объект
 * обе стороны видят одно и то же: нажатие открывает панель, а панель
 * возвращает кнопке правильный `aria-expanded`.
 */
export const coopShellUi = proxy({ open: false, railWide: false, subCollapsed: false });

/**
 * Запомнить вид меню за участником (дизайн-система, решение 459): выбор
 * действует во всех разделах и на других устройствах. Не дождались ответа
 * — не беда: на экране вид уже сменился, сервер догонит.
 */
/**
 * Сообщить оболочке, что вид меню сменился.
 *
 * Общий объект `coopShellUi` компоненты при отрисовке читают, но на его
 * изменение не перерисовываются — проверено на стенде 12.10.2026: значение
 * менялось, класс планки нет. Под это попадало и выдвижное меню телефона
 * (`open`). Поэтому меню и шапка слушают событие и перерисовываются сами.
 */
export function coopShellChanged(env) {
    env.bus.trigger("COOP_SHELL_UI");
}

export function coopSaveMenuState(orm, values) {
    orm.call("coop.shell", "set_menu_state", [], values).catch(() => {});
}

/**
 * Разделы нижней панели на телефоне — те же пять, что в макете
 * (`app.js`, блок «Нижняя таб-панель»).
 *
 * Список короткий и намеренно: панель отвечает на вопрос «где я и куда
 * можно уйти одним нажатием», а не заменяет меню. Остальные разделы — за
 * кнопкой меню в шапке.
 */
const TABBAR_LABELS = ["Моя страница", "Сообщения", "Ресурсы", "Проекты", "Кошелёк"];

// Где остановилась прокрутка расширений — за браузером, как вид каталога:
// вернувшись, человек видит планку такой, какой оставил.
const RAIL_SCROLL_KEY = "coop_theme.rail_scroll";

function readRailScroll() {
    try {
        return Number(browser.localStorage.getItem(RAIL_SCROLL_KEY)) || 0;
    } catch {
        return 0;
    }
}

function writeRailScroll(value) {
    try {
        browser.localStorage.setItem(RAIL_SCROLL_KEY, String(Math.round(value)));
    } catch {
        // Хранилище закрыто (приватное окно) — помнить просто нечем.
    }
}

export class CoopSidebar extends Component {
    static template = "coop_theme.Sidebar";
    static components = { CoopIcon };
    props = useProps();

    setup() {
        this.action = usePlugin(ActionPlugin);
        this.orm = useService("orm");
        this.menus = useService("menu");
        this.boot = useService("coopBoot");
        // Открытие панели общее с кнопкой в шапке — см. `coopShellUi`.
        this.ui = proxy(coopShellUi);
        useBus(this.env.bus, "COOP_SHELL_UI", () => render(this));
        this.state = proxy({
            main: [], extensions: [], admin: [], current: null, model: null,
            acting: null, actors: [],
            route: router.current?.action ?? null,
            soonLabel: null,
            fly: null,
            moreUp: false, moreDown: false,
        });
        this.extScroll = signal.ref();
        // Есть ли ещё пункты выше и ниже видимой части — от этого зависят
        // затухание у края и стрелки. Меняется не только от прокрутки:
        // окно сузили, планку развернули, добавили расширение.
        this.extResize = new ResizeObserver(() => this.measureExt());
        onMounted(() => {
            const box = this.extScroll();
            if (!box) {
                return;
            }
            box.scrollTop = readRailScroll();
            this.revealActive();
            this.measureExt();
            this.extResize.observe(box);
            if (box.firstElementChild) {
                this.extResize.observe(box.firstElementChild);
            }
        });
        onWillUnmount(() => this.extResize.disconnect());

        onWillStart(async () => {
            await this.load();
            if (!this.state.current) {
                // Сначала спрашиваем службу действий: к моменту, когда
                // меню собралось, экран обычно уже открыт, и она знает
                // его без единого запроса. Разбор адреса остаётся
                // запасным — на случай холодной загрузки, когда служба
                // ещё пуста.
                const open = this._actionFromEvent();
                this.state.current = open?.id || await this._currentAction();
            }
        });

        // Кнопка «назад» меняет адрес, не поднимая события о смене
        // экрана: раздел открыт прежним действием, менеджеру действий
        // сообщать не о чем. Без этого слушателя подсветка после
        // «назад» оставалась на том разделе, откуда ушли.
        // Роутер сообщает о смене раздела сам, и делает это до того, как
        // меняется адрес. Кнопка «назад» сюда же попадает.
        routerBus.addEventListener("ROUTE_CHANGE", () => this._rememberPath());
        // Треть секунды — незаметно человеку и достаточно, чтобы не
        // зависеть от того, в каком порядке движок обновляет свои части.
        this.routeTimer = browser.setInterval(() => this._syncRoute(), 300);
        onWillUnmount(() => browser.clearInterval(this.routeTimer));

        // Какой пункт подсвечен, знает не меню, а тот, кто открыл действие.
        // Меню живёт снаружи представления, и `env.config` у него свой —
        // пустой; поэтому текущее действие берётся из общего события, которым
        // Odoo объявляет о смене экрана.
        this.env.bus.addEventListener("ACTION_MANAGER:UPDATE", ({ detail }) => {
            this._rememberPath();
            const action = this._actionFromEvent(detail);
            const previous = this.state.current;
            if (!action) {
                return;
            }
            // Модель открытого экрана запоминаем всегда: по ней подсветка
            // находит раздел там, где действие не помогает.
            this.state.model = action.res_model || null;
            if (!this._knownAction(action)) {
                // Событие принесло действие, которого нет ни в одном пункте
                // меню. Так открываются вложенные экраны раздела и карточки
                // записей: у кошелька адрес вида /odoo/coop.wallet/6 —
                // номера действия в нём нет вовсе, и спрашивать адрес
                // бесполезно. Зато есть модель, а по ней раздел опознаётся
                // однозначно. Оставлять подсветку на прошлом разделе нельзя:
                // человек стоит на кошельке, а подсвечены «Ресурсы».
                this.state.current = null;
                this._currentAction().then((fromUrl) => {
                    if (fromUrl) {
                        this.state.current = fromUrl;
                    }
                });
                return;
            }
            if (action.tag === "coop_soon") {
                // У заглушек одно действие на все разделы, и различает их
                // только название. Без этого подсветка пропадала ровно
                // там, где она нужнее всего: на разделе, которого ещё нет.
                this.state.current = "soon:" + (action.params?.label || action.name);
            } else {
                this.state.current = action.id || action.tag;
            }
            // Ушли с экрана настройки — перечитываем меню. Иначе правки
            // видны только после перезагрузки страницы, и человек решает,
            // что они не сохранились.
            if (this.settingsId && previous === this.settingsId
                && this.state.current !== this.settingsId) {
                this.load();
            }
        });
    }

    async load() {
        let items = [];
        try {
            // Из общего запуска, а не своим вызовом: меню,
            // колокольчик и переключатели спрашивали сервер
            // порознь и занимали соединения впереди раздела.
            const boot = await this.boot.get();
            items = boot.sidebar || [];
            if (boot.menu) {
                this.ui.railWide = Boolean(boot.menu.rail_wide);
                this.ui.subCollapsed = Boolean(boot.menu.sub_collapsed);
                coopShellChanged(this.env);
            }
        } catch {
            // Меню не загрузилось — оболочка всё равно должна открыться:
            // пустая полоса слева хуже, чем недоступная платформа целиком.
            items = [];
        }
        this.state.main = items.filter((item) => item.section === "main");
        this.state.extensions = items.filter((item) => item.section === "ext");
        // Административные разделы приходят только при включённом режиме
        // полномочий и не хранятся в меню участника.
        this.state.admin = items.filter((item) => item.section === "admin");
        await this.loadActors();
        if (this.settingsId === undefined) {
            const resolved = await this._settingsAction();
            this.settingsId = resolved;
        }
    }

    /**
     * От чьего имени человек может действовать.
     *
     * Список короче единицы не бывает — свой профиль в нём есть всегда, —
     * но пока человек ни в одной организации не состоит, показывать
     * переключатель с единственным пунктом незачем.
     */
    async loadActors() {
        try {
            const info = (await this.boot.get()).acting || {};
            this.state.actors = info.options || [];
            this.state.acting = info.current || null;
        } catch {
            this.state.actors = [];
            this.state.acting = null;
        }
    }

    async setActing(partnerId) {
        const value = Number(partnerId);
        if (!value || value === this.state.acting) {
            return;
        }
        await this.orm.call("coop.shell", "set_acting", [value]);
        this.state.acting = value;
        // Умолчания считаются на сервере, и открытая форма про смену не
        // знает: в ней остался прежний владелец. Перезагрузка честнее,
        // чем экран, наполовину принадлежащий предыдущему лицу.
        browser.location.reload();
    }

    async _settingsAction() {
        try {
            const resolved = await this.orm.call(
                "coop.shell", "resolve_actions", [["coop_theme.action_coop_sidebar_items"]]);
            return resolved["coop_theme.action_coop_sidebar_items"] || false;
        } catch {
            return false;
        }
    }

    /**
     * Что открыто, если событие о смене экрана уже прошло мимо.
     *
     * Меню собирается позже, чем открывается первое действие, и на
     * загрузке страницы события ему не достаётся. Адрес его знает — но
     * может нести внешний идентификатор вместо числа, и тогда его надо
     * разрешить, иначе подсветки на первом экране не будет вовсе.
     */
    /**
     * Какое действие открыто сейчас.
     *
     * Раньше оно приходило прямо в событии — `detail.componentProps.action`.
     * В Odoo 19 в `componentProps` этого ключа больше нет вовсе: там
     * `context`, `domain`, `resModel` и прочее устройство представления.
     * Событие приходит, действие в нём не приходит, слушатель выходит
     * первой же строкой — и подсветка открытого раздела пропадает
     * целиком, без единой ошибки в журнале.
     *
     * Спрашиваем службу действий: она знает открытый экран независимо от
     * того, что положили в событие. Прежний путь оставлен запасным —
     * если в следующей версии ключ вернётся, ничего чинить не придётся.
     */
    _actionFromEvent(detail) {
        return (this.action?.currentController?.action
                || detail?.componentProps?.action
                || null);
    }

    async _currentAction() {
        // Адрес узла (/nn1/…) и движка (/odoo/…) разбираются одинаково.
        const rest = pathAfterPrefix(browser.location.pathname) || "";
        let path = rest.match(/^action-([^/?#]+)/);
        if (!path) {
            // Короткий адрес раздела: /odoo/projects вместо
            // /odoo/action-803. Их завели ради читаемых ссылок, а разбор
            // адреса остался прежним — и раздел, открытый по короткому
            // адресу, подсветки не получал.
            const short = rest.match(/^([a-z][\w-]*)\/?$/);
            if (short) {
                try {
                    // Через свой метод: читать `ir.actions.actions` из
                    // браузера участнику не положено, и прямой запрос
                    // отвечает «Odoo Server Error».
                    const resolved = await this.orm.call(
                        "coop.shell", "resolve_paths", [[short[1]]]);
                    return resolved[short[1]] || null;
                } catch {
                    return null;
                }
            }
            return null;
        }
        const raw = decodeURIComponent(path[1]);
        if (/^\d+$/.test(raw)) {
            return Number(raw);
        }
        try {
            const resolved = await this.orm.call("coop.shell", "resolve_actions", [[raw]]);
            return resolved[raw] || null;
        } catch {
            return null;
        }
    }

    /**
     * Первый кусок адреса после /odoo — короткий адрес раздела.
     *
     * Карточка записи выглядит как /odoo/projects/4, и первый кусок у
     * неё тот же: человек стоит внутри раздела, и подсвечен должен быть
     * он. Служебные адреса движка (/odoo/action-803, /odoo/coop.wallet/6)
     * сюда не попадают — там либо «action-», либо имя модели с точкой,
     * и ни то ни другое коротким адресом не бывает.
     */
    /**
     * Какой раздел открыт — по мнению роутера движка.
     *
     * `router.current.action` — это либо короткий адрес раздела
     * («projects», «discuss»), либо номер действия. Ровно то, что нужно
     * подсветке, и ровно то, чем меню сверяется с пунктами.
     *
     * Почему не адрес страницы и не событие о смене экрана — на обоих
     * уже обожглись:
     *
     * - событие приходит **раньше**, чем меняется адрес, и `location` в
     *   обработчике отдаёт предыдущий раздел. Подсветка отставала ровно
     *   на шаг: человек на «Людях», горят «Проекты»;
     * - отложить чтение на тик не помогает: роутер пишет адрес с
     *   задержкой, и угадывать её — то же самое, но с таймером.
     *
     * Роутер меняет своё состояние сразу, до адреса, и сообщает об этом
     * событием `ROUTE_CHANGE`. Это и есть источник правды.
     */
    _rememberPath() {
        // Значение читаем не в момент события, а следующим тиком: роутер
        // объявляет о смене раздела раньше, чем меняет своё состояние, и
        // прочитанное сразу оказывается прежним. Измерено: в обработчике
        // «tokenomics», а через тик — уже «projects».
        browser.setTimeout(() => this._syncRoute(), 0);
    }

    /**
     * Сверить подсвеченный раздел с тем, что открыто на самом деле.
     *
     * Вызывается и по событию роутера, и раз в треть секунды. Второе —
     * не перестраховка, а вывод: подсветка ломалась трижды за день, и
     * каждый раз потому, что я угадывал момент, когда движок уже
     * обновился. Сверка по таймеру ничего не угадывает; если значение
     * совпало, она не делает ничего и перерисовки не вызывает.
     */
    _syncRoute() {
        const current = router.current || {};
        const route = current.action ?? null;
        if (this.state.route !== route) {
            this.state.route = route;
        }
        // У непереносённых разделов одно действие на всех, и различает
        // их только название. Берём его оттуда же, у роутера: прежде
        // название приходило событием движка и отставало на шаг вместе
        // со всем остальным.
        const stack = current.actionStack || [];
        const label = stack.length ? stack[stack.length - 1].displayName : null;
        if (this.state.soonLabel !== label) {
            this.state.soonLabel = label;
        }
        this.revealActive();
    }

    /**
     * Открытое расширение — в видимой части планки. Двигаем, только когда
     * открытое сменилось: иначе каждые треть секунды планка возвращалась
     * бы к нему, сколько её ни прокручивай.
     */
    revealActive() {
        const box = this.extScroll();
        const item = box?.querySelector(".o_coop_nav_item.active");
        const key = item?.getAttribute("aria-label") || null;
        if (!box || key === this.revealed) {
            return;
        }
        this.revealed = key;
        if (!item) {
            return;
        }
        // Запас — чтобы пункт не стоял в затухании у края.
        const pad = 24;
        const top = item.offsetTop;
        const bottom = top + item.offsetHeight;
        if (top < box.scrollTop + pad) {
            box.scrollTop = top - pad;
        } else if (bottom > box.scrollTop + box.clientHeight - pad) {
            box.scrollTop = bottom - box.clientHeight + pad;
        }
    }

    measureExt() {
        const box = this.extScroll();
        if (!box) {
            return;
        }
        const up = box.scrollTop > 1;
        const down = box.scrollTop + box.clientHeight < box.scrollHeight - 1;
        if (this.state.moreUp !== up) {
            this.state.moreUp = up;
        }
        if (this.state.moreDown !== down) {
            this.state.moreDown = down;
        }
    }

    onExtScroll() {
        // Плашка выезда стоит по месту значка; значок уехал — уезжает и она.
        this.hideFly();
        this.measureExt();
        writeRailScroll(this.extScroll().scrollTop);
    }

    /** Стрелка у края: на три пункта в её сторону. */
    scrollExt(direction) {
        this.extScroll()?.scrollBy({ top: direction * 114, behavior: "smooth" });
    }

    /** Есть ли такое действие среди пунктов меню. */
    _knownAction(action) {
        if (action.tag === "coop_soon") {
            return true;
        }
        const id = action.id || action.tag;
        const allItems = [].concat(this.state.main || [], this.state.extensions || [],
                              this.state.admin || []);
        return allItems.some((item) => item.actionId === id);
    }

    isActive(item) {
        // Первым — адрес. Он виден всегда, не зависит ни от событий
        // движка, ни от запросов к серверу, и переживает обновление
        // мажорной версии: /odoo/projects — это раздел «Проекты», и
        // спорить тут не с чем.
        //
        // Это не украшение порядка проверок. Подсветка ломалась дважды,
        // и оба раза потому, что опознание раздела стояло на чужой
        // механике: сперва на форме события о смене экрана, потом на
        // праве читать `ir.actions.actions`. Адрес не ломается.
        const route = this.state.route;
        if (route !== null && route !== undefined) {
            if (item.path && String(route) === item.path) {
                return true;
            }
            if (item.actionId && Number(route) === item.actionId) {
                return true;
            }
            if (!item.actionId && route === "coop_soon") {
                return this.state.soonLabel === item.label;
            }
            // Роутер знает открытый раздел — он и решает. Без этого
            // возврата прежние пути подсвечивали заодно и тот раздел,
            // откуда ушли: горело сразу два пункта.
            return false;
        }

        const current = this.state.current;
        if (current) {
            if (!item.actionId) {
                return current === "soon:" + item.label;
            }
            if (item.actionId === Number(current)) {
                return true;
            }
        }
        // Действие не опознано — идём по модели. Одну модель могут делить
        // несколько разделов: и «Люди», и «Организации» стоят на res.partner.
        // Тогда не подсвечиваем ничего: пустая подсветка честнее ложной.
        if (!current && this.state.model && item.model === this.state.model) {
            const count = [].concat(this.state.main || [], this.state.extensions || [],
                                      this.state.admin || [])
                .filter((i) => i.model === this.state.model).length;
            return count === 1;
        }
        return false;
    }

    /** «+» у рубрики ведёт в каталог расширений — оттуда их и подключают.
     *
     *  По внешнему имени действия, а не по первому пункту списка: в
     *  списке теперь те расширения, что в макете, и каталога среди них
     *  нет — он витрина, а не расширение. */
    openCatalog() {
        // Со сбросом следа: каталог расширений — самостоятельный раздел,
        // а не углубление в тот, откуда пришли. Без сброса адрес копил
        // цепочку переходов — `/odoo/my-resources/notifications/extensions`,
        // — и выглядел поломкой. Владелец 16 сентября 2026 велел чистить.
        return this.action.doAction(
            "coop_extensions.action_coop_extension_catalog",
            { clearBreadcrumbs: true });
    }

    openSettings() {
        if (!this.settingsId) {
            return;
        }
        return this.action.doAction(this.settingsId, { clearBreadcrumbs: true });
    }

    /**
     * «Выйти» последней строкой бокового меню на телефоне (решение 410,
     * п. 13): меню учётной записи движка на узком экране спрятано, и
     * выйти было неоткуда. Путь — тот же, что у пункта движка
     * (`web/.../user_menu_items.js`, `logOutItem`): сообщение
     * сервис-воркеру и адрес выхода.
     */
    logout() {
        browser.navigator.serviceWorker?.controller?.postMessage("user_logout");
        browser.location.href = "/web/session/logout";
    }

    /**
     * Подразделы раздела — те же пункты меню модуля, что в меню
     * подразделов (`CoopSubnav.refresh`): один подраздел — это сам раздел,
     * у «Сообщений» подразделов нет.
     */
    subsFor(item) {
        if (!item.actionId) {
            return [];
        }
        const own = this.menus.getAll().find((menu) => menu.actionID === item.actionId);
        const app = own ? this.menus.getMenu(own.appID) : null;
        if (!app || NO_SUBNAV_APPS.includes(app.xmlid)) {
            return [];
        }
        const children = this.menus.getMenuAsTree(app.id).childrenTree || [];
        return children.length > 1 ? children : [];
    }

    /**
     * Выезд у свёрнутой планки (дизайн-система, `Rail`): по наведению и по
     * фокусу рядом со значком — имя раздела и его подразделы. У
     * развёрнутой планки названия и так видны, на узком экране планка —
     * выдвижная панель с подписями.
     */
    showFly(item, ev) {
        if (this.ui.railWide || browser.innerWidth <= 900) {
            return;
        }
        const rect = ev.currentTarget.getBoundingClientRect();
        const children = this.subsFor(item);
        const openId = this.action?.currentController?.action?.id;
        const current = this.isActive(item)
            ? (children.find((sub) => sub.actionID === openId) || {}).id : null;
        // У нижних значков плашка поднимается, чтобы не уйти за край окна:
        // заголовок ~44 точки, пункт — 38.
        const height = 44 + 38 * children.length;
        this.state.fly = {
            key: item.label,
            label: item.label,
            soon: !item.actionId,
            top: Math.round(Math.max(8, Math.min(rect.top, browser.innerHeight - height - 8))),
            left: Math.round(rect.right),
            children,
            current: current || null,
        };
    }

    hideFly() {
        if (this.state.fly) {
            this.state.fly = null;
        }
    }

    onRailKey(ev) {
        if (ev.key === "Escape") {
            this.hideFly();
        }
    }

    subIcon(name) {
        return subnavIcon(name);
    }

    openSub(sub) {
        this.state.fly = null;
        this.menus.selectMenu(sub);
    }

    /** Бургер узкого экрана: 216 пикселей из 360 — это меню вместо страницы. */
    toggle() {
        this.ui.open = !this.ui.open;
        coopShellChanged(this.env);
    }

    /**
     * Состав нижней панели: пять разделов из меню участника, в порядке
     * макета.
     *
     * Берём из уже загруженного меню, а не заводим свой список адресов:
     * подсветка, переход и «скоро» тогда работают ровно так же, как в
     * боковом меню, одним кодом. Раздела, которого у участника нет,
     * в панели не появится.
     */
    get tabbar() {
        const main = this.state.main || [];
        return TABBAR_LABELS
            .map((label) => main.find((item) => item.label === label))
            .filter(Boolean);
    }

    open(item) {
        this.hideFly();
        // Выбрали раздел — панель на узком экране закрывается сама: она
        // перекрывает страницу, ради которой её и открывали.
        if (this.ui.open) {
            this.ui.open = false;
            coopShellChanged(this.env);
        }
        // Переход по боковому меню начинает новый путь, а не продолжает
        // старый: раздел — это верхний уровень, и «Люди» внутри «Сделок»
        // в хлебных крошках означали бы вложенность, которой нет.
        const options = { clearBreadcrumbs: true };
        if (!item.actionId) {
            return this.action.doAction({
                type: "ir.actions.client",
                tag: "coop_soon",
                name: item.label,
                params: { label: item.label },
            }, options);
        }
        return this.action.doAction(item.actionId, options);
    }
}

export class CoopFooter extends Component {
    static template = "coop_theme.Footer";
    props = useProps();
}

/**
 * Страница «раздел готовится».
 *
 * Пункт меню, ведущий в пустоту, хуже отсутствующего: человек думает, что
 * сломалось. Здесь прямо сказано, что раздел ещё не перенесён.
 */
/**
 * Заставка на время загрузки.
 *
 * Владелец 21 сентября 2026: «секунд 5 точно грузится, а можно сделать
 * подвал с ссылками был внизу пока грузится и по центру была гифка
 * загрузки в стиле платформы».
 *
 * Пять секунд — это правда, и правда та, которую видит человек, а не
 * прибор: сеть отдаёт страницу за полсекунды, остальное уходит на
 * разбор и запуск семи мегабайт кода. Ускорить это сейчас нечем
 * (единственный рычаг — второй рабочий процесс — упирается в память
 * машины), но пустой экран и пять секунд ожидания — разные вещи. Пустой
 * экран не говорит, идёт ли что-нибудь вообще.
 *
 * Рисуется не гифкой, а разметкой со стилями. Причина не в чистоте, а в
 * деле: гифка это лишний запрос в самый занятый момент загрузки, она не
 * умеет менять цвет вместе с тёмной темой и мылится на плотных экранах.
 * Знак платформы здесь тот же файл, что в шапке, — он уже загружен к
 * этому моменту и ничего не стоит.
 */
export class CoopLoader extends Component {
    static template = "coop_theme.Loader";
    props = useProps();
}

export class CoopSoon extends Component {
    static template = "coop_theme.Soon";
    props = useProps();

    setup() {
        this.label = this.props.action?.params?.label || this.props.action?.name || "Раздел";
    }
}

registry.category("actions").add("coop_soon", CoopSoon);

patch(WebClient, {
    components: { ...WebClient.components, CoopSidebar, CoopSubnav, CoopFooter, CoopLoader },
});

/**
 * Пусто ли сейчас в рабочей области.
 *
 * Состояние снаружи компонента и одно на всё приложение: заставку
 * показывает оболочка, а знает о пустоте наблюдатель за разметкой.
 *
 * Сначала заставка гасла один раз и навсегда — на первом показанном
 * экране. Владелец 22 сентября 2026, показав снимок перехода между
 * разделами: «теперь примени это ко всем страницам и каталогам». И
 * правда: щёлкнув «Ресурсы» из «Вакансий», человек видит то же, что и
 * при первой загрузке — пустоту и подвал, подпирающий шапку. Разницы
 * между «грузится впервые» и «грузится раздел» для смотрящего нет.
 */
export const coopBootUi = proxy({ loading: true });

/**
 * Кнопка меню разделов стоит в шапке слева, как в макете.
 *
 * Раньше она висела кружком в левом нижнем углу поверх содержимого. Там
 * она перекрывала ссылки подвала и ничего не говорила о том, где человек
 * находится; низ экрана теперь занимает панель пяти разделов, и место
 * под неё зарезервировано было давно — 84 точки в `.o_coop_main`.
 */
patch(NavBar, {
    components: { ...NavBar.components, CoopIcon },
});

patch(NavBar.prototype, {
    setup() {
        super.setup();
        this.coopShell = proxy(coopShellUi);
        this.coopOrm = useService("orm");
        useBus(this.env.bus, "COOP_SHELL_UI", () => this.render());
    },

    /** Узкий экран — меню выезжает панелью; большой — планка
     *  сворачивается до значков и разворачивается (решение 459). */
    get coopNarrow() {
        return browser.innerWidth <= 900;
    },

    get coopBurgerLabel() {
        if (this.coopNarrow) {
            return "Меню разделов";
        }
        return this.coopShell.railWide ? "Свернуть разделы" : "Развернуть разделы";
    },

    /** Методом, а не присваиванием прямо в шаблоне: присваивание в
     *  выражении шаблона молча ничего не делает. */
    coopToggleSidebar() {
        if (this.coopNarrow) {
            this.coopShell.open = !this.coopShell.open;
        } else {
            this.coopShell.railWide = !this.coopShell.railWide;
            coopSaveMenuState(this.coopOrm, { rail_wide: this.coopShell.railWide });
        }
        coopShellChanged(this.env);
    },
});

/**
 * Новая страница открывается сверху.
 *
 * Прокрутка у нас вынесена на общий слой `.o_coop_layout`: полоса стоит у
 * правого края окна, как на обычном сайте, а не внутри рабочей области.
 * Слой при этом один на всю работу и между страницами не пересоздаётся —
 * в отличие от контейнера вида, на который рассчитывает Odoo. Поэтому
 * положение прокрутки переезжало с предыдущей страницы: пролистал
 * каталог до середины, нажал «Мою страницу» — и она открывалась где-то
 * на ленте, будто по якорю.
 *
 * Сброс повешен на событие, которое движок подаёт после отрисовки нового
 * действия. Диалоги (`mode === "new"`) пропускаются: они рисуются поверх
 * страницы, и та никуда не уходила.
 */
patch(WebClient.prototype, {
    setup() {
        super.setup();
        this.coopBoot = proxy(coopBootUi);

        // Заставка показывается только на первой загрузке.
        //
        // Была попытка показывать её и на переходах между разделами:
        // наблюдатель за разметкой следил, есть ли в рабочей области
        // собранный экран, и поднимал признак, когда его нет. 22 сентября
        // 2026 это уронило каталоги — «Упс! Что-то пошло не так» и
        // `Invalid loop expression: "undefined" is not iterable` в полосе
        // управления. Отложить запись на такт не помогло.
        //
        // Отката два урока. Первый: наблюдатель за разметкой — это
        // источник событий внутри отрисовки, и всё, что он трогает,
        // трогается в самый неподходящий момент; отсрочка лечит симптом,
        // а не устройство. Второй: возвращать надо к состоянию, которое
        // заведомо работало, а не к следующей догадке — вчерашняя
        // заставка на первой загрузке отработала вечер без единой
        // жалобы.
        //
        // Что делать с переходами — записано вопросом в базе знаний.
        // Пока там пусто: это хуже, чем было с заставкой, но лучше, чем
        // каталоги, которые не открываются.
        this.coopLoaderGuard = browser.setTimeout(() => {
            coopBootUi.loading = false;
        }, 15000);
        onWillUnmount(() => browser.clearTimeout(this.coopLoaderGuard));

        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", ({ detail: mode }) => {
            if (mode === "new") {
                return;
            }
            // Первый показанный экран гасит заставку навсегда.
            if (coopBootUi.loading) {
                coopBootUi.loading = false;
                browser.clearTimeout(this.coopLoaderGuard);
            }
            // Сброс — следующим кадром: в момент события разметка новой
            // страницы ещё не на месте, и слой короче, чем станет.
            browser.requestAnimationFrame(() => {
                // На большом экране прокручивается лист (решение 459),
                // на узком — весь слой; сбрасываем оба.
                for (const selector of [".o_coop_layout", ".o_coop_main"]) {
                    const node = document.querySelector(selector);
                    if (node) {
                        node.scrollTop = 0;
                    }
                }
            });
        });
    },
});
