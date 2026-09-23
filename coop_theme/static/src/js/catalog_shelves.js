/** @odoo-module **/

import { Component, onMounted, onWillStart, useState } from "@odoo/owl";
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
/**
 * Собрались ли полки — наружу, для ленты под ними.
 *
 * Лента пряталась по одному признаку «полки включены», а включены они и
 * тогда, когда собрать их не из чего: рубрик меньше двух, и полок нет.
 * Экран оставался пустым — ни полок, ни ленты. Так было видно на полке
 * «Друзья»: шесть человек, счётчик в отборе показывает шесть, а
 * карточек ноль.
 *
 * Поэтому лента смотрит не на настройку, а на итог: пока полки грузятся
 * — ждём (иначе лента мелькнёт и исчезнет), собрались — лента не нужна,
 * не собрались — лента возвращается.
 *
 * Итог сообщается вызовом `onLoaded` и только после того, как полки
 * встали на экран, а не общей переменной, в которую они писали из
 * `onWillStart` и `onWillUnmount`.
 *
 * Разница не стилистическая. Переменную читал каталог — родитель этих
 * же полок. Запись в неё из ещё не отрисованного потомка отменяла
 * отрисовку родителя, тот начинал её заново и создавал полки заново,
 * полки снова писали в переменную — и так до бесконечности. 21 сентября
 * 2026 на боевой это выглядело так: пятьсот запросов в минуту из одной
 * вкладки, на экране пусто, служба раз за разом перезапускалась по
 * пределу памяти. Единственный каталог без полок, расширения,
 * открывался нормально — им и был поставлен опыт.
 *
 * Правило общее: потомок не трогает состояние, от которого зависит
 * отрисовка родителя, пока эта отрисовка идёт. После `onMounted` —
 * можно: там перерисовка родителя обычная, а не отмена незаконченной.
 */

export class CoopShelves extends Component {
    static template = "coop_theme.CatalogShelves";
    static components = { KanbanRecord };
    static props = {
        resModel: { type: String },
        field: { type: String },
        domain: { type: Array, optional: true },
        // Порядок передаётся снаружи: своей модели полки грузят записи
        // сами, и без него брали их в порядке базы. На торгах это было
        // видно сразу — витрина показывала завершённые лоты при
        // выбранном порядке «сначала идущие».
        orderBy: { type: Array, optional: true },
        // Разбор представления и список полей — те же, по которым
        // каталог рисует свои карточки. Полка рисует ими же: два вида
        // карточек на одном экране владелец назвал разнобоем, и был
        // прав — витрина показывает тот же каталог, а не другой раздел.
        archInfo: { type: Object },
        fields: { type: Object },
        openRecord: { type: Function, optional: true },
        // Сколько полок собралось. Зовётся один раз, после появления на
        // экране: по этому числу каталог решает, показывать ли ленту.
        onLoaded: { type: Function, optional: true },
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
        this.shelvesModel = new RelationalModel(
            this.env, this.modelParams, {
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

        // Итог — каталогу, и только теперь: загрузка к этому времени
        // закончена (она вся в `onWillStart`), а отрисовка родителя уже
        // завершилась, и сообщение её не отменяет.
        onMounted(() => {
            this.props.onLoaded?.(this.state.shelves.length);
        });
    }

    get modelParams() {
        const { activeFields, fields } = extractFieldsFromArchInfo(
            this.props.archInfo, this.props.fields);
        // Поле рубрики карточке не нужно и в разборе представления его
        // может не быть — у закупок «Раздел» в канбане не показывается.
        // А разложить записи по полкам без него нечем: значение приходит
        // пустым, полки выходят с заголовками и без карточек.
        const description = this.props.fields[this.props.field];
        if (description && !activeFields[this.props.field]) {
            addFieldDependencies(activeFields, fields,
                [{ name: this.props.field, type: description.type }]);
        }
        // `groupBy` и `orderBy` пустыми списками, а не пропущенными:
        // модель их не подставляет, а `_getNextConfig` по ним проходит
        // `map` и `length` — без них загрузка падает на `undefined`.
        return {
            config: {
                resModel: this.props.resModel, activeFields, fields,
                domain: [], groupBy: [],
                orderBy: this.props.orderBy || [], context: {},
            },
            limit: this.perShelf * this.maxShelves,
        };
    }

    /** Сколько карточек грузим на полку.
     *
     *  Показывается меньше — столько, сколько помещается в два ряда;
     *  остальные ждут за «Смотреть все». Двенадцать взяты с запасом: в
     *  ряд встаёт от двух карточек на узкой области до шести на широкой,
     *  и при восьми второй ряд на широком экране выходил неполным. */
    get perShelf() {
        return 12;
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

    /** Номера полок, на которые попадает запись.
     *
     *  Значение поля приходит в пяти видах, и все пять встречаются в
     *  одном и том же каталоге:
     *
     *  * пара `[номер, название]` — связь у старых сборок;
     *  * объект с `id` — связь у нынешних;
     *  * простое значение — список выбора;
     *  * список номеров — множественная связь;
     *  * объект со списком `records` — она же у модели представления.
     *
     *  Разбираем все здесь, а не в цикле раскладки: перепутанный вид
     *  даёт не ошибку, а пустую полку, и искать причину потом дороже.
     */
    shelfIdsOf(record) {
        const value = record.data[this.props.field];
        if (value === undefined || value === null || value === false) {
            return [];
        }
        if (Array.isArray(value)) {
            // Пара `[номер, название]` у связи — именно пара, а не
            // список из двух номеров: второе значение строка.
            if (value.length === 2 && typeof value[1] === "string") {
                return [value[0]];
            }
            return value.map((item) => (
                item && typeof item === "object" ? item.id : item
            ));
        }
        if (typeof value === "object") {
            if (Array.isArray(value.records)) {
                return value.records.map((item) => item.resId ?? item.id);
            }
            if (Array.isArray(value.resIds)) {
                return value.resIds;
            }
            return value.id === undefined ? [] : [value.id];
        }
        return [value];
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
        const countOf = (g) => g.__count ?? g[this.props.field + "_count"] ?? 0;
        const labelOf = (value) => {
            // У списка выбора сервер отдаёт техническое значение —
            // `equipment`, `barter`, `running`, — и на полке стояло бы
            // именно оно. Метки берём у самой модели, одним запросом на
            // каталог.
            if (Array.isArray(value)) {
                return value[1];
            }
            return this.labels[value] || value;
        };
        const eligible = groups
            .filter((g) => g[this.props.field] && countOf(g) >= this.minPerShelf)
            .sort((a, b) => countOf(b) - countOf(a))
            .slice(0, this.maxShelves);

        // Всё, что не стало полкой: пустая рубрика и рубрики, в которых
        // меньше трёх записей. Владелец 15 сентября: «все карточки
        // должны быть в полках, если они не попадают в те категории
        // которые есть — то создаём категорию другие и определяем их
        // туда». Полка «Другое» и есть эта категория — собранная на
        // лету, чтобы каталог не оставлял записей за витриной даже
        // тогда, когда рубрику проставить не успели.
        const takenIds = eligible.map((g) => {
            const value = g[this.props.field];
            return Array.isArray(value) ? value[0] : value;
        });
        const remainder = groups
            .filter((g) => {
                const value = g[this.props.field];
                const id = Array.isArray(value) ? value[0] : value;
                return !takenIds.includes(id);
            })
            .reduce((sum, g) => sum + countOf(g), 0);
        const remainderDomain = ["!", [this.props.field, "in", takenIds]];

        // Одна полка — это не витрина, а тот же каталог с заголовком.
        // Так выходит там, где правила доступа оставили человеку
        // несколько записей одного вида: полок нет, каталог работает
        // как обычно.
        if (eligible.length + (remainder ? 1 : 0) < 2) {
            return;
        }

        // Записи всех полок одним запросом: модель грузит их отбором по
        // списку рубрик, а разложить по полкам можно уже здесь. Шесть
        // запросов вместо одного полка не стоит.
        const categoryIds = takenIds;
        await this.shelvesModel.load({
            domain: domain.concat([[this.props.field, "in", categoryIds]]),
            orderBy: this.props.orderBy || [],
            limit: this.perShelf * this.maxShelves,
        });
        const records = this.shelvesModel.root.records || [];
        const recordsByShelf = new Map(categoryIds.map((id) => [id, []]));
        for (const record of records) {
            // Запись попадает на КАЖДУЮ свою полку, а не на одну.
            // Специализаций у человека несколько (решение 381): столяр,
            // который ещё и водитель, должен быть виден обоими. При
            // одиночном поле список из одного значения — и поведение то
            // же, что было.
            for (const id of this.shelfIdsOf(record)) {
                const shelf = recordsByShelf.get(id);
                if (shelf && shelf.length < this.perShelf
                        && !shelf.includes(record)) {
                    shelf.push(record);
                }
            }
        }

        for (const g of eligible) {
            const value = g[this.props.field];
            const id = Array.isArray(value) ? value[0] : value;
            this.state.shelves.push({
                id,
                label: labelOf(value),
                count: countOf(g),
                records: recordsByShelf.get(id) || [],
                domain: domain.concat([[this.props.field, "=", id]]),
            });
        }

        if (remainder) {
            // Вторым заходом, а не первым: домен «всё, кроме взятых»
            // объединить с доменом полок одним запросом нельзя, а
            // грузить остаток всегда, когда его нет, — лишний запрос
            // на каждый каталог.
            await this.shelvesModel.load({
                domain: domain.concat(remainderDomain),
                orderBy: this.props.orderBy || [],
                limit: this.perShelf,
            });
            this.state.shelves.push({
                id: "__other__",
                label: this.otherLabel,
                count: remainder,
                // Обрезаем здесь, а не пределом загрузки: `load` предел
                // в параметрах не всегда соблюдает, и в полку приходили
                // все шестьдесят записей остатка. Лишние карточки ряд
                // прячет, но собирать их всё равно незачем.
                records: (this.shelvesModel.root.records || []).slice(0, this.perShelf),
                domain: domain.concat(remainderDomain),
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
        const field = info[this.props.field] || {};
        for (const [code, label] of field.selection || []) {
            this.labels[code] = label;
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
