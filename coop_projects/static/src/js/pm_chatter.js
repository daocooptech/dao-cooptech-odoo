/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Chatter } from "@mail/chatter/web_portal_project/chatter";
import { Composer } from "@mail/core/common/composer";
import { Thread } from "@mail/core/common/thread";
import { CoopIcon } from "@coop_theme/js/icons";

/**
 * Переписка «Управления проектом» — две вкладки, «Лента» и «Заметки»
 * (образец WorkHeaderD, задача 449 п. 5).
 *
 * У движка над перепиской три кнопки: «Отправить сообщение», «Внутренняя
 * заметка», «Активность», и все записи — одной лентой. В образце:
 * «Лента» — сообщения подписчикам и служебные записи, «Заметки» — только
 * внутренние записи команды; поле ввода открыто сверху в той вкладке, где
 * стоишь, под ним — кто увидит написанное. Поле заметки — на тёплом фоне,
 * чтобы не перепутать, куда пишешь. «Активность» снята: дела проекта
 * ведутся задачами.
 *
 * Только у проекта движка (`project.project`): у прочих записей переписка
 * остаётся штатной, стены (`coop_theme/wall.js`) — своими.
 */
const PM_MODEL = "project.project";

patch(Chatter, {
    components: { ...Chatter.components, CoopIcon },
});

patch(Chatter.prototype, {
    setup() {
        super.setup();
        if (this.coopPmTabs) {
            this.state.coopTab = "feed";
            this.state.composerType = "message";
        }
    },

    get coopPmTabs() {
        return this.threadModel() === PM_MODEL;
    },

    /** Поле — только тому, кто может писать; читать вкладки может каждый. */
    get coopPmCanPost() {
        const thread = this.state.thread;
        return Boolean(thread && (thread.canPostMessage || !thread.id));
    },

    coopSetTab(tab) {
        this.state.coopTab = tab;
        this.state.composerType = tab === "notes" ? "note" : "message";
    },

    coopTabCount(tab) {
        const messages = this.state.thread?.messages || [];
        return messages.filter((m) => !m.is_transient && coopPmInTab(m, tab)).length;
    },

    /**
     * Движок после отправки зовёт `toggleComposer()` без режима и тем
     * закрывает поле. Здесь поле открыто всегда — возвращаем тип вкладки.
     */
    onPostCallback() {
        super.onPostCallback();
        if (this.coopPmTabs) {
            this.state.composerType = this.state.coopTab === "notes" ? "note" : "message";
        }
    },

    toggleComposer(mode, options) {
        if (this.coopPmTabs && !mode) {
            return;
        }
        return super.toggleComposer(mode, options);
    },
});

/**
 * Заметка, написанная человеком, — во вкладке «Заметки», всё прочее — в
 * «Ленте». Служебные записи («Создано: проект», смена стадии) движок тоже
 * пишет подтипом заметки, но в образце они в «Ленте», рядом с сообщениями.
 */
function coopPmIsTeamNote(message) {
    return message.message_type === "comment" && message.isNote;
}

function coopPmInTab(message, tab) {
    return tab === "notes" ? coopPmIsTeamNote(message) : !coopPmIsTeamNote(message);
}

patch(Thread.prototype, {
    get orderedMessages() {
        const messages = super.orderedMessages;
        const tab = this.env.inChatter?.coopTab;
        if (!tab || this.props.thread?.model !== PM_MODEL) {
            return messages;
        }
        return messages.filter((m) => coopPmInTab(m, tab));
    },
});

patch(Composer, {
    components: { ...Composer.components, CoopIcon },
});

patch(Composer.prototype, {
    get coopPm() {
        return Boolean(this.env.inChatter?.coopTab
            && this.thread?.model === PM_MODEL && !this.props.composer.message);
    },

    get placeholder() {
        if (this.coopPm) {
            return this.props.type === "note"
                ? "Записать заметку для команды… @ — упомянуть"
                : "Написать в ленту проекта… @ — отметить";
        }
        return super.placeholder;
    },

    get SEND_TEXT() {
        if (this.coopPm) {
            return this.props.type === "note" ? "Записать" : "Отправить";
        }
        return super.SEND_TEXT;
    },

    /** Кто увидит написанное — под полем, как в образце. */
    get coopPmHint() {
        if (!this.coopPm) {
            return "";
        }
        if (this.props.type === "note") {
            return "видят только участники проекта";
        }
        // Пост остаётся в ленте, рассылки подписчикам нет (владелец 15.11,
        // `project_project._notify_get_recipients`): уведомление — только
        // отмеченным через @.
        return "уведомление получат только отмеченные через @";
    },
});
