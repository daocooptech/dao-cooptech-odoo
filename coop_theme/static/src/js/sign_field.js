/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, t, useProps } from "@odoo/owl";
import { CoopIcon } from "@coop_theme/js/icons";

/**
 * Значок записи без снимка — контур Tabler по значению поля (дизайн-система,
 * `Icon`: «значки — контуры Tabler, не эмодзи»).
 *
 * Прежде на месте пустого снимка стоял эмодзи из данных (`icon`) или
 * вписанный в шаблон: 🧾 ⚙️ 🛍 у расширений, 🛠 у задач «Помощи проекту».
 * Эмодзи рисует шрифт системы — у каждого телефона свой, цветной и не в
 * тон платформе. Поле остаётся тем же; меняется только то, чем оно
 * нарисовано.
 *
 * В виде: `<field name="category" widget="coop_sign"
 * options="{'map': {'sales': 'shopping-bag'}, 'icon': 'puzzle'}"/>` —
 * `map` сопоставляет значение поля имени значка, `icon` — значок, когда
 * сопоставления нет (или поля нет вовсе: тогда `map` не нужен).
 */
export class CoopSignField extends Component {
    static template = "coop_theme.SignField";
    static components = { CoopIcon };
    props = useProps({
        ...standardFieldProps,
        map: t.object().optional(),
        icon: t.string().optional(),
        size: t.number().optional(),
    });

    get iconName() {
        const value = this.props.record.data[this.props.name];
        return (this.props.map || {})[value] || this.props.icon || "puzzle";
    }
}

export const coopSignField = {
    component: CoopSignField,
    displayName: "Значок по значению",
    supportedTypes: ["selection", "char", "many2one", "boolean", "integer"],
    extractProps: ({ options }) => ({
        map: options.map,
        icon: options.icon,
        size: options.size,
    }),
};

registry.category("fields").add("coop_sign", coopSignField);
