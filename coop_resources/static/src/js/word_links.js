/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, t, useProps } from "@odoo/owl";
import { CoopIcon } from "@coop_theme/js/icons";

/**
 * Сырьё и оборудование словами на витрине ресурса.
 *
 * Решение владельца 26.10.2026, эталон `ResourcePage`: слово — не ссылка
 * на чужое объявление, а поиск. Нажатие открывает «Каталог ресурсов» со
 * словом в поиске и городом смотрящего в отборе — там видно, где взять
 * сейчас. Подсказка заранее говорит, что будет.
 *
 * Ставится на `material_word_ids` / `equipment_word_ids`; значок — в
 * `options.icon`.
 */
export class CoopWordLinks extends Component {
    static template = "coop_resources.WordLinks";
    static components = { CoopIcon };
    props = useProps({ ...standardFieldProps, icon: t.string().optional() });

    setup() {
        this.action = useService("action");
    }

    get words() {
        return this.props.record.data[this.props.name].records;
    }

    get icon() {
        return this.props.icon || "package";
    }

    tip(word) {
        const city = this.props.record.data.coop_viewer_city;
        return `Найти «${word.data.display_name}» в каталоге ресурсов` + (city ? ` · ${city}` : "");
    }

    find(word) {
        return this.action.doActionButton({
            type: "object",
            name: "action_find_word",
            resModel: "coop.resource",
            resId: this.props.record.resId,
            args: JSON.stringify([word.resId]),
        });
    }
}

registry.category("fields").add("coop_word_links", {
    component: CoopWordLinks,
    supportedTypes: ["many2many"],
    fieldDependencies: [{ name: "coop_viewer_city", type: "char" }],
    relatedFields: [{ name: "display_name", type: "char" }],
    extractProps: ({ options }) => ({ icon: options.icon }),
});
