/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useProps } from "@odoo/owl";

/**
 * Превью плитки каталога вакансий на странице «Добавить вакансию».
 *
 * Эталон — `VacancyAddPage` (решение 625): справа живая карточка каталога,
 * меняется по мере ввода. Разметка — та же, что у плитки
 * `view_coop_vacancy_kanban`, поэтому и вид тот же: обёртка
 * `.o_coop_vacancies` подхватывает правила `coop_vacancies.scss`.
 * Ставится на поле `id`.
 */
export class CoopVacancyPreview extends Component {
    static template = "coop_vacancies.VacancyPreview";
    props = useProps(standardFieldProps);

    get data() {
        return this.props.record.data;
    }

    get title() {
        const name = (this.data.name || "").trim();
        return name && name !== "Новая вакансия" ? name : "Кто нужен";
    }

    /** Подпись значения выбора — как её покажет плитка. */
    label(name) {
        const field = this.props.record.fields[name];
        const pair = (field.selection || []).find(([value]) => value === this.data[name]);
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
        return `/web/image/coop.vacancy/${this.props.record.resId}/image_512?unique=${unique}`;
    }

    get owner() {
        return this.data.partner_id || false;
    }

    get meta() {
        return [this.owner && this.owner.display_name, this.label("employment")]
            .filter(Boolean)
            .join(" · ");
    }
}

registry.category("fields").add("coop_vacancy_preview", {
    component: CoopVacancyPreview,
    supportedTypes: ["integer"],
});
