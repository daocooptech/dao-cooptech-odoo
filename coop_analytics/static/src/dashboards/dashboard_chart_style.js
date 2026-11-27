/** @odoo-module **/

import { components } from "@odoo/o-spreadsheet";
import { patch } from "@web/core/utils/patch";

/**
 * Графики дашбордов — в цветах дизайн-системы (владелец 27.11.2026: «и
 * графики по дизайн системе»).
 *
 * Правило системы (BlockChart, AnalyticsDealsPage): данные чернильные, цвет
 * — только смыслом. Завершена — чернильный, исполняется — `coop-teal`,
 * переговоры — `coop-gold`, спор и просрочка — `coop-error`, отменена —
 * `coop-line-strong`. Подписи осей и расшифровка — моноширинным.
 *
 * Цвета — светлые токены системы; тёмную тему делает фильтр движка.
 */
const TONE_BY_LABEL = [
    // «Ещё не завершена» — не «завершена»: отрицание проверяется первым.
    [/(^|\s)(ещё |еще )?не /i, "line-strong"],
    [/доволь|хорош/i, "teal"],
    [/разошл/i, "gold"],
    [/заверш|выполнен|оплачен|проведен/i, "ink"],
    [/исполня|в работе|активн|действу/i, "teal"],
    [/приёмк|приемк/i, "teal-dark"],
    [/перегов|обращени|ожида|заявлен|черновик/i, "gold"],
    [/спор|просроч|ошибк|отклон/i, "error"],
    [/отмен|закрыт|возвращ/i, "line-strong"],
    [/согласован/i, "slate-light"],
];
// Красный в ряду не участвует: он только про просрочку и спор.
const PALETTE = ["ink", "teal", "gold", "slate-light", "line-strong", "teal-dark", "slate"];
const MONO = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

// Токены текущей темы. В тёмной теме движок пропускал графики через
// фильтр (инверсия с поворотом оттенка) — охра становилась оранжевой,
// красный розовым; с графиков фильтр снят (coop_analytics.scss), и они
// рисуются прямо тёмными токенами системы.
const FALLBACK = {
    ink: "#14171a",
    slate: "#4a4a44",
    "slate-light": "#8f8f88",
    line: "#e6e6e1",
    "line-strong": "#d2d2cb",
    teal: "#146b64",
    "teal-dark": "#0e4f4a",
    gold: "#c98a2b",
    error: "#b3413a",
    white: "#ffffff",
};

function tokens() {
    const style = getComputedStyle(document.querySelector(".o_web_client") || document.documentElement);
    const out = {};
    for (const [name, fallback] of Object.entries(FALLBACK)) {
        out[name] = style.getPropertyValue(`--coop-${name}`).trim() || fallback;
    }
    return out;
}

function upper(scale) {
    // Подписи категорий — прописными, как в BlockChart.
    const own = scale.ticks?.callback;
    scale.ticks.callback = function (value, index, ticks) {
        const text = own ? own.call(this, value, index, ticks) : this.getLabelForValue(value);
        return typeof text === "string" ? text.toUpperCase() : text;
    };
}

// Подпись без смыслового цвета получает следующий цвет ряда и держит его
// на всех графиках экрана: «Перевод участнику» в столбцах и в круге —
// одного цвета.
const assigned = new Map();

function toneFor(label) {
    for (const [re, tone] of TONE_BY_LABEL) {
        if (re.test(label || "")) {
            return tone;
        }
    }
    const key = String(label || "");
    if (!assigned.has(key)) {
        assigned.set(key, PALETTE[assigned.size % PALETTE.length]);
    }
    return assigned.get(key);
}

function restyle(config) {
    const t = tokens();
    const datasets = config.data?.datasets || [];
    const labels = config.data?.labels || [];
    const pie = ["pie", "doughnut"].includes(config.type);
    datasets.forEach((ds) => {
        if (pie || (datasets.length === 1 && config.type === "bar")) {
            // Одна серия — столбцы или доли по подписям оси: цвет по смыслу
            // подписи, иначе — чернильный (у столбцов) или ряд палитры.
            const colors = labels.map((label) => {
                const known = TONE_BY_LABEL.some(([re]) => re.test(label || ""));
                return t[known || pie ? toneFor(label) : "ink"];
            });
            if (pie) {
                // Две доли одного цвета не различить: повтор — следующим
                // свободным цветом ряда.
                const used = new Set();
                colors.forEach((color, j) => {
                    if (used.has(color)) {
                        const free = PALETTE.map((tone) => t[tone]).find((c) => !used.has(c));
                        colors[j] = free || color;
                    }
                    used.add(colors[j]);
                });
            }
            ds.backgroundColor = colors;
            ds.borderColor = pie ? t.white : colors;
        } else {
            // Одна серия («Сумма», «Остаток») — просто данные, чернильным.
            const color = t[datasets.length === 1 ? "ink" : toneFor(ds.label)];
            ds.backgroundColor = config.type === "line" ? `${color}14` : color;
            ds.borderWidth = config.type === "line" ? 1.5 : 0;
            ds.pointRadius = config.type === "line" ? 2 : ds.pointRadius;
            ds.borderColor = color;
            ds.pointBackgroundColor = color;
        }
        if (config.type === "bar") {
            // Столбик показывает величину, а не занимает площадь (BarChart):
            // тонкий, между столбиками — воздух.
            ds.maxBarThickness = 10;
            ds.borderWidth = 0;
            ds.borderRadius = 0;
        }
    });
    const options = config.options || (config.options = {});
    const tick = { color: t["slate-light"], font: { family: MONO, size: 10 } };
    for (const [axis, scale] of Object.entries(options.scales || {})) {
        scale.ticks = { ...(scale.ticks || {}), ...tick };
        // Линейки — только поперёк значений и бледные; вдоль категорий нет.
        const across = axis.startsWith("y");
        scale.grid = { ...(scale.grid || {}), display: across, color: t.line, drawTicks: false };
        scale.border = { ...(scale.border || {}), display: !across, color: t["line-strong"] };
        if (!across) {
            upper(scale);
        }
    }
    const bg = options.plugins?.background;
    if (bg && typeof bg === "object") {
        bg.color = t.white;
    }
    const legend = options.plugins?.legend;
    if (legend) {
        const labelsOptions = { ...(legend.labels || {}) };
        // Расшифровку движок строит со своими цветами — чёрный текст, у
        // круга и цвета долей мимо набора данных. Без неё Chart.js берёт
        // цвета серий и `labels.color` — уже наши.
        delete labelsOptions.generateLabels;
        legend.labels = {
            ...labelsOptions,
            color: t.slate,
            font: { family: MONO, size: 10 },
            boxWidth: 8,
            boxHeight: 8,
        };
    }
    return config;
}

patch(components.ChartJsComponent.prototype, {
    createChart(chartData) {
        if (this.env.model.getters.isDashboard() && chartData?.chartJsConfig) {
            restyle(chartData.chartJsConfig);
        }
        super.createChart(chartData);
    },
    updateChartJs(chartData) {
        if (this.env.model.getters.isDashboard() && chartData?.chartJsConfig) {
            restyle(chartData.chartJsConfig);
        }
        super.updateChartJs(chartData);
    },
});
