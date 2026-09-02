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
 * другой каталог, надо открыть список приложений. В прототипе восемь с
 * лишним разделов постоянно на виду слева, и это не косметика, а другая
 * навигация: платформа устроена как одно пространство, а не как набор
 * приложений.
 *
 * Порядок пунктов до «Расширений» — из макета и обязателен. Расширения у
 * каждого узла свои: здесь показаны только те, что уже перенесены.
 */

// Обязательные разделы, в порядке макета. `action` — внешний
// идентификатор действия; там, где раздел ещё не перенесён, его нет, и
// пункт ведёт на страницу-заглушку, которая честно об этом говорит.
const MAIN_ITEMS = [
    { label: "Моя страница", icon: "fa-user-circle-o", action: null },
    { label: "Сообщения", icon: "fa-comments-o", action: "mail.action_discuss" },
    { label: "Люди", icon: "fa-users", action: "coop_people.action_coop_people" },
    { label: "Навыки", icon: "fa-wrench", action: "coop_skills.action_coop_skills" },
    { label: "Вакансии", icon: "fa-briefcase", action: "coop_vacancies.action_coop_vacancies" },
    { label: "Ресурсы", icon: "fa-cube", action: "coop_resources.action_coop_resources" },
    { label: "Проекты", icon: "fa-rocket", action: "project.open_view_project_all" },
    { label: "Организации", icon: "fa-university", action: "coop_orgs.action_coop_orgs" },
    { label: "Сообщества", icon: "fa-comments", action: null },
    { label: "Кошелёк", icon: "fa-credit-card", action: "coop_tokens.action_coop_token" },
    { label: "Сделки", icon: "fa-handshake-o", action: null },
];

// Расширения. В макете их полтора десятка — токеномика, цифровые активы,
// закупки, склад, аукционы и прочее; здесь только то, что уже перенесено
// на движок. Показывать пункт, за которым стоит чужой модуль Odoo без
// нашего экрана, значит выдавать чужую страницу за перенесённую.
const EXTENSION_ITEMS = [
    { label: "Каталог расширений", action: "coop_extensions.action_coop_extension_catalog" },
    { label: "Помощь проекту", action: "coop_bounty.action_coop_bounty_task" },
];

export class CoopSidebar extends Component {
    static template = "coop_theme.Sidebar";
    static props = {};

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = useState({ main: [], extensions: [], current: null });

        onWillStart(async () => {
            this.state.main = await this._resolve(MAIN_ITEMS);
            this.state.extensions = await this._resolve(EXTENSION_ITEMS);
            this.state.current = this._currentAction();
        });

        // Какой пункт подсвечен, знает не меню, а тот, кто открыл действие.
        // Меню живёт снаружи представления, и `env.config` у него свой —
        // пустой; поэтому текущее действие берётся из общего события, которым
        // Odoo объявляет о смене экрана.
        this.env.bus.addEventListener("ACTION_MANAGER:UPDATE", ({ detail }) => {
            const action = detail?.componentProps?.action;
            if (!action) {
                this.state.current = this._currentAction();
            } else if (action.tag === "coop_soon") {
                // У заглушек одно действие на все разделы, и различает их
                // только название. Без этого подсветка пропадала ровно
                // там, где она нужнее всего: на разделе, которого ещё нет.
                this.state.current = "soon:" + (action.params?.label || action.name);
            } else {
                this.state.current = action.id || action.tag;
            }
        });
    }

    _currentAction() {
        // Первая отрисовка происходит до события: адрес страницы уже знает,
        // какое действие открыто, и подсветка не мигает при загрузке.
        const path = browser.location.pathname.match(/\/odoo\/action-([^/?#]+)/);
        return path ? decodeURIComponent(path[1]) : null;
    }

    /**
     * Разрешить внешние идентификаторы в действия.
     *
     * Пункт, чьего действия на узле нет, не выбрасывается: он остаётся в
     * списке неактивным. Порядок разделов — часть договорённости с
     * владельцем, и молча выкидывать из него пункты значит менять
     * договорённость втихую.
     */
    async _resolve(items) {
        const xmlids = items.filter((i) => i.action).map((i) => i.action);
        let resolved = {};
        try {
            resolved = await this.orm.call("coop.shell", "resolve_actions", [xmlids]);
        } catch {
            resolved = {};
        }
        return items.map((item) => ({
            ...item,
            actionId: item.action ? resolved[item.action] || false : false,
        }));
    }

    isActive(item) {
        const current = this.state.current;
        if (!current) {
            return false;
        }
        if (!item.actionId) {
            return current === "soon:" + item.label;
        }
        // Адрес может нести и внешний идентификатор, и число: оба варианта
        // Odoo принимает, и оба должны подсвечивать один пункт.
        return item.actionId === Number(current) || item.action === current;
    }

    /** «+» у рубрики ведёт в каталог расширений — оттуда их и подключают. */
    openCatalog() {
        const catalog = this.state.extensions[0];
        return this.open(catalog || { label: "Расширения", actionId: false });
    }

    open(item) {
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
