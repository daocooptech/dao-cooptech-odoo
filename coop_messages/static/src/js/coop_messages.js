/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { DateTime } from "luxon";
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

import { fields } from "@mail/core/common/record";
import { Thread as ThreadComponent } from "@mail/core/common/thread";
import { Composer } from "@mail/core/common/composer";
import { Thread } from "@mail/core/common/thread_model";

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
        this.categories = CATEGORIES;
        this.state = useState({ category: "all", search: "", jump: 0 });
        onWillStart(() => this.store.isReady);
    }

    /** Все переписки, в которых человек состоит. */
    get threads() {
        return Object.values(this.store.Thread.records).filter(
            (thread) => thread.model === "discuss.channel" && thread.displayToSelf
        );
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

    select(thread) {
        thread.open();
        this.state.jump++;
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
