/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, t, useProps } from "@odoo/owl";

/**
 * Страница добавления — номер раздела и «Готово к публикации».
 *
 * Эталон — README дизайн-системы, «Страница добавления», и компоненты
 * `AddSection`, `Readiness` (решение 625, сверка 27.10.2026): человек
 * должен видеть, сколько осталось и что получится. Заполненный раздел
 * получает галочку вместо номера, справа — список того, что заполнено,
 * обязательное помечено «нужно».
 *
 * Оба виджета ставятся на поле `id` и сами значение не меняют: читают
 * запись и перерисовываются по мере ввода. Что считать заполненным —
 * в параметрах вида (`options`), а не здесь: у каждой страницы свои поля.
 *
 * Пункт: `{ field | fields, label, required, empty, anchor }`.
 * `fields` — заполнено хотя бы одно из полей (сырьё или оборудование),
 * `empty` — значение, которое заполненным не считается (имя черновика
 * «Новое объявление»), `anchor` — `name` раздела, к которому ведёт пункт.
 */

/** Заполнено ли поле: у каждого вида поля своя «пустота». */
export function isFilled(record, name, empty) {
    const value = record.data[name];
    const field = record.fields[name];
    if (!field || value === undefined || value === null || value === false) {
        return false;
    }
    if (["many2many", "one2many"].includes(field.type)) {
        return Boolean(value.count || (value.records && value.records.length));
    }
    if (field.type === "html") {
        return String(value).replace(/<[^>]+>/g, "").trim().length > 0;
    }
    if (["integer", "float", "monetary"].includes(field.type)) {
        return value > 0;
    }
    if (typeof value === "string") {
        const text = value.trim();
        return Boolean(text) && text !== empty;
    }
    return Boolean(value);
}

function itemFilled(record, item) {
    const names = item.fields || [item.field];
    return names.some((name) => isFilled(record, name, item.empty));
}

export class CoopAddStep extends Component {
    static template = "coop_theme.AddStep";
    props = useProps({
        ...standardFieldProps,
        num: t.number(),
        any: t.boolean().optional(),
        items: t.array(),
    });

    /** Обычно раздел заполнен, когда заполнено всё; необязательный
     * («Кто делает и из чего») — когда заполнено хоть что-то. */
    get done() {
        const check = (item) => itemFilled(this.props.record, item);
        return this.props.any ? this.props.items.some(check) : this.props.items.every(check);
    }
}

registry.category("fields").add("coop_add_step", {
    component: CoopAddStep,
    supportedTypes: ["integer"],
    extractProps: ({ options }) => ({
        num: options.num || 1,
        any: Boolean(options.any),
        items: (options.fields || []).map((name) => ({ field: name, empty: options.empty })),
    }),
});

export class CoopAddReady extends Component {
    static template = "coop_theme.AddReady";
    props = useProps({
        ...standardFieldProps,
        title: t.string().optional(),
        items: t.array(),
    });

    get rows() {
        return this.props.items.map((item, index) => ({
            ...item,
            key: index,
            done: itemFilled(this.props.record, item),
        }));
    }

    get doneCount() {
        return this.rows.filter((row) => row.done).length;
    }

    /** К разделу — прокруткой, без смены адреса страницы. */
    go(anchor) {
        const target = anchor && document.querySelector(`[name="${anchor}"]`);
        if (target) {
            target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }
}

registry.category("fields").add("coop_add_ready", {
    component: CoopAddReady,
    supportedTypes: ["integer"],
    extractProps: ({ options }) => ({
        title: options.title,
        items: options.items || [],
    }),
});
