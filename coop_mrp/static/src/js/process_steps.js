/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, markup, proxy, t, useProps } from "@odoo/owl";
import { CoopIcon } from "@coop_theme/js/icons";

/** Окно «Инструкция» или «Результат» операции. */
class CoopProcessDoc extends Component {
    static template = "coop_mrp.ProcessDoc";
    static components = { Dialog };
    props = useProps({ close: t.function(), title: t.string(), body: t.any() });
}

/**
 * Технологический процесс на витрине ресурса (`ProcessSteps`, решение 630).
 *
 * Сверху полоса из отрезков по длительности этапов, ниже этапы; у
 * раскрытого — операции с номером «2.1», длительностью и ссылками
 * «Инструкция», «Результат». Данные считает `coop.resource._coop_process`.
 */
export class CoopProcessSteps extends Component {
    static template = "coop_mrp.ProcessSteps";
    static components = { CoopIcon };
    props = useProps(standardFieldProps);

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.state = proxy({ open: 0 });
    }

    get steps() {
        return this.props.record.data[this.props.name] || [];
    }

    get total() {
        return this.steps.reduce((sum, s) => sum + (s.minutes || 0), 0) || 1;
    }

    pct(step) {
        return Math.round(((step.minutes || 0) / this.total) * 100) + "%";
    }

    toggle(index) {
        this.state.open = this.state.open === index ? -1 : index;
    }

    async openDoc(link) {
        const doc = await this.orm.call("coop.resource", "coop_process_doc",
            [[this.props.record.resId], link.op, link.kind]);
        this.dialog.add(CoopProcessDoc, { title: doc.title, body: markup(doc.body) });
    }
}

registry.category("fields").add("coop_process_steps", {
    component: CoopProcessSteps,
    supportedTypes: ["json"],
});
