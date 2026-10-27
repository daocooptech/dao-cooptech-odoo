/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useProps } from "@odoo/owl";

/**
 * Превью карточки каталога на странице «Разместить объявление».
 *
 * Эталон — `ResourceAddPage` (решение 625, сверка 27.10.2026): справа
 * живая плитка `ResourceCard`, меняется по мере ввода — человек видит,
 * как объявление будет выглядеть в каталоге, до публикации.
 *
 * Разметка — та же, что у плитки каталога (`view_coop_resource_kanban`),
 * поэтому и вид тот же без отдельных стилей: обёртка `.o_coop_resources`
 * подхватывает правила `coop_resources.scss`. Ставится на поле `id`.
 */
export class CoopResourcePreview extends Component {
    static template = "coop_resources.ResourcePreview";
    props = useProps(standardFieldProps);

    get data() {
        return this.props.record.data;
    }

    get title() {
        const name = (this.data.name || "").trim();
        return name && name !== "Новое объявление" ? name : "Название объявления";
    }

    get kindLabel() {
        const field = this.props.record.fields.listing_type;
        const pair = (field.selection || []).find(([value]) => value === this.data.listing_type);
        return pair ? pair[1] : "";
    }

    get isRequest() {
        return this.data.listing_type === "request";
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
        return `/web/image/coop.resource/${this.props.record.resId}/image_512?unique=${unique}`;
    }

    get owner() {
        return this.data.owner_id || false;
    }

    get meta() {
        return [this.owner && this.owner.display_name, this.data.category_id && this.data.category_id.display_name]
            .filter(Boolean)
            .join(" · ");
    }
}

registry.category("fields").add("coop_resource_preview", {
    component: CoopResourcePreview,
    supportedTypes: ["integer"],
});
