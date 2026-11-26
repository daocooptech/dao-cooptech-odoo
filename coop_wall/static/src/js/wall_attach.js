/** @odoo-module **/

import { Component, proxy, toRaw, usePlugin, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { NotificationPlugin } from "@web/core/notifications/notification_plugin";
import { useService } from "@web/core/utils/hooks";
import { markEventHandled } from "@web/core/utils/misc";
import { patch } from "@web/core/utils/patch";
import { Composer } from "@mail/core/common/composer";
import { registerComposerAction } from "@mail/core/common/composer_actions";
import { Message } from "@mail/core/common/message";
import { Message as MessageModel } from "@mail/core/common/message_model";
import { fields } from "@mail/model/export";
import { WALL_MODELS } from "@coop_theme/js/wall";

// Запись из каталогов, прикреплённая к посту стены (№ 454). Образец —
// холст ленты, доска «№ 454 · Прикрепить запись из каталогов». Что
// уместно на стене и что видно человеку, решает сервер
// (`models/wall_attach.py`).

const onWall = ({ composer }) => WALL_MODELS.includes(composer?.targetThread?.model);

/** Карточка записи — `LinkCard` дизайн-системы (`.coop-link`). */
export class CoopRecCard extends Component {
    props = useProps(["rec"]);
    static template = "coop_wall.RecCard";
}

/** Окно «Прикрепить запись». */
export class CoopAttachDialog extends Component {
    static components = { Dialog, CoopRecCard };
    props = useProps(["thread", "onPick", "close"]);
    static template = "coop_wall.AttachDialog";

    setup() {
        this.orm = useService("orm");
        this.notification = usePlugin(NotificationPlugin);
        this.state = proxy({ kinds: [], kind: "all", query: "", found: [], busy: true });
        this.timer = null;
        this.load();
    }

    get thread() {
        return this.props.thread;
    }

    async load() {
        const kinds = await this.orm.call(
            "mail.message", "coop_attach_kinds", [this.thread.model, this.thread.id]);
        this.state.kinds = [{ id: "all", label: "Все" }, ...kinds];
        await this.search();
    }

    async search() {
        this.state.busy = true;
        try {
            this.state.found = await this.orm.call("mail.message", "coop_attach_search", [
                this.thread.model, this.thread.id, this.state.kind, this.state.query.trim(),
            ]);
        } finally {
            this.state.busy = false;
        }
    }

    pickKind(kind) {
        this.state.kind = kind.id;
        this.search();
    }

    onQuery(ev) {
        this.state.query = ev.target.value;
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.search(), 300);
    }

    choose(rec) {
        this.props.onPick(rec);
        this.props.close();
    }
}

registerComposerAction("coop-wall-record", {
    condition: (p) => onWall(p) && !p.composer.message,
    icon: "link",
    name: "Прикрепить запись",
    onSelected: ({ composer, owner }, ev) => {
        markEventHandled(ev, "composer.clickOnAddAttachment");
        owner.env.services.dialog.add(CoopAttachDialog, {
            thread: composer.targetThread,
            onPick: (rec) => {
                owner.coopRec.card = rec;
                toRaw(composer).autofocus++;
            },
        });
    },
    sequence: 18,
});

patch(Composer, {
    components: { ...Composer.components, CoopRecCard },
});

patch(Composer.prototype, {
    setup() {
        super.setup(...arguments);
        this.coopRec = proxy({ card: null });
    },

    coopUnpick() {
        this.coopRec.card = null;
    },

    async _sendMessage(value, postData, extraData) {
        const card = this.coopRec?.card;
        const message = await super._sendMessage(value, postData, extraData);
        if (card && message && WALL_MODELS.includes(this.thread?.model)) {
            this.coopRec.card = null;
            try {
                message.coop_rec = await this.env.services.orm.call(
                    "mail.message", "coop_attach_set", [message.id, card.model, card.id]);
            } catch (error) {
                this.env.services.notification.add(
                    error.data?.message || "Запись не прикрепилась", { type: "danger" });
            }
        }
        return message;
    },
});

patch(Message, {
    components: { ...Message.components, CoopRecCard },
});

patch(MessageModel.prototype, {
    setup() {
        super.setup(...arguments);
        this.coop_rec = fields.Attr(false);
    },
});
