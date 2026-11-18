/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useProps } from "@odoo/owl";

/**
 * Превью плитки каталога навыков на странице «Добавить навык».
 *
 * Эталон — `SkillAddPage` (решение 625): справа живая карточка каталога,
 * меняется по мере ввода. Разметка — та же, что у плитки
 * `view_coop_skill_kanban`, поэтому и вид тот же: обёртка `.o_coop_skills`
 * подхватывает правила `coop_skills.scss`. Ставится на поле `id`.
 * Выбрана организация — превью со знаком организации (`ServiceAddPage`).
 */
export class CoopSkillPreview extends Component {
    static template = "coop_skills.SkillPreview";
    props = useProps(standardFieldProps);

    get data() {
        return this.props.record.data;
    }

    get isService() {
        return Boolean(this.data.partner_is_company);
    }

    get title() {
        const name = (this.data.name || "").trim();
        if (name && name !== "Новый навык") {
            return name;
        }
        return this.isService ? "Название услуги" : "Чем занимаетесь";
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
        return `/web/image/coop.skill.offer/${this.props.record.resId}/image_512?unique=${unique}`;
    }

    get owner() {
        return this.data.partner_id || false;
    }

    get rate() {
        return this.data.rate_display || "";
    }

    get meta() {
        const parts = [];
        if (this.owner) {
            parts.push(
                this.owner.display_name + (this.data.ready_to_travel ? ", готов к командировкам" : "")
            );
        }
        if (this.data.experience_display) {
            parts.push(this.data.experience_display);
        }
        return parts.join(" · ");
    }

    get skills() {
        const list = this.data.skill_ids;
        return list && list.records ? list.records.map((r) => r.data.display_name) : [];
    }
}

registry.category("fields").add("coop_skill_preview", {
    component: CoopSkillPreview,
    supportedTypes: ["integer"],
});
