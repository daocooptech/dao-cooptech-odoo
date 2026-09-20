/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useEffect, useRef, useState } from "@odoo/owl";

/**
 * Поле, которое правится по месту: карандаш, галочка, крестик.
 *
 * То же, что в блоке «О себе», но без разметки полосы — годится для
 * любой строки карточки: город, почта, телефон, сайт, дата рождения,
 * языки. Владелец 16 сентября 2026: «каждое поле редактируется отдельно,
 * где то текст, где то выбор даты, где то выпадающий список».
 *
 * Правка держится черновиком и в запись не пишется до галочки: иначе
 * страница считается изменённой с первой буквы, уход с неё спрашивает
 * про несохранённое, а отмена обязана помнить прежнее значение.
 *
 * Тип ввода берётся у самого поля — строка, дата, число: одно и то же
 * поведение для всех, а разница только в том, чем набирают.
 */
export class CoopInlineField extends Component {
    static template = "coop_profile.InlineField";
    static props = {
        ...standardFieldProps,
        placeholder: { type: String, optional: true },
    };

    setup() {
        this.ui = useState({ editing: false, draft: "", busy: false });
        this.input = useRef("input");
        useEffect(
            (el) => {
                if (el) {
                    el.focus();
                    if (el.setSelectionRange && el.type === "text") {
                        el.setSelectionRange(el.value.length, el.value.length);
                    }
                }
            },
            () => [this.input.el]
        );
    }

    get field() {
        return this.props.record.fields[this.props.name];
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }

    /** Как показать значение, когда его не правят. */
    get display() {
        const value = this.value;
        if (!value) {
            return "";
        }
        if (this.field.type === "date") {
            return this.props.record.data[this.props.name].toFormat("dd.MM.yyyy");
        }
        return String(value);
    }

    /** Чем набирают: строка, дата, число. */
    get inputType() {
        const type = this.field.type;
        if (type === "date") {
            return "date";
        }
        if (type === "integer" || type === "float") {
            return "number";
        }
        return "text";
    }

    get canEdit() {
        return !this.props.readonly;
    }

    get maxlength() {
        return this.field.size || undefined;
    }

    start() {
        const value = this.value;
        this.ui.draft = this.field.type === "date" && value
            ? value.toFormat("yyyy-MM-dd")
            : (value || "");
        this.ui.editing = true;
    }

    async accept() {
        if (this.ui.busy) {
            return;
        }
        this.ui.busy = true;
        try {
            await this.props.record.update({ [this.props.name]: this.parse(this.ui.draft) });
            const saved = await this.props.record.save();
            if (saved !== false) {
                this.ui.editing = false;
            }
        } finally {
            this.ui.busy = false;
        }
    }

    parse(draft) {
        if (!draft) {
            return false;
        }
        if (this.field.type === "integer") {
            return parseInt(draft, 10) || 0;
        }
        if (this.field.type === "float") {
            return parseFloat(draft) || 0;
        }
        return draft;
    }

    cancel() {
        this.ui.editing = false;
    }

    onInput(event) {
        this.ui.draft = event.target.value;
    }

    onKeydown(event) {
        if (event.key === "Enter") {
            event.preventDefault();
            this.accept();
        } else if (event.key === "Escape") {
            event.preventDefault();
            this.cancel();
        }
    }
}

export const coopInlineField = {
    component: CoopInlineField,
    displayName: "Правка по месту",
    supportedTypes: ["char", "date", "integer", "float"],
    extractProps: ({ attrs }) => ({ placeholder: attrs.placeholder }),
};

registry.category("fields").add("coop_inline", coopInlineField);
