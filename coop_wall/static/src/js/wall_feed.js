/** @odoo-module **/

import { Component, onWillStart, useState, useSubEnv } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { AttachmentList } from "@mail/core/common/attachment_list";
import { CoopWallPostFooter, CoopRepostCard } from "@coop_wall/js/wall_post";
import { CoopWallPoll } from "@coop_wall/js/wall_poll";

// Лента подписок — как стена (решение 410, п. 3): под текстом записи
// карточка репоста, опрос, вложения и ряд 👍 👎 💬 ↪ 🎁 ☆. Компоненты те
// же, что на стене; запись для них — из хранилища переписки движка
// (`mail.message.coop_feed_store`).

/**
 * Записи ленты — в хранилище одним запросом на экран: карточки рисуются по
 * одной, и просьбы одного такта собираются в один вызов сервера.
 */
export const coopWallFeedService = {
    dependencies: ["orm", "mail.store"],
    start(env, { orm, "mail.store": store }) {
        const loaded = new Map();
        let pending = [];
        let flushing = null;

        function flush() {
            const batch = pending;
            pending = [];
            flushing = null;
            const ids = batch.map((b) => b.id);
            orm.call("mail.message", "coop_feed_store", [ids]).then(
                (data) => {
                    store.insert(data);
                    batch.forEach((b) => b.resolve());
                },
                () => batch.forEach((b) => b.resolve())
            );
        }

        return {
            load(id) {
                if (!loaded.has(id)) {
                    loaded.set(id, new Promise((resolve) => {
                        pending.push({ id, resolve });
                        flushing ??= Promise.resolve().then(flush);
                    }));
                }
                return loaded.get(id);
            },
        };
    },
};
registry.category("services").add("coop_wall_feed", coopWallFeedService);

export class CoopWallFeedExtras extends Component {
    static template = "coop_wall.FeedExtras";
    static props = { ...standardFieldProps };
    static components = { AttachmentList, CoopWallPostFooter, CoopRepostCard, CoopWallPoll };

    setup() {
        this.store = useService("mail.store");
        this.feed = useService("coop_wall_feed");
        this.state = useState({ ready: false });
        // Видео в записи — проигрывателем, как на стене: шаблон вложений
        // стены смотрит на признак ленты записи (`coop_theme`, chatter.xml).
        useSubEnv({ inChatter: { aside: false } });
        onWillStart(async () => {
            await this.feed.load(this.props.record.resId);
            this.state.ready = true;
        });
    }

    get message() {
        return this.store["mail.message"].get(this.props.record.resId);
    }

    get attachments() {
        return this.message?.extra_body_attachment_ids || [];
    }

    // Удалять вложение из ленты подписок нельзя — это чужая запись.
    noUnlink() {}
}

registry.category("fields").add("coop_wall_feed_extras", {
    component: CoopWallFeedExtras,
    supportedTypes: ["integer"],
});
