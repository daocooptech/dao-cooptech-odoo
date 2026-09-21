/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useEffect, useRef, useState } from "@odoo/owl";

/**
 * Описание, которое правится по карандашу.
 *
 * То же, что «О себе» и строка карточки, но для длинного текста: абзацы,
 * а не строка. Владелец 21 сентября 2026: «нужно ко всем полям которые
 * мы редактируем добавить иконку карандаша и редактирование происходит
 * только при нажатии, а когда происходит редакция две иконки галочка
 * (сохранить) и крестик (отмена редакции)».
 *
 * Почему не штатный редактор разметки. Он всегда выглядит полем ввода:
 * страница проекта, которую пришли читать, показывает рамку на пол-экрана
 * и предлагает править там, где никто не собирался. Плюс страничная пара
 * «сохранить/отменить» появляется от первой же буквы.
 *
 * Разметка. В этих полях лежат абзацы и ничего больше — проверено по
 * боевой базе: 668 описаний, тег ровно один, `p`. Поэтому правка идёт
 * простым текстом: абзац — строка, пустая строка — новый абзац. Если в
 * значении окажется что-то кроме абзацев и переносов, карандаш не
 * показывается вовсе: молча превратить таблицу в текст хуже, чем не дать
 * её править отсюда.
 */
const ПРОСТЫЕ_ТЕГИ = new Set(["p", "br", "div", "span"]);

export class CoopBlockField extends Component {
    static template = "coop_theme.BlockField";
    static props = {
        ...standardFieldProps,
        placeholder: { type: String, optional: true },
        rows: { type: Number, optional: true },
    };

    setup() {
        // Черновик держится в стороне от записи: пока не нажали галочку,
        // страница не считается изменённой, а отмена — это просто выход
        // из правки.
        this.ui = useState({ editing: false, draft: "", busy: false });
        this.input = useRef("input");
        useEffect(
            (el) => {
                if (el) {
                    el.focus();
                    el.setSelectionRange(el.value.length, el.value.length);
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

    get isHtml() {
        return this.field.type === "html";
    }

    /** Что показывать в чтении: разметку — как разметку, текст — абзацами. */
    get paragraphs() {
        const value = String(this.value || "");
        if (!value) {
            return [];
        }
        if (!this.isHtml) {
            return value.split(/\n{2,}/).filter((кусок) => кусок.trim());
        }
        return this.toText(value).split(/\n{2,}/).filter((кусок) => кусок.trim());
    }

    /** Разметка → текст: абзац становится строкой, `<br>` — переносом. */
    toText(html) {
        return String(html)
            .replace(/<br\s*\/?>/gi, "\n")
            .replace(/<\/p\s*>/gi, "\n\n")
            .replace(/<[^>]+>/g, "")
            .replace(/&nbsp;/gi, " ")
            .replace(/&amp;/gi, "&")
            .replace(/&lt;/gi, "<")
            .replace(/&gt;/gi, ">")
            .replace(/\n{3,}/g, "\n\n")
            .trim();
    }

    /** Текст → разметка: строка становится абзацем. */
    toHtml(text) {
        const абзацы = String(text || "")
            .split(/\n{2,}/)
            .map((кусок) => кусок.trim())
            .filter(Boolean);
        if (!абзацы.length) {
            return false;
        }
        return абзацы
            .map((абзац) => "<p>" + this.escape(абзац).replace(/\n/g, "<br>") + "</p>")
            .join("");
    }

    escape(text) {
        return String(text)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }

    /**
     * Можно ли править отсюда. Не «есть ли право» — право берётся из
     * `readonly` представления, — а «не потеряем ли разметку».
     */
    get canEdit() {
        if (this.props.readonly) {
            return false;
        }
        if (!this.isHtml) {
            return true;
        }
        const теги = String(this.value || "").match(/<\s*([a-zA-Z0-9]+)/g) || [];
        return теги.every((тег) => ПРОСТЫЕ_ТЕГИ.has(тег.replace(/[<\s]/g, "").toLowerCase()));
    }

    start() {
        this.ui.draft = this.isHtml ? this.toText(this.value) : String(this.value || "");
        this.ui.editing = true;
    }

    async accept() {
        if (this.ui.busy) {
            return;
        }
        this.ui.busy = true;
        try {
            const значение = this.isHtml
                ? this.toHtml(this.ui.draft)
                : (this.ui.draft || false);
            await this.props.record.update({ [this.props.name]: значение });
            const записано = await this.props.record.save();
            if (записано !== false) {
                this.ui.editing = false;
            }
        } finally {
            this.ui.busy = false;
        }
    }

    cancel() {
        this.ui.editing = false;
    }

    onInput(event) {
        this.ui.draft = event.target.value;
    }

    onKeydown(event) {
        // Перевод строки набирает абзац, а сохраняет Ctrl+Enter: иначе
        // описание из двух абзацев не написать.
        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            this.accept();
        } else if (event.key === "Escape") {
            event.preventDefault();
            this.cancel();
        }
    }
}

export const coopBlockField = {
    component: CoopBlockField,
    displayName: "Описание с правкой по месту",
    supportedTypes: ["text", "html"],
    extractProps: ({ attrs, options }) => ({
        placeholder: attrs.placeholder,
        rows: options.rows ? Number(options.rows) : undefined,
    }),
};

registry.category("fields").add("coop_block", coopBlockField);
