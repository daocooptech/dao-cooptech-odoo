/** @odoo-module **/

import { Component, onWillStart, proxy, usePlugin, useProps } from "@odoo/owl";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ActionPlugin } from "@web/webclient/actions/action_plugin";

/**
 * Страница «Избранное» — решение 408.
 *
 * Всё, что человек отметил: записи со стен (☆ под записью) и сердечки
 * каталогов, — вкладками по видам. Сердечко или звёздочка на карточке
 * здесь снимает отметку, и карточка сразу уходит со страницы: оставить её
 * значило бы показывать в избранном то, чего там уже нет.
 */
export class CoopFavoritesPage extends Component {
    static template = "coop_theme.FavoritesPage";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.action = usePlugin(ActionPlugin);
        this.favorite = useService("coopFavorite");
        this.state = proxy({ tabs: [], current: null, loaded: false });
        onWillStart(() => this.load());
    }

    async load() {
        const tabs = await this.orm.call("coop.favorite", "coop_page", []);
        this.state.tabs = tabs;
        const firstFull = tabs.find((t) => t.items.length);
        this.state.current = (firstFull || tabs[0] || {}).key || null;
        this.state.loaded = true;
    }

    get tab() {
        return this.state.tabs.find((t) => t.key === this.state.current);
    }

    get total() {
        return this.state.tabs.reduce((sum, t) => sum + t.items.length, 0);
    }

    formatDate(item) {
        return deserializeDateTime(item.date).toFormat("d MMM yyyy, HH:mm");
    }

    async open(item) {
        const action = await this.orm.call("coop.favorite", "coop_open", [item.model, item.id]);
        if (action) {
            this.action.doAction(action);
        }
    }

    async openPost(post) {
        const action = await this.orm.call("coop.favorite", "coop_open", [post.page_model, post.page_id]);
        if (action) {
            this.action.doAction(action);
        }
    }

    _drop(item) {
        const tab = this.tab;
        tab.items = tab.items.filter((i) => i !== item);
    }

    async unheart(item) {
        await this.favorite.toggle(item.model, item.id);
        this._drop(item);
    }

    async unstar(post) {
        await this.orm.call("coop.favorite", "coop_unstar", [post.id]);
        this._drop(post);
    }
}

registry.category("actions").add("coop_theme.favorites", CoopFavoritesPage);

/**
 * Звёздочка в шапке — вход на страницу «Избранное» (решение 408).
 * Значок — линейный, в почерке остальных значков шапки.
 */
export class CoopFavoritesButton extends Component {
    static template = "coop_theme.FavoritesButton";
    props = useProps();

    setup() {
        this.action = usePlugin(ActionPlugin);
    }

    open() {
        this.action.doAction("coop_theme.action_coop_favorites");
    }
}

registry.category("systray").add(
    "coop_theme.favorites", { Component: CoopFavoritesButton }, { sequence: 21 });
