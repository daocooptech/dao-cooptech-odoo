/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Полки каталога: ряды по рубрикам над общим списком.
 *
 * Зачем. Каталог из ста записей одинаково устроен для всех: длинная лента,
 * в которой сразу не видно, что здесь вообще есть. Полка отвечает на этот
 * вопрос за один взгляд — «Оборудование», «Овощи и фрукты», «Стройматериалы»,
 * по нескольку карточек в каждой. Так устроен дизайн-макет, и владелец
 * попросил перенести это во все каталоги.
 *
 * Полки показываются только на чистом экране. Как только человек что-то
 * искал или отбирал, они пропадают: он уже знает, что ищет, и витрина
 * по рубрикам только мешает.
 *
 * Карточка полки нарочно проще карточки каталога — снимок, название,
 * город. Полка отвечает «что здесь бывает», а не «какая именно запись
 * мне нужна»; для второго есть сам каталог ниже.
 */
export class CoopShelves extends Component {
    static template = "coop_theme.CatalogShelves";
    static props = {
        resModel: { type: String },
        field: { type: String },
        domain: { type: Array, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ shelves: [], loading: true });

        onWillStart(async () => {
            // Полки не имеют права уронить каталог. Один неверный вызов
            // ORM уже сделал это: readGroup в этой версии движка нет, есть
            // formattedReadGroup, — и вместо каталога был пустой экран.
            // Поэтому вся загрузка обёрнута: не вышло собрать полки —
            // их просто не будет.
            try {
                await this.load();
            } catch (e) {
                console.warn("[полки] не собрались:", e);
                this.state.shelves = [];
            }
            this.state.loading = false;
        });
    }

    /** Сколько карточек в полке. Восемь — столько влезает в ряд на широком
     *  экране; на узком ряд прокручивается вбок, как в макете. */
    get perShelf() {
        return 8;
    }

    /** Сколько полок показывать. Больше шести — это уже не витрина,
     *  а второй каталог поверх первого. */
    get maxShelves() {
        return 6;
    }

    async load() {
        const domain = this.props.domain || [];
        // Сначала спрашиваем, какие рубрики вообще есть и сколько в них
        // записей: полка из одной карточки выглядит ошибкой, и такие
        // рубрики отсеиваются здесь, а не в разметке.
        // Имя метода разное в разных версиях движка: formattedReadGroup
        // в нынешней, readGroup в прежних. Берём то, что есть, а не то,
        // что помним.
        const orm = this.orm;
        let groups = [];
        if (orm.formattedReadGroup) {
            groups = await orm.formattedReadGroup(
                this.props.resModel, domain, [this.props.field], ["__count"], { limit: 40 }
            );
        } else if (orm.readGroup) {
            groups = await orm.readGroup(
                this.props.resModel, domain, [this.props.field],
                [this.props.field], { limit: 40 }
            );
        }
        const считать = (g) => g.__count ?? g[this.props.field + "_count"] ?? 0;
        const годные = groups
            .filter((g) => g[this.props.field] && считать(g) >= 3)
            .sort((a, b) => считать(b) - считать(a))
            .slice(0, this.maxShelves);

        for (const g of годные) {
            const значение = g[this.props.field];
            const [id, label] = Array.isArray(значение) ? значение : [значение, значение];
            const записи = await this.orm.searchRead(
                this.props.resModel,
                domain.concat([[this.props.field, "=", id]]),
                ["display_name", "city"],
                { limit: this.perShelf }
            );
            this.state.shelves.push({
                id, label, count: считать(g), records: записи,
            });
        }
    }

    photo(record) {
        return `/web/image/${this.props.resModel}/${record.id}/image_512`;
    }

    open(record) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: this.props.resModel,
            res_id: record.id,
            views: [[false, "form"]],
        });
    }

    /** «Смотреть все» открывает тот же каталог, отобранный по рубрике.
     *  Через действие, а не через строку поиска: у поисковой модели Odoo
     *  свой набор способов добавить условие в каждой версии, и завязываться
     *  на них значит чинить полки при каждом обновлении движка. */
    openAll(shelf) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: shelf.label,
            res_model: this.props.resModel,
            domain: (this.props.domain || []).concat([[this.props.field, "=", shelf.id]]),
            views: [[false, "kanban"], [false, "list"], [false, "form"]],
        });
    }
}
