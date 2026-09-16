/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useEffect, useRef, useState } from "@odoo/owl";

/**
 * Блок «О себе» с правкой по карандашу.
 *
 * Страница участника читается, а не заполняется: человек заходит на неё
 * смотреть, а правит раз в полгода. Поэтому поле здесь не должно всё
 * время выглядеть полем ввода — рамка на весь блок обещает правку там,
 * где её никто не начинал, и делает чужую страницу неотличимой от своей.
 *
 * Владелец 16 сентября 2026: «блок обо мне, сделай иконку редактирования
 * справа, а когда редактируем галочку и крестик, что бы можно было либо
 * опубликовать либо отменить редактирование».
 *
 * Отсюда три состояния: чтение с карандашом, правка с галочкой и
 * крестиком, и чужая страница — без единой кнопки. Третье берётся из
 * `readonly` самого поля (в представлении стоит `not coop_is_self`), а не
 * из своей проверки: право правки уже описано там, и второе описание
 * рядом рано или поздно разойдётся с первым.
 *
 * Шапка полосы нарисована здесь же, а не в представлении: карандаш стоит
 * в ней, и разводить кнопку и её состояние по двум местам значило бы
 * связывать их через DOM.
 */
export class CoopAboutField extends Component {
    static template = "coop_profile.AboutField";
    // Наследовать штатное поле не выходит: оно заводит свою работу с
    // полем ввода — ссылку на него, слежение за значением, разбор на
    // лету, — а ввода в чтении нет вовсе. Ссылка оказывалась пустой, и
    // обработчики кнопок молча не навешивались: ни ошибки, ни правки.
    static props = {
        ...standardFieldProps,
        placeholder: { type: String, optional: true },
    };

    setup() {
        // Черновик держится в стороне от записи, и это главное здесь.
        //
        // Если писать прямо в запись, страница становится изменённой с
        // первой же буквы: уход с неё спрашивает про несохранённое, а
        // отмена обязана помнить прежнее значение и возвращать его.
        // Черновик снимает и то и другое: отмена — это просто выход из
        // правки, запись при этом не тронута.
        this.ui = useState({ editing: false, draft: "", busy: false });
        this.input = useRef("input");
        useEffect(
            (el) => {
                if (el) {
                    el.focus();
                    // Курсор в конец, а не в начало: правят обычно
                    // дописывая, а выделенный целиком текст стирается
                    // первой же клавишей.
                    el.setSelectionRange(el.value.length, el.value.length);
                }
            },
            () => [this.input.el]
        );
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }

    get canEdit() {
        return !this.props.readonly;
    }

    get maxlength() {
        // Длина ограничена в базе (`varchar(280)`), и поле должно
        // говорить об этом до отправки, а не отказом после.
        return this.props.record.fields[this.props.name]?.size || undefined;
    }

    start() {
        this.ui.draft = this.value;
        this.ui.editing = true;
    }

    async accept() {
        if (this.ui.busy) {
            return;
        }
        this.ui.busy = true;
        try {
            await this.props.record.update({ [this.props.name]: this.ui.draft });
            const saved = await this.props.record.save();
            // Отказ сохранения (проверка на сервере, права) оставляет
            // правку открытой: закрыть её значило бы показать прежнее
            // значение так, будто новое принято.
            if (saved !== false) {
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

    /**
     * Enter — опубликовать, Esc — отменить.
     *
     * Строка одна, переносов в ней не бывает, поэтому Enter свободен и
     * значит ровно то же, что галочка.
     */
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

export const coopAboutField = {
    component: CoopAboutField,
    displayName: "О себе с правкой по карандашу",
    supportedTypes: ["char"],
    extractProps: ({ attrs }) => ({ placeholder: attrs.placeholder }),
};

registry.category("fields").add("coop_about", coopAboutField);
