/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { KanbanRecord } from "@web/views/kanban/kanban_record";
import { COOP_FAVORABLE, CoopFavoriteHeart } from "@coop_theme/js/favorite";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { ListController } from "@web/views/list/list_controller";
import { FormController } from "@web/views/form/form_controller";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { Pager } from "@web/core/pager/pager";
import { CoopTabs } from "@coop_theme/js/shell";
import { CoopFilters, coopFiltersUi } from "@coop_theme/js/catalog_filters";
import { CoopMap } from "@coop_theme/js/catalog_map";
import { CoopShelves } from "@coop_theme/js/catalog_shelves";
import { coopSort, parseOrder } from "@coop_theme/js/catalog_sort";
import { reactive, useEffect, useState } from "@odoo/owl";

/**
 * Виды каталога в одном переключателе: плиткой, списком, на карте — три
 * из макета — и таблица движка четвёртой.
 *
 * Таблица — отдельное представление Odoo, и его кнопка в переключателе
 * уже есть. Плитка и список — одно представление с разной раскладкой
 * карточки: второго канбана в одном действии Odoo не допускает, а
 * дублировать разметку незачем — в прототипе она тоже одна, и
 * переключается класс на списке.
 *
 * Поэтому кнопка «плиткой» подставляется в штатный переключатель рядом с
 * канбаном и списком. Своей группы кнопок нет намеренно: два
 * переключателя на одном экране заставляют гадать, чем они отличаются.
 */
const STORAGE_KEY = "coop-catalog-view";

function readSavedLayout() {
    // localStorage может быть недоступен — в приватном окне или при
    // запрете хранилища. Тогда просто плитка, как по умолчанию.
    try {
        return browser.localStorage.getItem(STORAGE_KEY);
    } catch {
        return null;
    }
}

// Общее состояние вида: его читает и панель управления, чтобы подсветить
// нужную кнопку, и представление, чтобы поставить класс на корень.
const MODES = ["tiles", "rows", "map"];

export const coopLayout = reactive({
    mode: MODES.includes(readSavedLayout()) ? readSavedLayout() : "tiles",
});

export function setCoopLayout(mode) {
    coopLayout.mode = mode;
    try {
        browser.localStorage.setItem(STORAGE_KEY, mode);
    } catch {
        // Не сохранилось — вид всё равно переключился, просто забудется.
    }
}

export class CoopCatalogKanbanController extends KanbanController {
    // Постраничная навигация рисуется внизу списка, как в макете, а не в
    // панели сверху. Данные берутся те же, что у штатной: представление
    // уже сложило их в настройку экрана, и считать их второй раз значило
    // бы завести второй счётчик, который разойдётся с первым.
    static components = { ...KanbanController.components, Pager, CoopFilters, CoopMap, CoopShelves };

    // Кнопка создания подписывается по разделу: «Добавить ресурс»,
    // «Добавить проект». Штатное «Новое» ничего не говорит о том, что
    // именно заводится, а в макете подпись у каждого каталога своя.
    get coopCreateLabel() {
        return this.props.context?.coop_create_label || "Добавить";
    }

    /** Вернуться к плиткам. Нужна карте: выбрав город, человек хочет
     *  увидеть тамошние записи, а не карту с одной оставшейся меткой.
     *  Передаётся карте свойством — своей ссылки на переключатель вида у
     *  неё нет намеренно, иначе модули ссылались бы друг на друга. */
    coopShowTiles() {
        setCoopLayout("tiles");
    }

    /** По какому полю раскладывать полки. Объявляется в действии
     *  каталога (`coop_shelf_field` в контексте), а не угадывается: у
     *  каждого раздела своя рубрикация, и промах здесь виден сразу всем.
     *  Не объявлено — полок нет, каталог работает как раньше. */
    get coopShelfField() {
        return this.props.context?.coop_shelf_field || false;
    }

    /** Полки только на чистом экране: без поиска, без отбора, без
     *  группировки и только в плитке. В списке витрина по рубрикам
     *  спорит с самим списком. */
    get coopShelvesVisible() {
        return Boolean(this.coopShelfField)
            && this.coopLayout.mode === "tiles"
            && this.coopSearchIsClean;
    }

    /** Есть ли полки на самом деле.
     *
     *  «Полки включены» и «полки собрались» — разные вещи: рубрик может
     *  быть меньше двух, и тогда полок нет. Лента под ними смотрит
     *  именно сюда, иначе экран остаётся пустым — ни полок, ни ленты.
     *  Пока полки грузятся, лента тоже ждёт: иначе она мелькнёт и
     *  исчезнет. */
    get coopShelvesFilled() {
        return this.coopShelvesVisible
            && (this.coopShelves.status === "loading" || this.coopShelves.count > 0);
    }

    /** Полки сообщили, сколько их собралось. Зовётся ими после того, как
     *  они встали на экран, — раньше нельзя: см. `catalog_shelves.js`. */
    coopShelvesLoaded(count) {
        this.coopShelves.status = "ready";
        this.coopShelves.count = count;
    }

    /** Порядок для полок.
     *
     *  Полки грузят записи своей моделью, и порядок им надо передать
     *  отдельно: без него они брали записи в порядке базы. На торгах это
     *  было видно сразу — из ста пяти лотов идут семь, и на витрине
     *  стояли одни завершённые, хотя в панели выбран порядок «сначала
     *  идущие».
     *
     *  Выбранный человеком порядок, а если он ничего не выбирал —
     *  тот, что объявлен в самом представлении. */
    get coopShelfOrder() {
        const order = this.coopSort?.orders?.[this.props.resModel];
        if (order) {
            return parseOrder(order);
        }
        return this.props.archInfo?.defaultOrder || [];
    }

    /** Домен самого раздела — без того, что человек выбрал в поиске.
     *
     *  `props.domain` для этого не годится: он уже с поиском. Домен
     *  действия лежит отдельно, в `globalDomain` поисковой модели, —
     *  измерено 15 сентября 2026 там же, где выяснилось про фасеты. */
    get coopBaseDomain() {
        return this.env.searchModel?.globalDomain || [];
    }

    /** Ничего не искали и не отбирали.
     *
     *  По фасетам поиска — по тем самым плашкам, которые видно в строке
     *  поиска. Прошлая попытка сделать это через `searchModel` считалась
     *  непроверяемой, и условие тогда убрали; теперь измерено: в
     *  подокружении контроллера `searchModel` есть, `facets` пуст на
     *  чистом экране и содержит по записи на каждое условие после
     *  поиска или отбора.
     *
     *  По домену это не считается, хотя так и было сделано сначала:
     *  `props.domain` у контроллера — уже отобранный домен, тот же
     *  самый, что у модели. Сравнивать его было не с чем, и условие
     *  всегда выходило истинным — полки не пропадали никогда.
     *
     *  Считается не «фасетов нет», а «фасеты те же, с какими раздел
     *  открылся». Разница не теоретическая: у биржи мощностей, биржи
     *  токенов и витрины уступок в действии стоит `search_default_…`,
     *  фасет появляется до того, как человек что-то нажал, — и по
     *  правилу «фасетов нет» полок в этих трёх каталогах не было
     *  никогда, вместо них открывалась лента. Измерено 15 сентября 2026:
     *  полок 0, в ленте 86 карточек, тогда как решение владельца от того
     *  же дня — «в каталоге только полки».
     *
     *  Отбор самого раздела и отбор человека — разные вещи: первый
     *  говорит, что это за каталог, второй — что человек в нём ищет.
     *  Витрина мешает только второму. */
    get coopSearchIsClean() {
        // Через `?.`: до готовности подокружения `searchModel` может ещё
        // не быть, а падать в геттере, от которого зависит весь экран,
        // нельзя.
        const model = this.env.searchModel;
        if (!model) {
            return true;
        }
        const facetSignature = (facet) => JSON.stringify(
            [facet.type, facet.title, facet.values || []]);
        const currentFacets = (model.facets || []).map(facetSignature);
        // Отбор раздела снимается один раз — при первом же обращении, то
        // есть на первой отрисовке, когда умолчания действия уже
        // применены, а человек ещё ничего не нажимал.
        if (this.sectionFacets === undefined) {
            this.sectionFacets = currentFacets;
        }
        // Подмножество, а не равенство: сняв умолчание раздела, человек
        // тоже оказывается на чистом экране, и полки должны вернуться.
        return currentFacets.every((key) => this.sectionFacets.includes(key));
    }

    setup() {
        super.setup();
        this.coopLayout = useState(coopLayout);
        // Состояние полок держит сам каталог, а не общая переменная, в
        // которую писали полки. Общая переменная давала круг: запись из
        // ещё не отрисованного потомка отменяла отрисовку родителя, и
        // всё начиналось заново — пятьсот запросов в минуту при пустом
        // экране. Теперь полки сообщают итог вызовом, после появления
        // на экране; подробности — в `catalog_shelves.js`.
        //
        // «loading» с самого начала: пока полки не сказали своё число,
        // лента не показывается, иначе она мелькнёт и исчезнет.
        this.coopShelves = useState({ status: "loading", count: 0 });
        this.coopSort = useState(coopSort);
        // Перезагружаем список, когда сменили признак сортировки. Через
        // общее состояние, а не через событие: порядок выбирают в панели
        // управления, а перезагружает представление — прямой ссылки
        // между ними у Odoo нет.
        useEffect(
            () => {
                const order = this.coopSort.orders[this.props.resModel];
                if (order) {
                    // Домен передаётся вместе с порядком, и это не
                    // лишнее слово. «Сбросить» в панели меняет разом два
                    // условия: снимает отбор и возвращает порядок по
                    // умолчанию. Отбор снимается через модель поиска —
                    // она сообщит об этом следующим кадром, — а порядок
                    // перезагружает список сразу же. Без домена эта
                    // перезагрузка успевала взять старый, ещё отобранный,
                    // и приходила второй: панель показывала «Показать
                    // результаты · 20», а в каталоге оставалось три
                    // карточки от снятого фильтра.
                    this.model.load({
                        orderBy: parseOrder(order),
                        domain: this.props.domain,
                    });
                }
            },
            () => [this.coopSort.orders[this.props.resModel]]
        );
    }
}

CoopCatalogKanbanController.template = "coop_theme.CatalogKanbanView";

/**
 * Сердечко «в избранное» на карточке — решение 408.
 *
 * В макете оно стоит на каждой карточке в двенадцати каталогах (15
 * сентября 2026, `69c9afe`), в MVP было только у ресурсов — строкой в
 * разметке их карточки. Чтобы не править разметку одиннадцати модулей по
 * одной строке, сердечко ставит сам общий вид каталогов: карточка —
 * `article` движка, сердечко — поверх её правого верхнего угла, то есть
 * поверх снимка, как в макете.
 *
 * Список — те же каталоги, что вкладки страницы «Избранное»
 * (`models/coop_favorite_page.py`, `KINDS`). Ресурсов здесь нет: у них
 * сердечко своё, в разметке карточки. Лента, сделки, заявки и прочие
 * списки дел — не то, что откладывают «на потом», сердечка там нет.
 */
export class CoopCatalogKanbanRecord extends KanbanRecord {
    static template = "coop_theme.CatalogKanbanRecord";
    static components = { ...KanbanRecord.components, CoopFavoriteHeart };

    get coopFavorable() {
        return COOP_FAVORABLE.includes(this.props.record.resModel) && this.props.record.resId;
    }
}

export class CoopCatalogKanbanRenderer extends KanbanRenderer {
    static components = { ...KanbanRenderer.components, KanbanRecord: CoopCatalogKanbanRecord };
}

registry.category("views").add("coop_catalog_kanban", {
    ...kanbanView,
    Controller: CoopCatalogKanbanController,
    Renderer: CoopCatalogKanbanRenderer,
});

// Вкладки раздела рисуются самой панелью: только так они попадают в одну
// строку с переключателем вида, а поиск с кнопкой добавления — в
// следующую. Отдельным блоком над панелью этого не собрать.
ControlPanel.components = { ...ControlPanel.components, CoopTabs };

patch(ControlPanel.prototype, {
    /**
     * Кнопка отбора стоит здесь, а не над каталогом.
     *
     * На узком экране панель отбора становилась карточкой во всю ширину
     * прямо над списком: полоса вкладок, строка поиска, кнопка
     * добавления, кнопка фильтра — и только потом первое объявление.
     * Фильтр нужен раз на десяток открытий каталога, а место занимал
     * всегда и всегда сверху. Теперь он открывается нижней шторкой, как
     * в макете, а кнопка живёт в строке каталога.
     */
    setup() {
        super.setup(...arguments);
        // Через `useState`, а не напрямую: иначе кнопка не узнает, что
        // шторку закрыли затемнением или кнопкой «Показать результаты», —
        // и `aria-expanded` остался бы `true` при закрытой панели.
        this.coopFilters = useState(coopFiltersUi);
    },

    /** Открыть или убрать шторку отбора. Методом, а не присваиванием
     *  прямо в шаблоне: присваивание в выражении шаблона молча ничего не
     *  делало — кнопка нажималась, состояние не менялось. */
    coopToggleFilters() {
        this.coopFilters.open = !this.coopFilters.open;
    },

    /**
     * Каталог платформы узнаётся по признаку в контексте действия. Признак
     * стоит на самом действии, поэтому виден и в канбане, и в списке — в
     * отличие от класса представления, который в списке недоступен.
     */
    get coopIsCatalog() {
        return Boolean(this.env.searchModel?.globalContext?.coop_catalog);
    },

    /**
     * Панель отбора нужна не только каталогам с плитками.
     *
     * Кнопка, открывающая её на узком экране, показывалась ровно там,
     * где стоит признак каталога, — а каталог расширений собран без
     * него: от общего каталога ему нужен отбор, но не переключатель
     * «плиткой / списком / на карте» (карты у модуля не бывает) и не
     * плиточная геометрия карточки. Признак у панели поэтому свой:
     * `coop_filters` значит «есть чем отбирать», `coop_catalog`
     * по-прежнему включает его заодно.
     */
    get coopHasFilters() {
        const context = this.env.searchModel?.globalContext || {};
        return Boolean(context.coop_catalog || context.coop_filters);
    },

    /**
     * Строка вкладок нужна не только каталогам.
     *
     * Раньше она показывалась ровно там, где стоял признак каталога, и
     * это совпадало: разделы платформы были каталогами. С «Токеномикой»
     * совпадение кончилось — у неё четыре вкладки поверх обычных списков
     * и ни одного каталога, и вкладки просто не появились. Ошибки при
     * этом не было никакой: признака нет — рисовать нечего.
     *
     * Поэтому признак заведён свой: `coop_section` значит «экран раздела
     * платформы», а `coop_catalog` — «и вдобавок каталог с плитками и
     * переключателем вида». Второе по-прежнему включает первое, но
     * первое больше не требует второго.
     */
    get coopHasTabs() {
        // На карточке записи вкладок раздела нет.
        //
        // Действие у карточки то же, что у каталога, и признак раздела
        // достаётся ей заодно: на странице аукциона выходило «← Аукционы»
        // и тут же вкладка «Все торги» — две дороги в одно место, рядом.
        // Владелец 16 сентября 2026: «это одна и та же страница, для чего
        // так». Вкладки называют разделы витрины и место им на витрине;
        // из карточки наружу ведёт путь и кнопка возврата.
        const context = this.env.searchModel?.globalContext || {};
        if (this.env.config?.viewType === "form") {
            // Кроме настроек: там сам раздел собран из карточек — вкладка
            // «Аккаунт» и есть экран, а не витрина записей. Признак на
            // действии, а не угадывание по виду: карточка аукциона и
            // экран настроек — оба формы, и различить их можно только
            // тем, что про них сказано.
            return Boolean(context.coop_settings);
        }
        return Boolean(context.coop_catalog || context.coop_section);
    },

    /**
     * Крошка одна — значит, возвращаться по ней некуда, а её текст
     * повторяет заголовок страницы прямо под ней. Считается по самим
     * крошкам, а не по признаку действия: так полоса пропадает везде,
     * где она пустая, а не только на «Моей странице».
     *
     * Каталог исключён, и это не мелочь. Признак вешает класс, который
     * снимает у полосы всё, чем она видна, — поля, границу, фон и
     * промежутки, причём через `!important`. Для пустой полосы это
     * верно, а у каталога в ней живут вкладки раздела, поиск, кнопка
     * добавления и переключатель вида: крошка там тоже одна, и все они
     * слипались в сплошную строку без единого промежутка. Отсюда шли
     * нули в замерах: вкладки вплотную к полю поиска, поле вплотную к
     * кнопке.
     */
    get coopSingleCrumb() {
        return !this.coopIsCatalog && (this.breadcrumbs?.length || 0) <= 1;
    },

    /**
     * Кнопки переключателя. У каталога канбан раздваивается на «плиткой» и
     * «канбаном»: это одно представление в двух раскладках.
     */
    get coopViewEntries() {
        const entries = this.env.config.viewSwitcherEntries || [];
        if (!this.coopIsCatalog) {
            return entries;
        }
        return entries.flatMap((entry) => {
            if (entry.type === "list") {
                // «Списком» в макете называется вид карточками во всю
                // ширину, а не таблица движка. Оставить у таблицы то же
                // слово значит поставить в один ряд две кнопки с одной
                // подписью.
                return [{ ...entry, name: "Таблицей", icon: "fa fa-table" }];
            }
            if (entry.type !== "kanban") {
                return [entry];
            }
            return [
                {
                    ...entry,
                    type: "coop_tiles",
                    name: "Плиткой",
                    icon: "oi oi-view-kanban",
                    active: entry.active && coopLayout.mode === "tiles",
                },
                {
                    ...entry,
                    name: "Списком",
                    icon: "fa fa-align-justify",
                    active: entry.active && coopLayout.mode === "rows",
                },
                {
                    ...entry,
                    type: "coop_map",
                    name: "На карте",
                    icon: "fa fa-map-marker",
                    active: entry.active && coopLayout.mode === "map",
                },
            ];
        });
    },

    switchView(viewType, isMiddleClick) {
        const layouts = { coop_tiles: "tiles", kanban: "rows", coop_map: "map" };
        if (this.coopIsCatalog && viewType in layouts) {
            setCoopLayout(layouts[viewType]);
            const active = this.env.config.viewSwitcherEntries?.find((view) => view.active);
            if (active?.type === "kanban") {
                // Уже в канбане — меняется только раскладка, перезагружать
                // представление незачем.
                return;
            }
            return super.switchView("kanban", isMiddleClick);
        }
        return super.switchView(viewType, isMiddleClick);
    },
});

// Кнопка создания в списках подписывается так же, как в каталоге.
//
// В плитке подпись своя с самого начала — «Добавить ресурс», «Добавить
// вакансию»: так в макете, и по ней видно, что именно заводится. А
// списки — «Мои вакансии», «Мои ресурсы», «Мои закупки» — остались со
// штатным «Новое». Владелец 15 сентября 2026 указал на это прямо:
// кнопка встречается много где и везде называется одинаково, тогда как
// в макете у неё своё место и своё название в каждом разделе.
//
// Патч общий, а не по `js_class` у каждого списка: подпись берётся из
// того же `coop_create_label`, что и в плитке, и там, где его в
// действии нет, остаётся штатное «Новое».
// Тот же геттер списку и форме: «Новое» встречается и там, и там, а
// подпись у раздела одна.
// Функцией, а не объектом: движок запрещает прикладывать один объект
// заплатки дважды (`patching_code`, «Applying the same patch to multiple
// objects»). Здесь внутри нет `super`, и до поры это сходило с рук, но
// правило движка не про «когда заметно», а про то, как заплатка
// устроена.
function createLabelPatch() {
    return {
    get coopCreateLabel() {
        // Из действия, а не из `props.context`. Списку достаётся контекст
        // поиска, а не действия: `WithSearch` передаёт вниз
        // `searchModel.context`, и от объявленного в действии там
        // остаются только `lang`, `tz`, `uid` и список компаний —
        // измерено 15 сентября 2026, подпись просто не доезжала. В
        // плитке контекст свой, поэтому там подпись работала с самого
        // начала, и расхождение выглядело необъяснимым.
        const action = this.env.services.action?.currentAction;
        return action?.context?.coop_create_label
            || this.props.context?.coop_create_label
            || "Новое";
    },
    };
}

patch(ListController.prototype, createLabelPatch());
patch(FormController.prototype, createLabelPatch());

/**
 * Своя страница добавления вместо штатного режима создания.
 *
 * Каталог объявляет в контексте действия имя метода — `coop_create_method`,
 * — и кнопка «Добавить…» зовёт его вместо того, чтобы открывать пустую
 * форму. Метод заводит черновик и возвращает действие на свою страницу
 * размещения.
 *
 * Зачем так, а не режимом создания у обычной формы. Владелец 22 сентября
 * 2026 выбрал «одной страницей, но с автосохранением черновика».
 * Автосохранение на платформе держится на том, что каждое поле сохраняет
 * себя само, — а сохранять себя поле может только в существующую запись.
 * Значит запись должна появиться до первого нажатия клавиши, и завести её
 * может только сервер.
 *
 * Признаком в контексте, а не списком моделей в коде: страниц добавления
 * впереди ещё пять — человек, организация, навык, проект, вакансия, — и
 * каждая должна ложиться сюда же, не трогая этот файл.
 *
 * Имена латиницей: решение 352.
 */
function coopOwnCreate() {
    return {
    async createRecord() {
        const action = this.env.services.action?.currentAction;
        const method =
            action?.context?.coop_create_method ||
            this.props.context?.coop_create_method;
        if (!method) {
            return super.createRecord(...arguments);
        }
        try {
            // Без позиционных аргументов: метод объявлен `@api.model`,
            // записей ему не передают. Пустой список здесь означал бы
            // аргумент, которого метод не принимает.
            const next = await this.env.services.orm.call(
                this.props.resModel, method, []);
            return this.env.services.action.doAction(next);
        } catch (error) {
            // Не сработало — открываем обычное создание, а не оставляем
            // человека с кнопкой, которая ничего не делает.
            console.warn("[каталог] своя страница добавления не открылась:", error);
            return super.createRecord(...arguments);
        }
    },
    };
}

// Каждому прототипу — свой объект, и создаёт его функция.
//
// Так прямо написано в документации движка
// (`developer/reference/frontend/patching_code`, раздел «Applying the same
// patch to multiple objects»): объект заплатки можно приложить только
// один раз, и **копировать его нельзя** — при копии `super` перестаёт
// указывать куда надо. Там же пример падения: после клонированной
// заплатки вызов метода даёт «is not a function».
//
// Я прошёл мимо обоих запретов подряд: сперва приложил один объект к
// двум прототипам, потом «починил» это копией через расширение — то
// самое, что документация запрещает отдельным предупреждением. Отсюда и
// падение каталогов.
patch(KanbanController.prototype, coopOwnCreate());
patch(ListController.prototype, coopOwnCreate());

// Строка поиска каталога: без штатного выпадающего меню и со своей
// подсказкой. Признак каталога тот же, что у панели управления, — из
// контекста действия.
patch(SearchBar.prototype, {
    get coopIsCatalog() {
        return Boolean(this.env.searchModel?.globalContext?.coop_catalog);
    },

    get coopPlaceholder() {
        return this.coopIsCatalog ? "Начните вводить название" : "Поиск...";
    },
});
