/**
 * Кольцо готовности — как в макете карточки проекта.
 *
 * Полоса движка отвечает на вопрос «сколько процентов», а в макете
 * готовность стоит рядом с названием и снимком и читается одним
 * взглядом, не отвлекая на себя строку формы. Полоса там же выглядит
 * как настройка, а не как главное число страницы.
 *
 * Обрезки по сотне нет намеренно: проект, собравший втрое больше
 * нужного, показывает своё число. Ограничена только дуга — рисовать
 * больше полного круга нечем.
 */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const RADIUS = 26;
const LENGTH = 2 * Math.PI * RADIUS;

export class CoopReadinessRing extends Component {
    static template = "coop_projects.ReadinessRing";
    static props = { ...standardFieldProps };

    get percent() {
        return this.props.record.data[this.props.name] || 0;
    }

    get dashArray() {
        return LENGTH.toFixed(1);
    }

    /** Непройденная часть круга. Сто процентов и больше — круг целиком. */
    get dashOffset() {
        const share = Math.min(Math.max(this.percent, 0), 100) / 100;
        return (LENGTH * (1 - share)).toFixed(1);
    }

    /** Цвет отвечает на «успевает ли»: до трети — тревожный. */
    get state() {
        if (this.percent >= 100) { return "o_coop_ring_full"; }
        if (this.percent < 34) { return "o_coop_ring_low"; }
        return "";
    }
}

registry.category("fields").add("coop_readiness_ring", {
    component: CoopReadinessRing,
    supportedTypes: ["integer", "float"],
});
