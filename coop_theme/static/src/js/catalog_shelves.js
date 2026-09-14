/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { RelationalModel } from "@web/model/relational_model/relational_model";
import { addFieldDependencies, extractFieldsFromArchInfo } from "@web/model/relational_model/utils";
import { KanbanRecord } from "@web/views/kanban/kanban_record";

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
    static components = { KanbanRecord };
    static props = {
        resModel: { type: String },
        field: { type: String },
        domain: { type: Array, optional: true },
        // Разбор представления и список полей — те же, по которым
        // каталог рисует свои карточки. Полка рисует ими же: два вида
        // карточек на одном экране владелец назвал разнобоем, и был
        // прав — витрина показывает тот же каталог, а не другой раздел.
        archInfo: { type: Object },
        fields: { type: Object },
        openRecord: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ shelves: [], loading: true });

        // Вторая модель — на все полки одна.
        //
        // Карточке канбана нужна не строка из `search_read`, а запись
        // модели: она сама достаёт значения полей, считает цвета и
        // разрешает условия видимости. Своя модель нужна потому, что у
        // каталога загружена только первая страница, а полкам нужны
        // записи каждой рубрики.
        //
        // Одна на шесть полок, а не шесть по одной: столько же запросов
        // ушло бы на счётчики, а записи всё равно берутся одним
        // запросом с отбором по списку рубрик.
        this.модельПолок = new RelationalModel(
            this.env, this.параметрыМодели, {
                action: useService("action"),
                dialog: useService("dialog"),
                notification: useService("notification"),
                orm: this.orm,
            });

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

    get параметрыМодели() {
        const { activeFields, fields } = extractFieldsFromArchInfo(
            this.props.archInfo, this.props.fields);
        // Поле рубрики карточке не нужно и в разборе представления его
        // может не быть — у закупок «Раздел» в канбане не показывается.
        // А разложить записи по полкам без него нечем: значение приходит
        // пустым, полки выходят с заголовками и без карточек.
        const описание = this.props.fields[this.props.field];
        if (описание && !activeFields[this.props.field]) {
            addFieldDependencies(activeFields, fields,
                [{ name: this.props.field, type: описание.type }]);
        }
        // `groupBy` и `orderBy` пустыми списками, а не пропущенными:
        // модель их не подставляет, а `_getNextConfig` по ним проходит
        // `map` и `length` — без них загрузка падает на `undefined`.
        return {
            config: {
                resModel: this.props.resModel, activeFields, fields,
                domain: [], groupBy: [], orderBy: [], context: {},
            },
            limit: this.perShelf * this.maxShelves,
        };
    }

    /** Сколько карточек грузим на полку. Показывается меньше — столько,
     *  сколько влезло целыми; остальные ждут за «Смотреть все». Грузим с
     *  запасом, чтобы на широком экране полка не обрывалась на третьей. */
    get perShelf() {
        return 8;
    }

    /** Сколько полок показывать.
     *
     *  Столько, сколько рубрик в каталоге: решение владельца от 15
     *  сентября — все карточки должны быть в полках. Потолок в шесть
     *  штук означал бы, что записи тринадцатой рубрики на витрине не
     *  видно вовсе.
     *
     *  Ограничение оставлено на случай справочника из сотни рубрик:
     *  сорок полок — это уже не витрина, и остаток уйдёт в «Другое». */
    get maxShelves() {
        return 24;
    }

    /** Ниже какого числа записей рубрика не становится полкой. Полка из
     *  одной карточки читается как ошибка; такие рубрики складываются в
     *  «Другое» — вместе с теми записями, у которых рубрики нет. */
    get minPerShelf() {
        return 3;
    }

    /** Имя полки для всего, что не попало в остальные. */
    get otherLabel() {
        return "Другое";
    }

    async load() {
        const domain = this.props.domain || [];
        await this.readFieldInfo();
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
        const подпись = (значение) => {
            // У списка выбора сервер отдаёт техническое значение —
            // `equipment`, `barter`, `running`, — и на полке стояло бы
            // именно оно. Метки берём у самой модели, одним запросом на
            // каталог.
            if (Array.isArray(значение)) {
                return значение[1];
            }
            return this.labels[значение] || значение;
        };
        const годные = groups
            .filter((g) => g[this.props.field] && считать(g) >= this.minPerShelf)
            .sort((a, b) => считать(b) - считать(a))
            .slice(0, this.maxShelves);

        // Всё, что не стало полкой: пустая рубрика и рубрики, в которых
        // меньше трёх записей. Владелец 15 сентября: «все карточки
        // должны быть в полках, если они не попадают в те категории
        // которые есть — то создаём категорию другие и определяем их
        // туда». Полка «Другое» и есть эта категория — собранная на
        // лету, чтобы каталог не оставлял записей за витриной даже
        // тогда, когда рубрику проставить не успели.
        const взятые = годные.map((g) => {
            const значение = g[this.props.field];
            return Array.isArray(значение) ? значение[0] : значение;
        });
        const остаток = groups
            .filter((g) => {
                const значение = g[this.props.field];
                const id = Array.isArray(значение) ? значение[0] : значение;
                return !взятые.includes(id);
            })
            .reduce((сумма, g) => сумма + считать(g), 0);
        const условиеОстатка = ["!", [this.props.field, "in", взятые]];

        // Одна полка — это не витрина, а тот же каталог с заголовком.
        // Так выходит там, где правила доступа оставили человеку
        // несколько записей одного вида: полок нет, каталог работает
        // как обычно.
        if (годные.length + (остаток ? 1 : 0) < 2) {
            return;
        }

        // Записи всех полок одним запросом: модель грузит их отбором по
        // списку рубрик, а разложить по полкам можно уже здесь. Шесть
        // запросов вместо одного полка не стоит.
        const рубрики = взятые;
        await this.модельПолок.load({
            domain: domain.concat([[this.props.field, "in", рубрики]]),
            limit: this.perShelf * this.maxShelves,
        });
        const записи = this.модельПолок.root.records || [];
        const поПолкам = new Map(рубрики.map((id) => [id, []]));
        for (const запись of записи) {
            // Значение поля у записи модели приходит в трёх видах: пара
            // [номер, название] у старых сборок, объект с `id` у
            // нынешних, простое значение у списка выбора. Разбираем все
            // три здесь, иначе полка пустая, а ошибки нет.
            const значение = запись.data[this.props.field];
            const id = Array.isArray(значение) ? значение[0]
                : (значение && typeof значение === "object" ? значение.id : значение);
            const полка = поПолкам.get(id);
            if (полка && полка.length < this.perShelf) {
                полка.push(запись);
            }
        }

        for (const g of годные) {
            const значение = g[this.props.field];
            const id = Array.isArray(значение) ? значение[0] : значение;
            this.state.shelves.push({
                id,
                label: подпись(значение),
                count: считать(g),
                records: поПолкам.get(id) || [],
                domain: domain.concat([[this.props.field, "=", id]]),
            });
        }

        if (остаток) {
            // Вторым заходом, а не первым: домен «всё, кроме взятых»
            // объединить с доменом полок одним запросом нельзя, а
            // грузить остаток всегда, когда его нет, — лишний запрос
            // на каждый каталог.
            await this.модельПолок.load({
                domain: domain.concat(условиеОстатка),
                limit: this.perShelf,
            });
            this.state.shelves.push({
                id: "__other__",
                label: this.otherLabel,
                count: остаток,
                // Обрезаем здесь, а не пределом загрузки: `load` предел
                // в параметрах не всегда соблюдает, и в полку приходили
                // все шестьдесят записей остатка. Лишние карточки ряд
                // прячет, но собирать их всё равно незачем.
                records: (this.модельПолок.root.records || []).slice(0, this.perShelf),
                domain: domain.concat(условиеОстатка),
            });
        }
    }

    /**
     * Метки рубрики.
     *
     * У списка выбора сервер отдаёт техническое значение — `equipment`,
     * `barter`, `running`, — и на заголовке полки стояло бы именно оно.
     * Метки живут в описании поля, поэтому спрашиваем модель, одним
     * запросом на каталог. У `many2one` название приходит с данными, и
     * спрашивать нечего.
     */
    async readFieldInfo() {
        this.labels = {};
        const info = await this.orm.call(
            this.props.resModel, "fields_get",
            [[this.props.field], ["type", "selection"]]);
        const поле = info[this.props.field] || {};
        for (const [код, метка] of поле.selection || []) {
            this.labels[код] = метка;
        }
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
            // Домен берётся у самой полки: у «Другого» он не «рубрика
            // равна», а «рубрика не из взятых», и вывести его из
            // номера полки нельзя.
            domain: shelf.domain,
            views: [[false, "kanban"], [false, "list"], [false, "form"]],
        });
    }
}
