/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useProps } from "@odoo/owl";

/**
 * Поле выбора, нарисованное вкладками страницы (дизайн-система, `Tabs`):
 * подписи в ряд, у выбранной — подчёркивание, под всем рядом — линия.
 *
 * Значение то же, что у строки состояний движка, и меняется так же, —
 * поэтому всё, что от него зависит (кнопки в шапке, видимость частей
 * формы), работает без правок. Первое применение — «Мой кошелёк»:
 * в эталоне `WalletPage` пять его частей стоят вкладками, а не
 * плашками-стрелками строки состояний.
 */
export class CoopTabsField extends Component {
    static template = "coop_theme.TabsField";
    props = useProps({ ...standardFieldProps });

    get items() {
        const field = this.props.record.fields[this.props.name];
        return (field.selection || []).map(([value, label]) => ({ value, label }));
    }

    get current() {
        return this.props.record.data[this.props.name];
    }

    async select(value) {
        if (value === this.current) {
            return;
        }
        await this.props.record.update({ [this.props.name]: value });
    }
}

export const coopTabsField = {
    component: CoopTabsField,
    displayName: "Вкладки страницы",
    supportedTypes: ["selection"],
};

registry.category("fields").add("coop_tabs", coopTabsField);
