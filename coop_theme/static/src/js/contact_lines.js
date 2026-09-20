/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";

/**
 * Свободные строки контактов: «название — значение», сколько нужно.
 *
 * Перечень видов связи устаревает быстрее платформы: Skype, мессенджеры,
 * соцсети и приложения жили в карточке отдельными полями, и каждый новый
 * способ связи требовал бы своего. Владелец 16 сентября 2026 решил
 * обратное: человек сам называет, чем с ним связаться.
 *
 * Правка идёт прямо в базу, а не через черновик формы: строка — своя
 * запись, и добавление третьего телефона не должно делать всю страницу
 * «изменённой» и спрашивать про несохранённое на выходе. Показ берётся
 * из самой формы, так что после записи достаточно перечитать карточку.
 */
export class CoopContactLines extends Component {
    static template = "coop_theme.ContactLines";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        // editing: id правимой строки, 'new' — добавляемая, null — покой.
        this.ui = useState({ editing: null, name: "", value: "", busy: false });
    }

    get lines() {
        return this.props.record.data[this.props.name].records;
    }

    get canEdit() {
        return !this.props.readonly;
    }

    start(line) {
        this.ui.editing = line.resId;
        this.ui.name = line.data.name || "";
        this.ui.value = line.data.value || "";
    }

    startNew() {
        this.ui.editing = "new";
        this.ui.name = "";
        this.ui.value = "";
    }

    cancel() {
        this.ui.editing = null;
    }

    /** Пустое название или пустое значение — не строка, а недоразумение. */
    get filled() {
        return Boolean(this.ui.name.trim() && this.ui.value.trim());
    }

    async accept() {
        if (this.ui.busy || !this.filled) {
            return;
        }
        this.ui.busy = true;
        try {
            const values = {
                name: this.ui.name.trim(),
                value: this.ui.value.trim(),
            };
            if (this.ui.editing === "new") {
                await this.orm.create("coop.contact.line", [
                    { ...values, partner_id: this.props.record.resId },
                ]);
            } else {
                await this.orm.write("coop.contact.line", [this.ui.editing], values);
            }
            await this.props.record.load();
            this.ui.editing = null;
        } finally {
            this.ui.busy = false;
        }
    }

    async remove(line) {
        if (this.ui.busy) {
            return;
        }
        this.ui.busy = true;
        try {
            await this.orm.unlink("coop.contact.line", [line.resId]);
            await this.props.record.load();
        } finally {
            this.ui.busy = false;
        }
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

export const coopContactLines = {
    component: CoopContactLines,
    displayName: "Свободные строки контактов",
    supportedTypes: ["one2many"],
    relatedFields: () => [
        { name: "name", type: "char" },
        { name: "value", type: "char" },
        { name: "sequence", type: "integer" },
    ],
};

registry.category("fields").add("coop_contact_lines", coopContactLines);
