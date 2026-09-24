/** @odoo-module **/

import { Component, reactive, useRef, useState } from "@odoo/owl";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { Message } from "@mail/core/common/message";
import { WALL_MODELS } from "@coop_theme/js/wall";

// Под записью на стене — ряд действий и комментарии.
//
// Владелец 24 сентября 2026 (решение 404): «сделать комментарии к
// постам на стене, оценку смайликом, иконку вознаграждение … и сделать
// репост или сохранить в избранное».
//
// Реакция смайликом и звёздочка «в избранное» у движка есть, но прячутся
// в меню, которое появляется только при наведении мыши, — на телефоне их
// не найти вовсе. Здесь они вынесены в ряд под записью, как в соцсетях,
// и вызывают то же самое, что меню движка. Комментарии — свои
// (`coop.wall.comment`, почему — в модели).

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
    static props = ["message", "thread", "owner"];
    static template = "coop_wall.WallPostFooter";

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

    onReact(ev) {
        this.props.owner.reactionPicker?.open({ el: ev.currentTarget });
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
