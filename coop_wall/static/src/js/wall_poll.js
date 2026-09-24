/** @odoo-module **/

import { Component, toRaw, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { DateTimeInput } from "@web/core/datetime/datetime_input";
import { deserializeDateTime, serializeDateTime } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";
import { markEventHandled } from "@web/core/utils/misc";
import { registerComposerAction } from "@mail/core/common/composer_actions";
import { WALL_MODELS } from "@coop_theme/js/wall";

// Опросы и отложенная публикация на стене (решения 404, 410).
//
// Опрос — вид записи: вопрос и от двух до десяти вариантов. Голос один и
// без отзыва; итог видит проголосовавший, автор и все после окончания.
// Сервер — `models/coop_wall_poll.py`: он же решает, что отдать в
// браузер, — числа тому, кто ещё не голосовал, не уходят вовсе.
//
// Отложенная запись — отложенное сообщение движка: список
// «Запланировано» с «Отправить сейчас / Изменить / Отменить» над лентой
// движок рисует сам; видит его только автор (правило в
// `security/coop_wall_rules.xml`).

const MAX_OPTIONS = 10;

const onWall = ({ composer }) => WALL_MODELS.includes(composer?.targetThread?.model);

/** Карточка опроса в записи. */
export class CoopWallPoll extends Component {
    static props = ["message"];
    static template = "coop_wall.Poll";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ busy: false, voters: null });
    }

    get poll() {
        return this.props.message.coop_poll;
    }

    get deadline() {
        if (!this.poll.close_at) {
            return "";
        }
        const at = deserializeDateTime(this.poll.close_at);
        return (this.poll.closed ? "Завершён " : "До ") + at.toFormat("d MMM, HH:mm");
    }

    get totalLabel() {
        const n = this.poll.total;
        const mod10 = n % 10;
        const mod100 = n % 100;
        let word = "голосов";
        if (mod10 === 1 && mod100 !== 11) {
            word = "голос";
        } else if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) {
            word = "голоса";
        }
        return `${n} ${word}`;
    }

    async vote(option) {
        if (!this.poll.can_vote || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            this.props.message.coop_poll = await this.orm.call(
                "coop.wall.poll", "coop_vote", [this.poll.id, option.id]);
        } catch (error) {
            this.notification.add(error.data?.message || "Голос не записан", { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    async close() {
        this.props.message.coop_poll = await this.orm.call(
            "coop.wall.poll", "coop_close", [this.poll.id]);
    }

    toggleVoters(option) {
        this.state.voters = this.state.voters === option.id ? null : option.id;
    }
}

/** Окно «Опрос». */
export class CoopPollDialog extends Component {
    static components = { Dialog, DateTimeInput };
    static props = ["thread", "close"];
    static template = "coop_wall.PollDialog";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            question: "",
            options: ["", ""],
            isPublic: false,
            closeAt: false,
            scheduledAt: false,
            busy: false,
        });
        this.now = luxon.DateTime.local();
    }

    get canAdd() {
        return this.state.options.length < MAX_OPTIONS;
    }

    addOption() {
        if (this.canAdd) {
            this.state.options.push("");
        }
    }

    removeOption(index) {
        if (this.state.options.length > 2) {
            this.state.options.splice(index, 1);
        }
    }

    setOption(index, ev) {
        this.state.options[index] = ev.target.value;
    }

    async publish() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        const thread = toRaw(this.props.thread);
        try {
            const result = await this.orm.call("coop.wall.poll", "coop_create", [
                thread.model,
                thread.id,
                this.state.question,
                this.state.options,
                this.state.isPublic,
                this.state.closeAt ? serializeDateTime(this.state.closeAt) : false,
                this.state.scheduledAt ? serializeDateTime(this.state.scheduledAt) : false,
            ]);
            if (result.scheduled) {
                await thread.fetchThreadData(["scheduledMessages"]);
                this.notification.add("Опрос запланирован", { type: "success" });
            } else {
                await thread.fetchNewMessages();
            }
            this.props.close();
        } catch (error) {
            this.notification.add(error.data?.message || "Опрос не опубликован", { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }
}

/** Окно «Отложить»: когда выйдет запись, набранная в поле. */
export class CoopScheduleDialog extends Component {
    static components = { Dialog, DateTimeInput };
    static props = ["composer", "owner", "close"];
    static template = "coop_wall.ScheduleDialog";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        // По умолчанию — завтра в девять утра: время, когда ленту читают.
        this.state = useState({
            at: luxon.DateTime.local().plus({ days: 1 }).set({ hour: 9, minute: 0, second: 0 }),
            busy: false,
        });
        this.now = luxon.DateTime.local();
    }

    async schedule() {
        if (this.state.busy || !this.state.at) {
            return;
        }
        this.state.busy = true;
        const composer = toRaw(this.props.composer);
        const thread = composer.targetThread;
        try {
            await this.orm.call("mail.scheduled.message", "coop_schedule", [
                thread.model,
                thread.id,
                String(composer.composerHtml || ""),
                composer.attachments.map((a) => a.id),
                serializeDateTime(this.state.at),
            ]);
            // Черновик уходит из поля, а его файлы — нет: они переехали к
            // отложенной записи на сервере (`coop_schedule`).
            this.props.owner.clear();
            await thread.fetchThreadData(["scheduledMessages"]);
            this.notification.add(
                `Запись выйдет ${this.state.at.toFormat("d MMM, HH:mm")}`, { type: "success" });
            this.props.close();
        } catch (error) {
            this.notification.add(error.data?.message || "Не удалось отложить", { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }
}

registerComposerAction("coop-wall-poll", {
    condition: (p) => onWall(p) && !p.composer.message,
    icon: "fa fa-bar-chart",
    name: "Опрос",
    onSelected: ({ composer, owner }, ev) => {
        markEventHandled(ev, "composer.clickOnAddAttachment");
        owner.env.services.dialog.add(CoopPollDialog, { thread: composer.targetThread });
    },
    sequence: 16,
});

// Часы у «Опубликовать» (решение 410): отложить то, что набрано в поле.
registerComposerAction("coop-wall-schedule", {
    condition: (p) => onWall(p) && !p.composer.message,
    icon: "fa fa-clock-o",
    name: "Отложить",
    onSelected: ({ composer, owner }, ev) => {
        markEventHandled(ev, "composer.clickOnAddAttachment");
        const empty = !String(composer.composerHtml || "").replace(/<[^>]*>/g, "").trim()
            && !composer.attachments.length;
        if (empty) {
            owner.env.services.notification.add(
                "Сначала напишите запись — потом выберите, когда ей выйти", { type: "info" });
            return;
        }
        owner.env.services.dialog.add(CoopScheduleDialog, { composer, owner });
    },
    sequence: 17,
});
