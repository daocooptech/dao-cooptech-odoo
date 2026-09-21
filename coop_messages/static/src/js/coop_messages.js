/** @odoo-module **/

import { Component, onWillStart, useExternalListener, useRef, useState, useSubEnv } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

import { fields } from "@mail/core/common/record";
import { Thread as ThreadComponent } from "@mail/core/common/thread";
import { Composer } from "@mail/core/common/composer";
import { ActionList } from "@mail/core/common/action_list";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { threadActionsRegistry, useThreadActions } from "@mail/core/common/thread_actions";
import { Store } from "@mail/core/common/store_service";
import { MessagingMenu } from "@mail/core/public_web/messaging_menu";
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
        this.coop_managed = fields.Attr(false);
    },

    /**
     * У служебной переписки на экране её собственное название.
     *
     * Движок у переписки один на один показывает имя собеседника, а не
     * название канала. Для разговора двух людей это правильно, а у
     * служебных собеседник один на все шесть — помощник платформы, и в
     * списке выходило шесть одинаковых строк «Bot». При этом названия у
     * них в базе осмысленные: «Проверка объявлений», «Кошелёк и
     * платежи», «Споры по сделкам».
     */
    get displayName() {
        if (this.coop_kind === "service" && this.name) {
            return this.name;
        }
        return super.displayName;
    },

    /**
     * Переписка открывается в разделе платформы, а не окном движка.
     *
     * Движок на «открыть переписку» отвечает по-своему: либо окошком в
     * углу поверх страницы, либо собственным экраном Discuss. И то и
     * другое — второй интерфейс переписки рядом с нашим: человек нажимает
     * значок чатов в шапке, выбирает диалог и попадает не туда, где та же
     * переписка лежит в разделе.
     *
     * Поэтому все входы ведут в один раздел: значок в шапке,
     * уведомление, ссылка «написать» с чужой карточки. Если раздел уже
     * открыт — просто меняем выбранную переписку, без перехода: переход
     * поверх самого себя сбрасывает прокрутку ленты.
     */
    open(options) {
        if (this.model !== "discuss.channel") {
            return super.open(...arguments);
        }
        const actionService = this.store.env.services.action;
        this.setAsDiscussThread(false);
        const открытоСейчас = actionService.currentController?.action?.tag;
        if (открытоСейчас === "coop_messages.messages") {
            return true;
        }
        actionService.doAction("coop_messages.action_coop_messages",
                               { clearBreadcrumbs: true });
        return true;
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
    // Пайщики — отдельно от организаций: рабочая жизнь кооператива и
    // паевая это разные разговоры, и пайщик, не работающий в
    // кооперативе, в рабочем чате не состоит.
    { id: "shareholders", label: "Пайщики" },
    { id: "project", label: "Проекты" },
    { id: "community", label: "Сообщества" },
    { id: "service", label: "Сервис" },
];

// Что из действий движка стоит в шапке диалога наружу, а что уходит под
// многоточие. Разбор проектировщика от 16 сентября 2026: наружу три
// значка, четвёртый — многоточие; пятый всегда оказывается дублем пункта
// меню, а упирается здесь не ширина, а внимание.
//
// Поиск по сообщениям — самое частое действие внутри переписки. Звонок
// ищут глазами, а не в меню. Третий значок разный: в групповой переписке
// «кто здесь» спрашивают до первого сообщения, в личной участников нет.
const ЗНАЧКИ_НАРУЖУ_В_ГРУППЕ = ["search-messages", "call", "member-list"];
const ЗНАЧКИ_НАРУЖУ_В_ЛИЧНОЙ = ["search-messages", "call", "attachments"];

// Действия движка, которых на экране платформы быть не должно.
//
// «Открыть в полном Discuss» — ровно тот второй экран того же, ради
// которого раздел и переводили на наш. Остальные принадлежат окнам
// переписки поверх страницы, которых у платформы нет, или открывают
// форму настроек словами движка — нужное из неё вынесено отдельными
// пунктами.
const ДЕЙСТВИЯ_НЕ_ПОКАЗЫВАЕМ = new Set([
    "expand-discuss", "show-threads", "fold-chat-window", "close",
    "advanced-settings",
]);

// Выпадающий список у значка чатов в шапке: две вкладки, а не три.
//
// У движка переписки трёх видов: личная (один на один), группа
// (несколько человек, без названия, только по приглашению) и канал (с
// названием, в него можно вступить самому). Разница не в числе людей, а
// в том, есть ли имя и можно ли войти.
//
// Владелец 16 сентября 2026: «если каналы это обычные групповые чаты, то
// надо так и написать, а не плодить сущности». Для кооператора и группа,
// и канал — групповой разговор, и двух вкладок под это не нужно.
//
// Поэтому вкладок две: «Личные» — разговор один на один, «Групповые» —
// всё остальное. Деление делается там, где движок сопоставляет вкладку
// видам переписки: тогда и список, и счётчик, и поиск считают по нему
// сами.
patch(Store.prototype, {
    tabToThreadType(tab) {
        if (tab === "chat") {
            return ["chat"];
        }
        if (tab === "channel") {
            return ["channel", "group"];
        }
        return super.tabToThreadType(...arguments);
    },
});

// Служебные переписки — своей вкладкой.
//
// Решение владельца 16 сентября 2026: «служебные можно вынести в
// отдельную вкладку». Это переписки с самой платформой — помощник,
// извещения системы; человеческого разговора в них нет, а в общем
// списке они стоят наравне с живыми людьми и занимают верх, потому что
// пишут чаще всех.
//
// Вид переписки у нас свой (`coop_kind`), а движок отбирает вкладки по
// своему виду канала — сопоставлением их не связать. Поэтому список
// для этой вкладки собирается здесь, а из остальных вкладок служебные
// убираются.
const ВКЛАДКА_СЛУЖЕБНЫЕ = "coop_service";

patch(MessagingMenu.prototype, {
    get threads() {
        if (this.store.discuss.activeTab !== ВКЛАДКА_СЛУЖЕБНЫЕ) {
            return super.threads.filter((т) => т.coop_kind !== "service");
        }
        const свежесть = (т) => т.newestPersistentOfAllMessage?.datetime || 0;
        return Object.values(this.store.Thread.records)
            .filter((т) => т.coop_kind === "service" && т.displayToSelf)
            .sort((а, б) => (свежесть(б) > свежесть(а) ? 1 : -1));
    },
});

// Слова движка на экран не пускаем.
//
// Движок говорит «канал», «тред», «пользователь» — для кооператора это
// чужой язык: у него чат сообщества, переписка и люди. Подписи
// переопределяются у самих действий, а не переводом: перевод один на всю
// установку, а здесь нужен язык платформы в одном разделе.
const ПОДПИСИ_ДЕЙСТВИЙ = {
    "search-messages": "Поиск по переписке",
    "call": "Позвонить",
    "camera-call": "Видеозвонок",
    "member-list": "Участники",
    "attachments": "Вложения",
    "pinned-messages": "Закреплённые",
    "notification-settings": "Уведомления этой переписки",
    "invite-people": "Позвать людей",
    "mark-read": "Отметить прочитанной",
    "leave": "Выйти из переписки",
    "rename-thread": "Переименовать",
    "delete-thread": "Удалить переписку",
};

for (const [id, подпись] of Object.entries(ПОДПИСИ_ДЕЙСТВИЙ)) {
    const определение = threadActionsRegistry.get(id, null);
    if (определение) {
        определение.name = подпись;
    }
}

export class CoopMessages extends Component {
    static template = "coop_messages.Messages";
    static components = { Thread: ThreadComponent, Composer, ActionList, Dropdown };
    static props = ["*"];

    setup() {
        this.store = useService("mail.store");
        this.action = useService("action");
        this.orm = useService("orm");
        this.ui = useService("ui");
        this.categories = CATEGORIES;
        // Состояние заводится до действий треда, и порядок здесь важен.
        //
        // `useThreadActions` спрашивает открытую переписку сразу, при
        // сборке, а `activeThread` — когда в хранилище ещё нет открытой —
        // отвечает первой из видимых, то есть читает `state.category`.
        // Стоя ниже, состояние в этот момент ещё не существовало, и экран
        // падал с «Cannot read properties of undefined (reading
        // 'category')». Видно это было не всегда: если переписка в
        // хранилище уже открыта, `activeThread` возвращает её, не
        // заглядывая в состояние. Поэтому раздел «Сообщения» открывался
        // нормально, а «Написать» со страницы человека — нет: там
        // открытой переписки ещё нет.
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
        // Всё, что движок умеет с перепиской, приходит отсюда одним
        // списком: звонок, видео, участники, приглашение, вложения,
        // закреплённое, поиск по сообщениям, уведомления треда, «покинуть».
        //
        // Через реестр движка, а не своими кнопками: список действий
        // меняется от версии к версии и зависит от того, что за тред
        // открыт — личный диалог, канал или почтовый ящик. Свои кнопки
        // означали бы, что после обновления половина возможностей
        // пропала, и никто бы этого не заметил.
        this.threadActions = useThreadActions({ thread: () => this.activeThread });
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
            await this.openRequestedDialog();
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

    /** Групповая ли переписка: от этого зависит третий значок в шапке. */
    get isGroupThread() {
        const тип = this.activeThread?.channel_type;
        return тип === "channel" || тип === "group";
    }

    /** Значки, которые стоят в шапке наружу. */
    get quickActions() {
        const наружу = this.isGroupThread
            ? ЗНАЧКИ_НАРУЖУ_В_ГРУППЕ
            : ЗНАЧКИ_НАРУЖУ_В_ЛИЧНОЙ;
        return наружу
            .map((id) => this.threadActions.actions.find((a) => a.id === id))
            .filter(Boolean);
    }

    /** Всё остальное — под многоточием, в порядке движка. */
    get moreActions() {
        const наружу = new Set(this.quickActions.map((a) => a.id));
        // Из переписки, которую ведёт платформа, выйти нельзя: её состав
        // следует за записью, и вышедшего вернул бы первый же пересчёт.
        // Кнопку убираем, а не оставляем отвечать отказом: обещание,
        // которое отменяется само, хуже отсутствующего.
        const ведётПлатформа = this.activeThread?.coop_managed;
        return this.threadActions.actions.filter(
            (a) => !наружу.has(a.id)
                && !ДЕЙСТВИЯ_НЕ_ПОКАЗЫВАЕМ.has(a.id)
                && !(ведётПлатформа && a.id === "leave"));
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

    /**
     * Диалог, ради которого экран и открыли.
     *
     * Кнопка «Написать» на странице человека передаёт сюда его номер:
     * раздел «Сообщения» открывается сразу на переписке с ним, а не на
     * первой попавшейся. Заводить канал заранее нечем — `joinChat`
     * находит уже существующий или создаёт новый, и оба случая для
     * экрана выглядят одинаково.
     */
    async openRequestedDialog() {
        const кто = this.props.action?.params?.coop_partner_id;
        if (!кто) {
            return;
        }
        const thread = await this.store.joinChat(кто, false);
        if (thread) {
            this.select(thread);
        }
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
                // Тех, кто принимает письма только от друзей, в выдаче нет:
                // иначе запрет, о котором кнопка «Написать» честно
                // предупреждает, обходится этой панелью за два щелчка.
                ["coop_accepts_my_message", "=", true],
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
