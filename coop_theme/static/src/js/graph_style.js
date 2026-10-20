/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { GraphRenderer } from "@web/views/graph/graph_renderer";

/**
 * Графики движка — в цветах платформы (эталон: `BlockChart`, `LineChart`,
 * `AnalyticsDealsPage`; README дизайн-системы, «Графики»).
 *
 * Штатный вид `graph` красит серии палитрой Chart.js — синий, розовый,
 * бирюзовый, оранжевый, — и на «Панелях управления» каждый график выглядел
 * чужим (владелец 21.10: «все графики везде тоже не в стиле платформы»).
 * По эталону данные — чернильные, цвет несёт смысл и появляется точечно:
 * исполняется — `coop-teal`, внимание и переговоры — `coop-gold`,
 * просрочка — `coop-error`, отменённое — `coop-line-strong`. Подписи осей —
 * моноширинным, прописными; сетка — `coop-line`.
 *
 * Цвета читаются из переменных темы при каждой отрисовке, поэтому тёмная
 * тема подхватывается сама. `getColor` подменить нельзя: рендерер взял его
 * при загрузке, — красим готовые наборы данных после штатной сборки.
 */
const MONO = "'JetBrains Mono', ui-monospace, monospace";

function tokens() {
    // Токены объявлены на `.o_web_client` (backend.scss), не на корне.
    const css = getComputedStyle(document.querySelector(".o_web_client") || document.documentElement);
    const v = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
    return {
        ink: v("--coop-ink", "#1d1d1b"),
        teal: v("--coop-teal", "#14877c"),
        gold: v("--coop-gold", "#c9971c"),
        error: v("--coop-error", "#c0392b"),
        slate: v("--coop-slate", "#4a4a44"),
        slateLight: v("--coop-slate-light", "#8f8f88"),
        lineStrong: v("--coop-line-strong", "#c9c9c1"),
        line: v("--coop-line", "#e4e4de"),
    };
}

// Смысл по названию серии: состояния сделок, задач, выплат.
const MEANING = [
    [/исполня|в работе|выполня|активн|открыт|подтвержд/i, "teal"],
    [/переговор|ожида|черновик|на согласован|рассмотр/i, "gold"],
    [/просроч|спор|ошибк|отклон/i, "error"],
    [/отмен|закрыт без|архив/i, "lineStrong"],
    [/заверш|выполнен|оплачен|закрыт|готов/i, "ink"],
];

function seriesColors(labels, c) {
    // Сперва смысл, потом порядок — и порядок не повторяет занятые смыслом
    // цвета: иначе «На приёмке» выходила чернильной, как «Завершена».
    const meant = labels.map((label) => {
        const hit = MEANING.find(([re]) => re.test(label || ""));
        return hit ? c[hit[1]] : null;
    });
    const used = new Set(meant.filter(Boolean));
    const all = [c.ink, c.teal, c.gold, c.slateLight, c.slate, c.lineStrong];
    const free = all.filter((color) => !used.has(color));
    const order = free.length ? free : all;
    let next = 0;
    return meant.map((color) => color || order[next++ % order.length]);
}

function withAlpha(color, alpha) {
    const m = /^#([0-9a-f]{6})$/i.exec(color);
    if (!m) {
        return color;
    }
    const n = parseInt(m[1], 16);
    return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

patch(GraphRenderer.prototype, {
    getBarChartData() {
        const data = super.getBarChartData(...arguments);
        const c = tokens();
        const series = data.datasets.filter((d) => d.type !== "line");
        const colors = seriesColors(series.map((d) => d.label), c);
        series.forEach((d, i) => {
            d.backgroundColor = colors[i];
            d.hoverBackgroundColor = colors[i];
            d.borderRadius = 2;
            d.maxBarThickness = 28;
        });
        for (const d of data.datasets.filter((d) => d.type === "line")) {
            // Линия итога поверх столбцов — пунктир, как тренд в эталоне.
            Object.assign(d, {
                borderColor: c.slateLight,
                backgroundColor: c.slate,
                borderDash: [4, 4],
                borderWidth: 1.5,
                pointRadius: 3,
                pointHoverRadius: 5,
            });
        }
        return data;
    },

    getLineChartData() {
        const data = super.getLineChartData(...arguments);
        const c = tokens();
        const colors = seriesColors(data.datasets.map((d) => d.label), c);
        data.datasets.forEach((d, i) => {
            d.borderColor = colors[i];
            d.pointBackgroundColor = colors[i];
            d.hoverBackgroundColor = colors[i];
            d.backgroundColor = withAlpha(colors[i], 0.08);
            d.borderWidth = 2;
            d.pointRadius = 2;
        });
        return data;
    },

    getPieChartData() {
        const data = super.getPieChartData(...arguments);
        const c = tokens();
        const colors = seriesColors(data.labels || [], c);
        for (const d of data.datasets) {
            if (Array.isArray(d.backgroundColor)) {
                d.backgroundColor = d.backgroundColor.map((_, i) => colors[i % colors.length]);
            }
        }
        return data;
    },

    getScaleOptions() {
        const scales = super.getScaleOptions(...arguments);
        const c = tokens();
        for (const [axis, scale] of Object.entries(scales)) {
            scale.ticks = {
                ...scale.ticks,
                color: c.slate,
                font: { family: MONO, size: 11 },
            };
            if (axis === "x" && scale.ticks.callback) {
                const label = scale.ticks.callback;
                scale.ticks.callback = (...args) => {
                    const value = label(...args);
                    return typeof value === "string" ? value.toUpperCase() : value;
                };
            }
            if (scale.grid && scale.grid.color !== "transparent") {
                scale.grid = { ...scale.grid, color: c.line };
            }
            if (scale.title) {
                scale.title = { ...scale.title, color: c.slate, font: { family: MONO, size: 11 } };
            }
        }
        return scales;
    },

    getLegendOptions() {
        const legend = super.getLegendOptions(...arguments);
        const c = tokens();
        legend.labels = {
            ...(legend.labels || {}),
            color: c.slate,
            font: { family: MONO, size: 11 },
        };
        return legend;
    },
});
