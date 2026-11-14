/**
 * «Сводка» управления проектом (образец WorkHeaderD, задача 449, кусок 2).
 *
 * Данные — поле `coop_summary` (Json): «Статус» плашкой и строки
 * «значок · подпись · тонкая шкала · значение». Строка — переход, тот же,
 * что у бывшей кнопки-счётчика движка: метод проекта по ключу строки
 * (`action_coop_summary_open`).
 *
 * Место — правая колонка над перепиской. Переписку движок собирает при
 * компиляции формы (`mail/.../form_compiler.js`), поэтому блок «Сводки»
 * из листа копируется в её контейнер там же, при сборке. В листе блок
 * остаётся: он виден, когда переписка ушла вниз (узкий экран), а копия
 * у переписки — когда переписка сбоку. Какой из двух показан — решает
 * стиль по классу `o-aside` контейнера переписки.
 */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { FormCompiler } from "@web/views/form/form_compiler";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { CoopIcon } from "@coop_theme/js/icons";

export class CoopProjectSummary extends Component {
    static template = "coop_projects.ProjectSummary";
    static components = { CoopIcon };
    props = useProps(standardFieldProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
    }

    get data() {
        return this.props.record.data[this.props.name] || { rows: [] };
    }

    get status() {
        return this.data.status || { code: "to_define", label: "" };
    }

    barStyle(row) {
        return `width: ${Math.max(0, Math.min(100, row.pct || 0))}%`;
    }

    async open(ev, key) {
        ev.preventDefault();
        const record = this.props.record;
        if (!record.resId) {
            return;
        }
        const action = await this.orm.call(
            record.resModel, "action_coop_summary_open", [[record.resId], key]);
        if (action) {
            // Действия движка вычисляют домен по `active_id` на клиенте
            // («Обновления» проекта): без него — ошибка разбора выражения.
            await this.action.doAction(action, {
                additionalContext: { active_id: record.resId, active_model: record.resModel },
            });
        }
    }
}

registry.category("fields").add("coop_project_summary", {
    component: CoopProjectSummary,
    supportedTypes: ["json"],
});

patch(FormCompiler.prototype, {
    compile(node, params) {
        const res = super.compile(node, params);
        const side = res.querySelector(".o_coop_pm_side");
        const chatter = res.querySelector(".o-mail-Form-chatter:not(.o-isInFormSheetBg)");
        if (side && chatter && !chatter.querySelector(".o_coop_pm_aside")) {
            const copy = side.cloneNode(true);
            copy.classList.remove("o_coop_pm_side");
            copy.classList.add("o_coop_pm_aside");
            chatter.prepend(copy);
        }
        return res;
    },
});
