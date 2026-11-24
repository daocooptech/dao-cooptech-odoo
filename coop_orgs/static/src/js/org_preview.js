/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useProps } from "@odoo/owl";

/**
 * Превью плитки каталога организаций на странице «Добавить организацию».
 *
 * Эталон — `OrgAddPage` (решение 625). Разметка — та же, что у плитки
 * `view_coop_orgs_kanban`: обёртка `.o_coop_orgs` подхватывает правила
 * `coop_orgs.scss`. Ставится на поле `id`.
 */
export class CoopOrgPreview extends Component {
    static template = "coop_orgs.OrgPreview";
    props = useProps(standardFieldProps);

    get data() {
        return this.props.record.data;
    }

    get title() {
        return (this.data.name || "").trim() || "Название организации";
    }

    /** Новый знак ещё не сохранён — показываем его как есть. */
    get image() {
        const value = this.data.image_1920;
        if (!value) {
            return false;
        }
        if (typeof value === "string" && value.length > 200) {
            return `data:image/*;base64,${value}`;
        }
        return `/web/image/coop.org.add/${this.props.record.resId}/image_1920`;
    }

    get okved() {
        return (this.data.okved_id && this.data.okved_id.display_name) || "";
    }
}

registry.category("fields").add("coop_org_preview", {
    component: CoopOrgPreview,
    supportedTypes: ["integer"],
});
