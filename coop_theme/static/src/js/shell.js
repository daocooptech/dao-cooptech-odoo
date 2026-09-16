/** @odoo-module **/

import { Component, reactive, useState, onWillStart, onWillUnmount } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";
import { router, routerBus } from "@web/core/browser/router";
import { WebClient } from "@web/webclient/webclient";
import { NavBar } from "@web/webclient/navbar/navbar";

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
    static props = {};

    setup() {
        this.menus = useService("menu");
        this.action = useService("action");
        this.state = useState({ tabs: [], current: null });
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
        return this.env.config?.actionId || this.lastActionId || null;
    }

    refresh() {
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
            return;
        }
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
    }

    open(tab) {
        this.menus.selectMenu(tab);
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
export const coopShellUi = reactive({ open: false });

/**
 * Разделы нижней панели на телефоне — те же пять, что в макете
 * (`app.js`, блок «Нижняя таб-панель»).
 *
 * Список короткий и намеренно: панель отвечает на вопрос «где я и куда
 * можно уйти одним нажатием», а не заменяет меню. Остальные разделы — за
 * кнопкой меню в шапке.
 */
const TABBAR_LABELS = ["Моя страница", "Сообщения", "Ресурсы", "Проекты", "Кошелёк"];

export class CoopSidebar extends Component {
    static template = "coop_theme.Sidebar";
    static props = {};

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.boot = useService("coopBoot");
        // Открытие панели общее с кнопкой в шапке — см. `coopShellUi`.
        this.ui = useState(coopShellUi);
        this.state = useState({
            main: [], extensions: [], admin: [], current: null, model: null,
            acting: null, actors: [],
            route: router.current?.action ?? null,
            soonLabel: null,
        });

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
            items = (await this.boot.get()).sidebar || [];
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
        const pathname = browser.location.pathname;
        let path = pathname.match(/\/odoo\/action-([^/?#]+)/);
        if (!path) {
            // Короткий адрес раздела: /odoo/projects вместо
            // /odoo/action-803. Их завели ради читаемых ссылок, а разбор
            // адреса остался прежним — и раздел, открытый по короткому
            // адресу, подсветки не получал.
            const short = pathname.match(/^\/odoo\/([a-z][\w-]*)\/?$/);
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
    }

    /** Есть ли такое действие среди пунктов меню. */
    _knownAction(action) {
        if (action.tag === "coop_soon") {
            return true;
        }
        const id = action.id || action.tag;
        const все = [].concat(this.state.main || [], this.state.extensions || [],
                              this.state.admin || []);
        return все.some((item) => item.actionId === id);
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
            const сколько = [].concat(this.state.main || [], this.state.extensions || [],
                                      this.state.admin || [])
                .filter((i) => i.model === this.state.model).length;
            return сколько === 1;
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

    /** Бургер узкого экрана: 216 пикселей из 360 — это меню вместо страницы. */
    toggle() {
        this.ui.open = !this.ui.open;
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
        // Выбрали раздел — панель на узком экране закрывается сама: она
        // перекрывает страницу, ради которой её и открывали.
        this.ui.open = false;
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
    static props = {};
}

/**
 * Страница «раздел готовится».
 *
 * Пункт меню, ведущий в пустоту, хуже отсутствующего: человек думает, что
 * сломалось. Здесь прямо сказано, что раздел ещё не перенесён.
 */
export class CoopSoon extends Component {
    static template = "coop_theme.Soon";
    static props = ["*"];

    setup() {
        this.label = this.props.action?.params?.label || this.props.action?.name || "Раздел";
    }
}

registry.category("actions").add("coop_soon", CoopSoon);

patch(WebClient, {
    components: { ...WebClient.components, CoopSidebar, CoopFooter },
});

/**
 * Кнопка меню разделов стоит в шапке слева, как в макете.
 *
 * Раньше она висела кружком в левом нижнем углу поверх содержимого. Там
 * она перекрывала ссылки подвала и ничего не говорила о том, где человек
 * находится; низ экрана теперь занимает панель пяти разделов, и место
 * под неё зарезервировано было давно — 84 точки в `.o_coop_main`.
 */
patch(NavBar.prototype, {
    setup() {
        super.setup();
        this.coopShell = useState(coopShellUi);
    },

    /** Методом, а не присваиванием прямо в шаблоне: присваивание в
     *  выражении шаблона молча ничего не делает. */
    coopToggleSidebar() {
        this.coopShell.open = !this.coopShell.open;
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
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", ({ detail: mode }) => {
            if (mode === "new") {
                return;
            }
            // Сброс — следующим кадром: в момент события разметка новой
            // страницы ещё не на месте, и слой короче, чем станет.
            browser.requestAnimationFrame(() => {
                const layout = document.querySelector(".o_coop_layout");
                if (layout) {
                    layout.scrollTop = 0;
                }
            });
        });
    },
});
