/**
 * Сердечко «в избранное» на карточке каталога.
 *
 * В макете оно стоит на каждой карточке во всех каталогах, справа
 * сверху, и заполняется цветом, когда отмечено. Владелец 15 сентября
 * 2026: «добавь сердечки на каждую карточку — это будет добавить в
 * избранное, ты как то делал такое и мне понравилось».
 *
 * Отметки берутся одним запросом на весь экран, а не по одному на
 * карточку: в каталоге их сотня, и сто запросов ради сотни сердец —
 * ровно та цена, из-за которой страница и висит.
 *
 * Служба общая на все каталоги: разделов полтора десятка, и отметка
 * «нравится» у них одна и та же.
 */
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export const coopFavoriteService = {
    dependencies: ["orm"],
    start(env, { orm }) {
        const marks = {};      // модель → Set номеров
        const promises = {};     // модель → обещание загрузки

        async function load(model) {
            if (!promises[model]) {
                promises[model] = orm
                    .call("coop.favorite", "coop_ids_for", [model])
                    .then((ids) => {
                        marks[model] = new Set(ids);
                        return marks[model];
                    })
                    .catch(() => {
                        // Избранное не имеет права ронять каталог: не
                        // загрузилось — значит сердец не будет, а записи
                        // на месте.
                        promises[model] = null;
                        marks[model] = new Set();
                        return marks[model];
                    });
            }
            return promises[model];
        }

        return {
            ready: load,
            has(model, recordId) {
                return !!marks[model] && marks[model].has(recordId);
            },
            async toggle(model, recordId) {
                const isFavorite = await orm.call(
                    "coop.favorite", "coop_toggle", [model, recordId]);
                await load(model);
                if (marks[model]) {
                    if (isFavorite) {
                        marks[model].add(recordId);
                    } else {
                        marks[model].delete(recordId);
                    }
                }
                return isFavorite;
            },
        };
    },
};

registry.category("services").add("coopFavorite", coopFavoriteService);

export class CoopFavoriteHeart extends Component {
    static template = "coop_theme.FavoriteHeart";
    static props = { ...standardFieldProps };

    setup() {
        this.favorite = useService("coopFavorite");
        this.state = useState({ on: false, busy: false });
        this.model = this.props.record.resModel;
        this.recordId = this.props.record.resId;
        this.favorite.ready(this.model).then(() => {
            this.state.on = this.favorite.has(this.model, this.recordId);
        });
    }

    /**
     * Имя латиницей намеренно: шаблонизатор OWL разбирает выражения
     * своим токенизатором, и кириллица в них не проходит вовсе.
     */
    async toggle(ev) {
        // Карточка каталога — ссылка: без остановки события щелчок по
        // сердцу открывал бы запись.
        ev.stopPropagation();
        ev.preventDefault();
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            this.state.on = await this.favorite.toggle(this.model, this.recordId);
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("fields").add("coop_favorite_heart", {
    component: CoopFavoriteHeart,
    supportedTypes: ["boolean", "integer", "char"],
});
