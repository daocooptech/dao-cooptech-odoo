/** @odoo-module **/

import { Component, reactive, useRef, useState } from "@odoo/owl";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { Message } from "@mail/core/common/message";
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
// Ряд — только значки и числа: 👍 N, 👎 N, 💬 N, ☆. Лайк и дизлайк —
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

patch(Message, {
    components: { ...Message.components, CoopWallPostFooter },
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
