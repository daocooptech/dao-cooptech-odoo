/** @odoo-module **/

import { Component, onWillStart, proxy, usePlugin, useProps } from "@odoo/owl";
import { NotificationPlugin } from "@web/core/notifications/notification_plugin";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { CoopTabs } from "@coop_theme/js/shell";

/**
 * «Прогноз и план» — слой 4 «Аналитики» (решение 423). Данные —
 * models/forecast.py, `coop.forecast.overview`.
 *
 * По каждому показателю: этот месяц (факт, план, темп), столбцы за 12
 * месяцев с отметкой плана, тренд на полгода вперёд штриховкой. План
 * задаётся здесь же — на месяц или сразу на несколько вперёд.
 */

const ROWS = 10;
const nf = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });

export class CoopForecast extends Component {
    static template = "coop_analytics.Forecast";
    static components = { CoopTabs };
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.notification = usePlugin(NotificationPlugin);
        this.state = proxy({ data: null, partnerId: null, edit: null, busy: false });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("coop.forecast", "overview", [this.state.partnerId]);
    }

    async pickPartner(id) {
        this.state.partnerId = id;
        this.state.edit = null;
        await this.load();
    }

    // ── формат ──────────────────────────────────────────────────────
    fmt(metric, v) {
        if (v === null || v === undefined) {
            return "—";
        }
        return metric.unit === "rub" ? `${nf.format(Math.round(v))} ₽` : nf.format(Math.round(v));
    }
    short(metric, v) {
        if (!v) {
            return "";
        }
        const a = Math.abs(v);
        if (metric.unit !== "rub") {
            return nf.format(Math.round(v));
        }
        if (a >= 1e6) {
            return `${(v / 1e6).toFixed(1).replace(".", ",")} млн`;
        }
        if (a >= 1e3) {
            return `${Math.round(v / 1e3)} тыс`;
        }
        return nf.format(Math.round(v));
    }

    // ── этот месяц ──────────────────────────────────────────────────
    pctLabel(metric) {
        const pct = metric.now.pct;
        if (pct === null || pct === undefined) {
            return "";
        }
        const of = metric.better === "down" ? "лимита" : "плана";
        if (pct > 999) {
            return `в ${nf.format(Math.round(pct / 100))} раз больше ${of}`;
        }
        return `${pct}% ${of}`;
    }
    barWidth(metric) {
        return `width: ${Math.min(100, metric.now.pct || 0)}%`;
    }
    status(metric) {
        const pct = metric.now.pct;
        if (pct === null || pct === undefined) {
            return "none";
        }
        if (metric.better === "down") {
            return pct > 100 ? "bad" : "good";
        }
        return pct >= 100 ? "good" : "track";
    }

    // ── график ──────────────────────────────────────────────────────
    scale(metric) {
        let max = 1;
        for (const m of metric.months) {
            max = Math.max(max, m.fact || 0, m.forecast || 0, m.plan || 0);
        }
        return max;
    }
    // BlockChart (дизайн-система): клеток в столбце — ROWS; факт — залитые
    // клетки (без плана — чернильные, план выполнен — бирюзовые, нет —
    // охра), тренд — клетки контуром над фактом, план — черта поперёк.
    count(metric, v) {
        if (!v || v <= 0) {
            return 0;
        }
        return Math.max(1, Math.min(ROWS, Math.round((v / this.scale(metric)) * ROWS)));
    }
    cells(metric, m) {
        const fact = this.count(metric, m.fact);
        const trend = !m.past && m.forecast !== null ? this.count(metric, m.forecast) : 0;
        const tone = m.done === true ? "o_coop_fc_c_done" : m.done === false ? "o_coop_fc_c_miss" : "o_coop_fc_c_fact";
        const out = [];
        for (let r = 0; r < ROWS; r++) {
            out.push(r < fact ? tone : r < trend ? "o_coop_fc_c_trend" : "");
        }
        return out;
    }
    planTop(metric, v) {
        const k = Math.min(ROWS, Math.round(((v || 0) / this.scale(metric)) * ROWS));
        return `bottom: calc(${((k / ROWS) * 100).toFixed(2)}% - 1px)`;
    }
    colClass(metric, m) {
        return {
            o_coop_fc_past: m.past,
            o_coop_fc_cur: m.current,
            o_coop_fc_future: !m.past && !m.current,
            o_coop_fc_done: m.done === true,
            o_coop_fc_miss: m.done === false,
        };
    }
    colTitle(metric, m) {
        const parts = [m.label];
        if (m.fact !== null) {
            parts.push(`факт ${this.fmt(metric, m.fact)}`);
        }
        if (m.forecast !== null) {
            parts.push(`тренд ${this.fmt(metric, m.forecast)}`);
        }
        if (m.plan !== null && m.plan !== undefined) {
            parts.push(`план ${this.fmt(metric, m.plan)}`);
        }
        return parts.join(" · ");
    }

    // ── план ────────────────────────────────────────────────────────
    futureMonths(metric) {
        return metric.months.filter((m) => !m.past);
    }
    openEdit(metric) {
        const now = metric.months.find((m) => m.current);
        this.state.edit = {
            metric: metric.key,
            month: now.key,
            target: now.plan ?? Math.round(metric.now.forecast || metric.avg || 0),
            repeat: "1",
        };
    }
    async savePlan(clear = false) {
        const e = this.state.edit;
        this.state.busy = true;
        try {
            await this.orm.call("coop.forecast", "set_plan", [
                this.state.partnerId,
                e.metric,
                e.month,
                clear ? null : Number(e.target) || 0,
                Number(e.repeat) || 1,
            ]);
            this.notification.add(clear ? "План снят" : "План сохранён", { type: "success" });
            this.state.edit = null;
            await this.load();
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("actions").add("coop_analytics.forecast", CoopForecast);
