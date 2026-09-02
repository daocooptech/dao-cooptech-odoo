/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";
import { WebClient } from "@web/webclient/webclient";

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
export class CoopSidebar extends Component {
    static template = "coop_theme.Sidebar";
    static props = {};

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = useState({
            main: [], extensions: [], admin: [], current: null, open: false,
            acting: null, actors: [],
        });

        onWillStart(async () => {
            await this.load();
            if (!this.state.current) {
                this.state.current = await this._currentAction();
            }
        });

        // Какой пункт подсвечен, знает не меню, а тот, кто открыл действие.
        // Меню живёт снаружи представления, и `env.config` у него свой —
        // пустой; поэтому текущее действие берётся из общего события, которым
        // Odoo объявляет о смене экрана.
        this.env.bus.addEventListener("ACTION_MANAGER:UPDATE", ({ detail }) => {
            const action = detail?.componentProps?.action;
            const previous = this.state.current;
            if (!action) {
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
            items = await this.orm.call("coop.sidebar.item", "items_for_current_user", []);
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
            const info = await this.orm.call("coop.shell", "acting_options", []);
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
    async _currentAction() {
        const path = browser.location.pathname.match(/\/odoo\/action-([^/?#]+)/);
        if (!path) {
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

    isActive(item) {
        const current = this.state.current;
        if (!current) {
            return false;
        }
        if (!item.actionId) {
            return current === "soon:" + item.label;
        }
        return item.actionId === Number(current);
    }

    /** «+» у рубрики ведёт в каталог расширений — оттуда их и подключают. */
    openCatalog() {
        const catalog = this.state.extensions[0];
        return this.open(catalog || { label: "Расширения", actionId: false });
    }

    openSettings() {
        if (!this.settingsId) {
            return;
        }
        return this.action.doAction(this.settingsId, { clearBreadcrumbs: true });
    }

    /** Бургер узкого экрана: 216 пикселей из 360 — это меню вместо страницы. */
    toggle() {
        this.state.open = !this.state.open;
    }

    open(item) {
        // Выбрали раздел — панель на узком экране закрывается сама: она
        // перекрывает страницу, ради которой её и открывали.
        this.state.open = false;
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
