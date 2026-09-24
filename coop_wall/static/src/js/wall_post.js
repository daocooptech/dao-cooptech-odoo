/** @odoo-module **/

import { Component, markup, reactive, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { Message } from "@mail/core/common/message";
import { Message as MessageModel } from "@mail/core/common/message_model";
import { fields } from "@mail/core/common/record";
import { MessageReactions } from "@mail/core/common/message_reactions";
import { WALL_MODELS } from "@coop_theme/js/wall";

// Под записью на стене — ряд действий и комментарии.
//
// Владелец 24 сентября 2026 (решение 404): «сделать комментарии к
// постам на стене, оценку смайликом … и сделать репост или сохранить в
// избранное». Следом, о виде ряда: «надпись оценить надо убрать, вместо
// неё цифрами количество лайков, иконка лайка, иконка дизлайка,
// количество дизлайков, иконка комментария, слово комментировать
// удалить, количество комментариев цифрой, иконка избранного, слово в
// избранное удалить».
//
// Ряд — только значки и числа: 👍 N, 👎 N, 💬 N, ↪ N, 🎁 N, ☆. Репост —
// стрелкой «поделиться», как во ВКонтакте: кольцевые стрелки владелец
// не узнал («не вижу иконку репоста»). Лайк и дизлайк —
// реакции движка 👍 и 👎 (`mail.message.reaction`): хранятся, считаются и
// приходят в браузер тем же путём, что прочие реакции, и из общего
// списка реакций под записью стены убраны, чтобы не стоять дважды.
// Звёздочка — избранное движка. Комментарии — свои (`coop.wall.comment`,
// почему — в модели).

export const LIKE = "👍";
export const DISLIKE = "👎";

/**
 * Комментарии всех записей экрана — одним запросом.
 *
 * Записи рисуются по одной, и каждая просит свои комментарии; просьбы,
 * пришедшие в одном такте, собираются в один вызов сервера.
 */
export const coopWallCommentsService = {
    dependencies: ["orm"],
    start(env, { orm }) {
        const byPost = reactive({});
        let pending = new Set();
        let scheduled = null;

        function flush() {
            const ids = [...pending];
            pending = new Set();
            scheduled = null;
            orm.call("coop.wall.comment", "coop_for_posts", [ids]).then(
                (result) => {
                    for (const id of ids) {
                        byPost[id] = result[id] || [];
                    }
                },
                () => {
                    // Комментарии не имеют права ронять стену: не
                    // загрузились — значит под записью их нет.
                    for (const id of ids) {
                        byPost[id] = [];
                    }
                }
            );
        }

        return {
            byPost,
            load(postId) {
                if (postId in byPost || pending.has(postId) || postId <= 0) {
                    return;
                }
                pending.add(postId);
                scheduled ??= Promise.resolve().then(flush);
            },
            async add(postId, body) {
                const comment = await orm.call("coop.wall.comment", "coop_add", [postId, body]);
                byPost[postId] = [...(byPost[postId] || []), comment];
            },
            async remove(postId, commentId) {
                await orm.call("coop.wall.comment", "coop_remove", [commentId]);
                byPost[postId] = (byPost[postId] || []).filter((c) => c.id !== commentId);
            },
        };
    },
};
registry.category("services").add("coop_wall_comments", coopWallCommentsService);

// Сколько комментариев видно сразу. Остальные — по «Показать все».
const SHOWN = 2;

export class CoopWallPostFooter extends Component {
    static props = ["message", "thread"];
    static template = "coop_wall.WallPostFooter";

    LIKE = LIKE;
    DISLIKE = DISLIKE;

    setup() {
        this.comments = useService("coop_wall_comments");
        this.byPost = useState(this.comments.byPost);
        this.state = useState({ expanded: false, writing: false, draft: "", busy: false });
        this.inputRef = useRef("input");
        this.comments.load(this.props.message.id);
    }

    get list() {
        return this.byPost[this.props.message.id] || [];
    }

    get shown() {
        const list = this.list;
        return this.state.expanded ? list : list.slice(-SHOWN);
    }

    get hidden() {
        return this.state.expanded ? 0 : Math.max(0, this.list.length - SHOWN);
    }

    get canReact() {
        return this.props.message.canAddReaction(this.props.thread);
    }

    reaction(content) {
        return this.props.message.reactions.find((r) => r.content === content);
    }

    count(content) {
        return this.reaction(content)?.count || 0;
    }

    mine(content) {
        const reaction = this.reaction(content);
        return Boolean(reaction && this.props.message.effectiveSelf.in(reaction.personas));
    }

    /**
     * Лайк и дизлайк взаимно исключают друг друга: поставил один — второй,
     * если был, снимается. Повторное нажатие снимает свой.
     */
    async toggle(content) {
        if (!this.canReact) {
            return;
        }
        if (this.mine(content)) {
            await this.reaction(content).remove();
            return;
        }
        const other = content === LIKE ? DISLIKE : LIKE;
        if (this.mine(other)) {
            await this.reaction(other).remove();
        }
        await this.props.message.react(content);
    }

    get canStar() {
        return this.props.message.canToggleStar;
    }

    get showInput() {
        return this.state.writing || this.list.length > 0;
    }

    avatarUrl(comment) {
        return `/web/image/res.partner/${comment.author_id}/avatar_128`;
    }

    formatDate(comment) {
        return deserializeDateTime(comment.date).toFormat("d MMM, HH:mm");
    }

    onComment() {
        this.state.writing = true;
        // Поле рисуется в этом же такте; фокус — после отрисовки.
        setTimeout(() => this.inputRef.el?.focus());
    }

    get reposts() {
        return this.props.message.coop_repost_count || 0;
    }

    onRepost() {
        this.env.services.dialog.add(CoopRepostDialog, {
            message: this.props.message,
            thread: this.props.thread,
        });
    }

    get thanks() {
        return this.props.message.coop_thanks_count || 0;
    }

    onThanks() {
        this.env.services.dialog.add(CoopThanksDialog, { message: this.props.message });
    }

    onStar() {
        this.props.message.toggleStar();
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    async send() {
        const body = this.state.draft.trim();
        if (!body || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await this.comments.add(this.props.message.id, body);
            this.state.draft = "";
            this.state.expanded = true;
        } finally {
            this.state.busy = false;
        }
    }

    remove(comment) {
        this.comments.remove(this.props.message.id, comment.id);
    }
}

/**
 * Окно «Поделиться у себя на странице»: пара своих слов (можно без них) и
 * исходная запись для памяти, о чём речь.
 */
export class CoopRepostDialog extends Component {
    static components = { Dialog };
    static props = ["message", "thread", "close"];
    static template = "coop_wall.RepostDialog";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ comment: "", busy: false });
    }

    get preview() {
        const m = this.props.message;
        const html = m.body ? String(m.body) : "";
        const text = new DOMParser().parseFromString(html, "text/html").body.textContent.trim();
        return {
            author: m.author_id?.name || "",
            text: text.length > 200 ? text.slice(0, 200) + "…" : text,
        };
    }

    async share() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call("mail.message", "coop_repost", [this.props.message.id, this.state.comment]);
            const m = this.props.message;
            m.coop_repost_count = (m.coop_repost_count || 0) + 1;
            this.notification.add("Запись появилась на вашей странице.", { type: "success" });
            const me = m.store.self_partner || m.store.self;
            const thread = this.props.thread;
            if (thread?.model === "res.partner" && me && thread.id === me.id) {
                thread.fetchNewMessages?.();
            }
            this.props.close();
        } finally {
            this.state.busy = false;
        }
    }
}

/**
 * «Поблагодарить» (решение 406). Платформа денег не касается: рубли даритель
 * переводит в своём банке по СБП автора, токены — на адрес автора в
 * выбранной сети; здесь он
 * только отмечает, что перевод сделан, а автор — пришли ли деньги.
 *
 * Автор своей записи видит в этом же окне, кто и сколько прислал, и
 * отмечает каждую благодарность.
 */
export class CoopThanksDialog extends Component {
    static components = { Dialog };
    static props = ["message", "close"];
    static template = "coop_wall.ThanksDialog";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            info: null, channel: "sbp", amount: "", understood: false, busy: false,
            networkId: null, token: null,
        });
        this.load();
    }

    async load() {
        const info = await this.orm.call("coop.wall.thanks", "coop_info", [this.props.message.id]);
        this.state.info = info;
        this.state.channel = info.sbp ? "sbp" : "token";
        const first = info.networks?.[0];
        this.state.networkId = first?.id || null;
        this.state.token = first?.tokens[0]?.symbol || null;
    }

    get network() {
        return (this.state.info?.networks || []).find((n) => n.id === this.state.networkId);
    }

    onNetwork(ev) {
        this.state.networkId = parseInt(ev.target.value);
        this.state.token = this.network?.tokens[0]?.symbol || null;
    }

    get canSend() {
        const amount = parseFloat(String(this.state.amount).replace(",", "."));
        return this.state.understood && amount > 0 && !this.state.busy;
    }

    async declare() {
        if (!this.canSend) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call("coop.wall.thanks", "coop_declare", [
                this.props.message.id,
                this.state.channel,
                parseFloat(String(this.state.amount).replace(",", ".")),
                this.state.understood,
                this.state.channel === "token" ? this.state.networkId : false,
                this.state.channel === "token" ? this.state.token : false,
            ]);
            this.notification.add(
                "Спасибо! Автор увидит подарок у себя и отметит, когда он придёт.",
                { type: "success" }
            );
            this.props.close();
        } finally {
            this.state.busy = false;
        }
    }

    async mark(item, state) {
        const updated = await this.orm.call("coop.wall.thanks", "coop_set_state", [item.id, state]);
        Object.assign(item, updated);
        const confirmed = new Set(
            this.state.info.received.filter((t) => t.state === "confirmed").map((t) => t.sender_id)
        );
        this.props.message.coop_thanks_count = confirmed.size;
    }

    formatDate(item) {
        return deserializeDateTime(item.date).toFormat("d MMM, HH:mm");
    }

    formatAmount(item) {
        const n = item.channel === "token" ? item.amount : Math.round(item.amount);
        const where = item.channel === "token" && item.network ? ` · ${item.network}` : "";
        return `${n.toLocaleString("ru-RU")} ${item.currency}${where}`;
    }
}


export class CoopRepostCard extends Component {
    static props = ["repost"];
    static template = "coop_wall.RepostCard";

    get body() {
        return markup(this.props.repost.body || "");
    }

    get date() {
        return deserializeDateTime(this.props.repost.date).toFormat("d MMM yyyy, HH:mm");
    }

    get avatarUrl() {
        return `/web/image/res.partner/${this.props.repost.author_id}/avatar_128`;
    }
}

patch(Message, {
    components: { ...Message.components, CoopWallPostFooter, CoopRepostCard },
});

patch(Message.prototype, {
    // Запись стены, а не служебное сообщение и не заметка: ряд действий
    // только под тем, что люди написали сами (ср. `orderedMessages` в
    // `coop_theme/static/src/js/wall.js`).
    get coopIsWallPost() {
        return (
            Boolean(this.env.inChatter) &&
            WALL_MODELS.includes(this.props.thread?.model) &&
            this.message.message_type === "comment" &&
            !this.message.isNote &&
            this.message.id > 0
        );
    },
});

// Лайк и дизлайк на стене стоят в ряду под записью со своими числами —
// в общем списке реакций движка они были бы вторым разом.
patch(MessageReactions.prototype, {
    get coopReactions() {
        const reactions = this.props.message.reactions;
        const thread = this.props.message.thread;
        if (!this.env.inChatter || !WALL_MODELS.includes(thread?.model)) {
            return reactions;
        }
        return reactions.filter((r) => r.content !== LIKE && r.content !== DISLIKE);
    },
});

// Репост и благодарности: карточка исходника и числа приходят с сервера
// (`models/mail_message.py`, `_to_store_defaults`).
patch(MessageModel.prototype, {
    setup() {
        super.setup(...arguments);
        this.coop_repost = fields.Attr(false);
        this.coop_repost_count = fields.Attr(0);
        this.coop_thanks_count = fields.Attr(0);
    },

    // Репост без своих слов — не пустая запись: в нём карточка. Иначе
    // движок показал бы на его месте «сообщение удалено».
    computeIsEmpty() {
        return !this.coop_repost && super.computeIsEmpty();
    },
});
