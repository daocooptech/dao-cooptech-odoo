/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField, charField, charFieldProps } from "@web/views/fields/char/char_field";
import { useInputField } from "@web/views/fields/input_field_hook";
import { signal, t, useProps } from "@odoo/owl";

/**
 * Название на страницах добавления: заготовка черновика — не значение (№ 472).
 *
 * Черновик заводится сразу, с именем «Новое объявление», «Новый навык»:
 * поле обязательное. Стоя значением, заготовка дописывалась к тому, что
 * печатает человек. Здесь она показана пустым полем с подсказкой, а в
 * записи остаётся до первого введённого названия.
 */
export class CoopDraftName extends CharField {
    static template = "web.CharField";
    props = useProps({ ...charFieldProps, draft: t.string().optional() });
    input = signal.ref();

    setup() {
        useInputField({
            ref: this.input,
            getValue: () => this.shown,
            parse: (v) => this.parse(v),
        });
        this.selectionStart = this.shown.length;
    }

    /** Заготовок может быть несколько: «Новый навык|Новая услуга». */
    get drafts() {
        return (this.props.draft || "").split("|");
    }

    get shown() {
        const value = this.props.record.data[this.props.name] || "";
        return this.drafts.includes(value.trim()) ? "" : value;
    }

    get formattedValue() {
        return this.shown;
    }

    /** Стёрли всё — снова заготовка: без имени черновик не сохранить. */
    parse(value) {
        return super.parse(value) || this.drafts[0];
    }
}

registry.category("fields").add("coop_draft_name", {
    ...charField,
    component: CoopDraftName,
    extractProps: (info) => ({
        ...charField.extractProps(info),
        draft: info.options.draft,
    }),
});
