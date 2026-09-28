/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { CoopTabs } from "@coop_theme/js/shell";

/**
 * «Портфель участника» — слой 3 «Аналитики» (решения 420, 421, 422).
 * Данные — models/portfolio.py, одним снимком.
 *
 * Сверху четыре раздельных блока: общего итога в рублях нет (решение 422),
 * пай, оценка труда и монеты в одну сумму не складываются. Ниже — что
 * придёт за 12 месяцев (договорено, расчётно, просрочено, натурой), затем
 * вложения по видам с оговорками юриста и открытая статистика платформы.
 */

const SECTIONS = [
    { key: "shares", label: "Паи" },
    { key: "projects", label: "Вклады в проекты" },
    { key: "farm", label: "Пулы проектов" },
    { key: "tokens", label: "Токены требования" },
    { key: "cfa", label: "ЦФА" },
    { key: "crypto", label: "Монеты" },
    { key: "payments", label: "Платежи по сделкам" },
];

const nf = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 });
const nf6 = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 6 });

export class CoopPortfolio extends Component {
    static template = "coop_analytics.Portfolio";
    static components = { CoopTabs };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.sections = SECTIONS;
        this.state = useState({ data: null, section: "shares", showOverdue: false });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("coop.portfolio", "snapshot", []);
    }

    // ── формат ──────────────────────────────────────────────────────
    rub(v) {
        return `${nf.format(Math.round(v || 0))} ₽`;
    }
    num(v) {
        return nf2.format(v || 0);
    }
    coins(v) {
        return nf6.format(v || 0);
    }
    date(s) {
        if (!s) {
            return "—";
        }
        const [y, m, d] = s.split("-");
        return `${d}.${m}.${y}`;
    }
    count(section) {
        return (this.state.data?.[section] || []).length;
    }

    // ── график поступлений ──────────────────────────────────────────
    get scale() {
        const s = this.state.data.schedule;
        let max = Math.max(s.overdue.in, s.overdue.out, 1);
        for (const m of s.months) {
            max = Math.max(max, m.contract + m.estimate, m.out);
        }
        return max;
    }
    bar(value) {
        return `height: ${Math.max(0, (value / this.scale) * 100).toFixed(1)}%`;
    }
    get monthsTotal() {
        const months = this.state.data.schedule.months;
        return {
            contract: months.reduce((a, m) => a + m.contract, 0),
            estimate: months.reduce((a, m) => a + m.estimate, 0),
            out: months.reduce((a, m) => a + m.out, 0),
        };
    }

    // ── распределение активов с оценкой ─────────────────────────────
    partStyle(part, index) {
        return `width: ${Math.max(part.pct, 0.6)}%; background: var(--coop-pf-c${index % 5})`;
    }
    dotStyle(index) {
        return `background: var(--coop-pf-c${index % 5})`;
    }

    // ── переходы ────────────────────────────────────────────────────
    openRecord(model, id) {
        if (!id) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("coop_analytics.portfolio", CoopPortfolio);
