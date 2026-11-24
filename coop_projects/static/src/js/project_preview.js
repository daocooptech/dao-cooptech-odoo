/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useProps } from "@odoo/owl";

/**
 * Превью плитки каталога проектов на странице «Добавить проект».
 *
 * Эталон — `ProjectAddPage` (решение 625). Разметка — та же, что у плитки
 * `view_coop_project_kanban`: обёртка `.o_coop_projects` подхватывает
 * правила `coop_projects.scss`. Ставится на поле `id`.
 */
export class CoopProjectPreview extends Component {
    static template = "coop_projects.ProjectPreview";
    props = useProps(standardFieldProps);

    get data() {
        return this.props.record.data;
    }

    get title() {
        const name = (this.data.name || "").trim();
        return name && name !== "Новый проект" ? name : "Название проекта";
    }

    get kind() {
        const pair = this.props.record.fields.kind.selection.find(
            ([value]) => value === this.data.kind);
        return pair ? pair[1] : "";
    }

    /** Новый снимок ещё не сохранён — показываем его как есть. */
    get image() {
        const value = this.data.image_1920;
        if (!value) {
            return false;
        }
        if (typeof value === "string" && value.length > 200) {
            return `data:image/*;base64,${value}`;
        }
        const unique = encodeURIComponent(this.data.write_date || "");
        return `/web/image/coop.project/${this.props.record.resId}/image_512?unique=${unique}`;
    }

    get owner() {
        return this.data.partner_id || false;
    }

    /** Засечка порога; при полном сборе совпала бы с концом полосы. */
    get mark() {
        const value = this.data.funding_rule === "threshold" ? this.data.funding_threshold : 0;
        return value && value < 100 ? value : 0;
    }
}

registry.category("fields").add("coop_project_preview", {
    component: CoopProjectPreview,
    supportedTypes: ["integer"],
});
