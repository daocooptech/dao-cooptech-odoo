/** @odoo-module **/

import { Component, onWillStart, useExternalListener, useRef, useState, useSubEnv } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

import { fields } from "@mail/core/common/record";
import { Thread as ThreadComponent } from "@mail/core/common/thread";
import { Composer } from "@mail/core/common/composer";
import { Thread } from "@mail/core/common/thread_model";
import { composerActionsRegistry } from "@mail/core/common/composer_actions";

// Luxon в движке подключён библиотекой, а не модулем: импортировать его
// нельзя — сборщик не найдёт «luxon», наш файл не определится, и вместе
// с ним не окажется в реестре действие раздела. Экран тогда пустой.
const { DateTime } = luxon;

/**
 * Вложение и голосовое сообщение — как в макете, отдельными видимыми
 * кнопками, а не пунктами скрытого меню «+».
 *
 * У движка они попадают в список «прочих» действий и всплывают только
 * по клику на «+» — экономия места, которая на широком экране обернулась
 * тем, что владелец случайно задел «Голосовое сообщение», пока проверял
 * прокрутку списка: кнопка пряталась там же, где на неё легко нажать
 * не глядя. В макете таких меню нет вовсе — только прямые кнопки.
 *
 * Это не отдельные наши кнопки, а те же самые действия движка: просто
 * `sequenceQuick` переводит их из «прочих» в «быстрые», и они встают в
 * один ряд с отправкой и эмодзи. Условие — только для нашего экрана
 * (`env.inCoopMessages`, выставлен ниже), обычный Discuss не трогаем.
 */
const QUICK_ON_THIS_SCREEN = { "upload-files": 25, "voice-start": 15, "voice-stop": 15 };
for (const [id, sequenceQuick] of Object.entries(QUICK_ON_THIS_SCREEN)) {
    const definition = composerActionsRegistry.get(id, null);
    if (!definition) {
        continue;
    }
    const original = definition.sequenceQuick;
    definition.sequenceQuick = function (params) {
        if (params.owner?.env?.inCoopMessages) {
            return sequenceQuick;
        }
        return typeof original === "function" ? original.call(this, params) : original;
    };
}

// Шаблонные ответы (`::сокращение`) в макете отсутствуют, а после того
// как вложение и голосовое стали прямыми кнопками, это единственное,
// что осталось бы в меню «+» — сама кнопка меню тогда не исчезла бы, а
// открывала бы список из одного пункта. Проще снять этот пункт здесь же
// и остаться совсем без меню, как в макете.
const cannedResponseDef = composerActionsRegistry.get("add-canned-response", null);
if (cannedResponseDef) {
    const originalCondition = cannedResponseDef.condition;
    cannedResponseDef.condition = function (params) {
        if (params.owner?.env?.inCoopMessages) {
            return false;
        }
        return typeof originalCondition === "function"
            ? originalCondition.call(this, params)
            : originalCondition;
    };
}

/**
 * Раздел «Сообщения» — переписки движка Discuss экраном из макета.
 *
 * Всё, что касается доставки сообщений, остаётся движку: лента и поле
 * ввода здесь — те же самые компоненты Discuss, что и на штатном экране.
 * Своё — только обрамление: список переписок с фильтрами по видам, поиск
 * и шапка со ссылкой на запись, о которой идёт разговор.
 *
 * Почему не правка штатного экрана. Discuss устроен вокруг разделов
 * («Каналы», «Личные сообщения») и складывает переписки по ним; в макете
 * список плоский, а вид переписки — фильтр над ним, и переключение фильтра
 * не должно перекладывать записи. Это разные способы смотреть на один
 * набор, и попытка выразить один через другой каждый раз ломает второй.
 */

// Наши поля канала приезжают вместе с ним, но модели переписки о них не
// сказано, и без объявления они не попадают под наблюдение — список
// перестаёт перерисовываться при смене вида.
patch(Thread.prototype, {
    setup() {
        super.setup();
        this.coop_kind = fields.Attr(false);
        this.coop_subtitle = fields.Attr("");
        this.coop_res_model = fields.Attr("");
        this.coop_res_id = fields.Attr(false);
        this.coop_link_label = fields.Attr("");
        this.coop_pinned = fields.Attr(false);
    },
});

// Порядок и подписи — из макета. «Непрочитанные» стоят вторыми и, как в
// прототипе, исчезают, когда непрочитанных нет: пустой фильтр с нулём
// рядом только занимает место.
const CATEGORIES = [
    { id: "all", label: "Все" },
    { id: "unread", label: "Непрочитанные" },
    { id: "person", label: "Личные" },
    { id: "deal", label: "Сделки" },
    { id: "org", label: "Организации" },
    { id: "project", label: "Проекты" },
    { id: "community", label: "Сообщества" },
    { id: "service", label: "Сервис" },
];

export class CoopMessages extends Component {
    static template = "coop_messages.Messages";
    static components = { Thread: ThreadComponent, Composer };
    static props = ["*"];

    setup() {
        this.store = useService("mail.store");
        this.action = useService("action");
        this.orm = useService("orm");
        this.categories = CATEGORIES;
        this.state = useState({
            category: "all",
            search: "",
            jump: 0,
            // Панель «Добавить диалог»: своё маленькое состояние — открыта
            // ли она, что набрано в поиске человека и кого уже нашли.
            newDialogOpen: false,
            newDialogQuery: "",
            newDialogResults: [],
        });
        // У ленты уже есть готовый вид переписки — цветные пузыри,
        // хвостик, свои сообщения справа. Он не самодельный, а встроен в
        // движок, только включается признаком `inChatWindow` — тем же,
        // что раньше давал приличный вид только в плавающем окошке чата
        // (которое мы как раз убрали). Здесь тот же признак — тот же вид,
        // но в своей панели, а не поверх экрана.
        // Свой признак экрана — только чтобы вложение и голосовое (см.
        // выше) стали прямыми кнопками именно здесь, не трогая обычный
        // Discuss.
        useSubEnv({ inChatWindow: true, inCoopMessages: true });
        this.newDialogRef = useRef("newDialog");
        // Клик мимо панели закрывает её — тот же приём, что у popover'ов
        // в макете (вложение, эмодзи): открытая панель поверх списка
        // переписок не должна требовать отдельной кнопки «закрыть».
        useExternalListener(window, "click", (ev) => {
            if (this.state.newDialogOpen && !this.newDialogRef.el?.contains(ev.target)) {
                this.state.newDialogOpen = false;
            }
        });
        onWillStart(async () => {
            await this.store.isReady;
            // Переписки движок присылает не при загрузке страницы, а по
            // запросу: их может быть много, и на большинстве экранов они
            // не нужны. Штатный Discuss просит их при открытии — просим и
            // мы, иначе список пуст при полной базе.
            await this.store.channels.fetch();
        });
    }

    /**
     * Все переписки, в которых человек состоит.
     *
     * Берутся из набора движка, а не перебором всех записей хранилища:
     * перебор возвращает верный список ровно один раз — в момент вызова.
     * Появление новой переписки такой список не замечает, и экран
     * остаётся пустым при полной базе, пока его не перерисует что-то
     * другое. Набор `allChannels` движок ведёт сам, и на него подписка
     * работает.
     */
    get threads() {
        return this.store.allChannels.filter((thread) => thread.displayToSelf);
    }

    /**
     * Закреплённые сверху, дальше по свежести разговора.
     *
     * Без второго ключа порядок «плавает»: у переписок, где сегодня никто
     * не писал, время последнего интереса совпадает с точностью до
     * секунды, и список при каждой перерисовке выходит другим.
     */
    get sortedThreads() {
        return this.threads.slice().sort((a, b) => {
            if (Boolean(a.coop_pinned) !== Boolean(b.coop_pinned)) {
                return a.coop_pinned ? -1 : 1;
            }
            const at = a.lastInterestDt?.ts ?? 0;
            const bt = b.lastInterestDt?.ts ?? 0;
            return bt - at || b.id - a.id;
        });
    }

    unreadOf(thread) {
        return thread.self_member_id?.message_unread_counter || 0;
    }

    inCategory(thread, category) {
        if (category === "all") {
            return true;
        }
        if (category === "unread") {
            return this.unreadOf(thread) > 0;
        }
        return thread.coop_kind === category;
    }

    matchesSearch(thread, query) {
        const needle = (query || "").trim().toLowerCase();
        if (!needle) {
            return true;
        }
        const haystack = [
            thread.displayName,
            thread.coop_subtitle,
            this.previewOf(thread),
        ];
        return haystack.some((part) => (part || "").toLowerCase().includes(needle));
    }

    countOf(category) {
        return this.threads.filter((thread) => this.inCategory(thread, category)).length;
    }

    /** Чипы: пустой фильтр «Непрочитанные» не показывается. */
    get shownCategories() {
        return this.categories.filter(
            (category) => category.id !== "unread" || this.countOf("unread") > 0
        );
    }

    get visibleThreads() {
        return this.sortedThreads.filter(
            (thread) =>
                this.inCategory(thread, this.state.category) &&
                this.matchesSearch(thread, this.state.search)
        );
    }

    previewOf(thread) {
        return thread.newestPersistentOfAllMessage?.previewText || "";
    }

    /**
     * Время последнего сообщения так, как его пишут в списке переписок:
     * сегодняшнее — часами, вчерашнее и старше — датой.
     */
    stampOf(thread) {
        const dt = thread.newestPersistentOfAllMessage?.datetime;
        if (!dt) {
            return "";
        }
        const now = DateTime.now();
        if (dt.hasSame(now, "day")) {
            return dt.toFormat("HH:mm");
        }
        if (dt.hasSame(now.minus({ days: 1 }), "day")) {
            return "вчера";
        }
        return dt.toFormat("dd.MM");
    }

    get activeThread() {
        const current = this.store.discuss.thread;
        if (current?.model === "discuss.channel" && current.displayToSelf) {
            return current;
        }
        return this.visibleThreads[0];
    }

    /** «В сети» / «был(а) недавно» под именем в личной переписке. */
    onlineStatus(thread) {
        return thread.correspondent?.im_status;
    }

    /**
     * Переключить открытую переписку — внутри своей же панели.
     *
     * `thread.open()` — на это и рассчитан: движок ищет активный экран
     * Discuss, чтобы переключить его, а нашего экрана он не узнаёт (это
     * не тот компонент) и откатывается на плавающее окошко чата поверх
     * интерфейса. У нас своя панель под это уже есть — просто ставим
     * переписку как открытую в хранилище, как это делает сам Discuss.
     */
    select(thread) {
        this.store.discuss.thread = thread;
        this.state.jump++;
    }

    /** Открыть/закрыть панель «Добавить диалог» и сбросить её состояние. */
    toggleNewDialog() {
        this.state.newDialogOpen = !this.state.newDialogOpen;
        this.state.newDialogQuery = "";
        this.state.newDialogResults = [];
    }

    /**
     * Поиск человека для нового диалога.
     *
     * По имени, без учёта регистра, только участники платформы — с
     * посторонним контактом Odoo (перевозчиком из адресной книги,
     * банком в реквизитах) переписки не заводят. Свою запись из выдачи
     * исключаем: с собой не переписываются.
     */
    async searchNewDialog(query) {
        this.state.newDialogQuery = query;
        const needle = query.trim();
        if (needle.length < 2) {
            this.state.newDialogResults = [];
            return;
        }
        const people = await this.orm.searchRead(
            "res.partner",
            [
                ["coop_is_participant", "=", true],
                ["is_company", "=", false],
                ["id", "!=", this.store.self.id],
                ["name", "ilike", needle],
            ],
            ["id", "name", "city"],
            { limit: 20 }
        );
        // Пока запрос летал, человек мог напечатать другое слово —
        // ответ на устаревший запрос тогда просто выбрасываем.
        if (this.state.newDialogQuery === query) {
            this.state.newDialogResults = people;
        }
    }

    /**
     * Начать переписку с выбранным человеком — своя или уже существующая.
     *
     * `store.startChat()` не подходит напрямую: она сама открывает
     * переписку через `thread.open()`, а это ровно тот путь, что уводит
     * в плавающее окошко поверх экрана (см. `select()` выше). Здесь та же
     * последовательность — найти или завести канал, — но открытие в
     * своей панели, через `select()`.
     */
    async startNewDialog(person) {
        const thread = await this.store.joinChat(person.id, false);
        this.toggleNewDialog();
        if (thread) {
            this.select(thread);
        }
    }

    /** Переход к записи, из которой выросла переписка. */
    openRecord(thread) {
        if (!thread.coop_res_model || !thread.coop_res_id) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: thread.coop_res_model,
            res_id: thread.coop_res_id,
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("coop_messages.messages", CoopMessages);
