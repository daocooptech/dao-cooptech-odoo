/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
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
/** Номер из ссылки, как бы её ни прислали: запись, пара или число. */
function valueOfPair(link) {
    if (Array.isArray(link)) {
        return link[0];
    }
    return typeof link === "number" ? link : undefined;
}

export class CoopInlineField extends Component {
    static template = "coop_theme.InlineField";
    static props = {
        ...standardFieldProps,
        placeholder: { type: String, optional: true },
        // Длинное значение переносится, а не обрезается многоточием.
        // Название проекта в одну строку не помещается: владелец
        // 21 сентября 2026 — «в проектах название включает очень мало
        // символов, из-за этого не видно название полностью».
        wrap: { type: Boolean, optional: true },
        rows: { type: Number, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        // `options` — подсказки для связи: пусто, пока не начали набирать.
        // `chosen` — что выбрали из подсказок, до галочки ещё не записано.
        this.ui = useState({
            editing: false, draft: "", busy: false, options: [], chosen: null,
        });
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
            return value.toFormat("dd.MM.yyyy");
        }
        if (this.field.type === "datetime") {
            return value.toFormat("dd.MM.yyyy HH:mm");
        }
        if (this.field.type === "many2one") {
            return value.display_name || "";
        }
        if (this.field.type === "selection") {
            const option = (this.field.selection || []).find(([key]) => key === value);
            return option ? option[1] : String(value);
        }
        // Числа и деньги — форматировщиком движка, а не как есть.
        //
        // Владелец 22 сентября 2026 про страницу проекта: «в блоке
        // ресурсы "нужно" написано цифрами слитно и без валюты, сделать
        // как ниже в "собрано"». Так и было: «собрано» рисует движок и
        // получается «1 455 000,00 ₽», а «нужно» правится по месту, и
        // наш виджет печатал `String(value)` — «1455000».
        //
        // Берём тот же реестр `formatters`, которым движок форматирует
        // поля (документация, `frontend/registries`). Свой разбор разрядов
        // и валют писать нельзя: он разойдётся с движком на первой же
        // настройке языка, и два числа на одной странице будут выглядеть
        // по-разному — ровно то, что владелец и заметил.
        if (["monetary", "float", "integer"].includes(this.field.type)) {
            const format = registry.category("formatters").get(this.field.type, null);
            if (format) {
                const options = {};
                if (this.field.digits) {
                    options.digits = this.field.digits;
                }
                if (this.field.type === "monetary") {
                    const поле = this.field.currency_field || "currency_id";
                    const валюта = this.props.record.data[поле];
                    // Ссылка приходит то записью, то парой, то числом —
                    // смотря как поле объявлено. Берём номер из любого.
                    const номер = валюта && (валюта.id ?? valueOfPair(валюта));
                    if (номер) {
                        options.currencyId = номер;
                    }
                }
                try {
                    return format(value, options);
                } catch (ошибка) {
                    console.warn("[правка по месту] не отформатировалось:", ошибка);
                }
            }
        }
        return String(value);
    }

    /** Число ли это. Нужно, чтобы набрать его тем же шрифтом, каким
     *  движок набирает свои числа: в столбце сумм цифры разной ширины
     *  глазом не сравниваются. */
    get isNumeric() {
        return ["monetary", "float", "integer"].includes(this.field.type);
    }

    /** Набирают в несколько строк: длинный текст и всё, что переносится. */
    get isMultiline() {
        return this.field.type === "text" || this.props.wrap === true;
    }

    /** Чем набирают: строка, дата, число. */
    get inputType() {
        const type = this.field.type;
        if (type === "date") {
            return "date";
        }
        if (type === "datetime") {
            return "datetime-local";
        }
        if (type === "integer" || type === "float" || type === "monetary") {
            return "number";
        }
        return "text";
    }

    /** Выбор из списка — свой вид правки: не набирают, а выбирают. */
    get isSelection() {
        return this.field.type === "selection";
    }

    /** Связь — набирают и выбирают из подсказок. */
    get isRelation() {
        return this.field.type === "many2one";
    }

    get selectionOptions() {
        return this.field.selection || [];
    }

    get canEdit() {
        return !this.props.readonly;
    }

    get maxlength() {
        return this.field.size || undefined;
    }

    start() {
        const value = this.value;
        this.ui.options = [];
        this.ui.chosen = null;
        if (this.field.type === "date" && value) {
            this.ui.draft = value.toFormat("yyyy-MM-dd");
        } else if (this.field.type === "datetime" && value) {
            // Поле ввода времени понимает только такой вид, без пояса:
            // «2026-09-21T18:30».
            this.ui.draft = value.toFormat("yyyy-MM-dd'T'HH:mm");
        } else if (this.isRelation) {
            // В строке — то, что уже выбрано: правка начинается с
            // прежнего ответа, а не с чистого листа.
            this.ui.draft = value ? value.display_name || "" : "";
            this.ui.chosen = value || null;
        } else {
            this.ui.draft = value || "";
        }
        this.ui.editing = true;
    }

    /**
     * Подсказки для связи. Справочник может быть на тысячи строк —
     * выпадающий список со всеми не годится: его не пролистать. Поэтому
     * спрашиваем у сервера по набранному, как это делает сам движок.
     *
     * Отбор поля здесь не передаётся (`domain` у `name_search`): на
     * карточке все связи — простые справочники без условий. Появится
     * условие — передавать придётся, иначе подскажем то, чего выбрать
     * нельзя.
     */
    async suggest(term) {
        const pairs = await this.orm.call(
            this.field.relation, "name_search", [], {
                name: term || "",
                limit: 8,
            });
        this.ui.options = pairs.map(([id, display_name]) => ({ id, display_name }));
    }

    pick(option) {
        this.ui.chosen = option;
        this.ui.draft = option ? option.display_name : "";
        this.ui.options = [];
        this.accept();
    }

    async accept() {
        if (this.ui.busy) {
            return;
        }
        this.ui.busy = true;
        try {
            const value = this.isRelation
                ? (this.ui.draft ? this.ui.chosen : false)
                : this.parse(this.ui.draft);
            // Связь без выбора из подсказок — не значение: набранное
            // руками название может не совпасть ни с одной записью, и
            // молча стереть прежнее было бы хуже, чем ничего не делать.
            if (this.isRelation && this.ui.draft && !this.ui.chosen) {
                this.ui.busy = false;
                return;
            }
            await this.props.record.update({ [this.props.name]: value });
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
        if (this.field.type === "float" || this.field.type === "monetary") {
            return parseFloat(draft) || 0;
        }
        return draft;
    }

    cancel() {
        this.ui.editing = false;
    }

    onInput(event) {
        this.ui.draft = event.target.value;
        if (this.isRelation) {
            // Набрали своё — прежний выбор больше не в счёт.
            this.ui.chosen = null;
            this.suggest(this.ui.draft);
        }
    }

    /** Выбор из списка записывается сразу: выбрали — значит ответили. */
    async onSelect(event) {
        this.ui.draft = event.target.value;
        await this.accept();
    }

    onKeydown(event) {
        if (event.key === "Enter") {
            // В многострочном поле перевод строки — это перевод строки, а
            // не «готово»: иначе абзац не набрать. Там сохраняет Ctrl+Enter.
            if (this.isMultiline && !event.ctrlKey && !event.metaKey) {
                return;
            }
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
    supportedTypes: ["char", "text", "date", "datetime", "integer", "float",
                     "monetary", "selection", "many2one"],
    extractProps: ({ attrs, options }) => ({
        placeholder: attrs.placeholder,
        wrap: options.wrap === true || options.wrap === "true",
        rows: options.rows ? Number(options.rows) : undefined,
    }),
};

registry.category("fields").add("coop_inline", coopInlineField);
