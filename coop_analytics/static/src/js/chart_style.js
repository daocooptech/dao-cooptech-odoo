/** @odoo-module **/


/**
 * Графики платформы — как графики дизайн-системы (владелец 27.11.2026:
 * «сделай все графики как в дизайн системе»).
 *
 * Дашборды (таблица движка) и вид «График» рисуют через Chart.js, а
 * система рисует свои графики сама. Здесь Chart.js доводится до образцов
 * системы:
 *   - столбцы без отрицательных значений — BlockChart: столбец из
 *     квадратных клеток, пустые клетки видны и дают сетку;
 *   - столбцы со знаком (приход вверх, расход вниз) — BarChart: тонкий
 *     столбик в 5 точек;
 *   - линии — LineChart: плавная линия 1,75, план и тренд пунктиром,
 *     под главной линией штриховка;
 *   - круга в системе нет — на дашбордах доли рисуются столбцами из
 *     клеток; в виде «График» круг человек выбирает сам — он остаётся,
 *     в цветах системы.
 * Цвет — только смыслом (завершена — чернильный, исполняется —
 * `coop-teal`, переговоры — `coop-gold`, спор — `coop-error`,
 * отменена — `coop-line-strong`); подписи — моноширинным, прописными.
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
const DASHED = /план|тренд|прогноз|средн/i;
const MONO = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

// Токены текущей темы. Фильтр тёмной темы движка с графиков снят
// (coop_analytics.scss) — они рисуются прямо тёмными токенами системы.
const FALLBACK = {
    ink: "#14171a",
    slate: "#4a4a44",
    "slate-light": "#8f8f88",
    line: "#e6e6e1",
    "line-strong": "#d2d2cb",
    surface: "#f2f2ee",
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

// Подпись без смыслового цвета получает следующий цвет ряда и держит его
// на всех графиках экрана.
const assigned = new Map();

export function toneFor(label) {
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

function known(label) {
    return TONE_BY_LABEL.some(([re]) => re.test(label || ""));
}

function upper(scale) {
    const own = scale.ticks?.callback;
    scale.ticks.callback = function (value, index, ticks) {
        const text = own ? own.call(this, value, index, ticks) : this.getLabelForValue(value);
        return typeof text === "string" ? text.toUpperCase() : text;
    };
}

// ── BlockChart: столбцы из клеток ────────────────────────────────────
// Клетка — квадрат 6–22 точки, между клетками 2 точки по высоте; шаг
// клетки равен шагу шкалы, поэтому подписи слева совпадают с клетками.
function blockPlugin(t) {
    return {
        id: "coopBlocks",
        beforeDatasetsDraw(chart) {
            const { ctx, chartArea: area, scales } = chart;
            const x = scales.x;
            const y = scales.y;
            const n = chart.data.labels?.length || 0;
            // Знак проверяется при рисовании: при создании графика данных
            // ещё нет. Есть минус — это BarChart, рисует сам Chart.js.
            if (!x || !y || !n || chart.data.datasets.some((ds) => values(ds).some((v) => v < 0))) {
                return true;
            }
            const slot = x.width / n;
            // Клетка — почти во всю ширину столбца, как в образце: сетка
            // плотная, между столбцами 3 точки.
            const want = Math.max(6, Math.min(22, Math.floor(slot - 3)));
            const rows = Math.max(6, Math.round(area.height / (want + 2)));
            const pitch = area.height / rows;
            const cell = Math.max(3, Math.min(pitch - 2, slot - 3));
            const unit = (y.max - Math.max(0, y.min)) / rows || 1;
            ctx.save();
            for (let i = 0; i < n; i++) {
                const x0 = Math.round(x.getPixelForValue(i) - cell / 2);
                // Клеток в столбце — по его сумме (ненулевой столбец — хотя бы
                // одна клетка); между частями они делятся по долям, остаток —
                // самым крупным остаткам. Так мелкие части не раздувают столбец.
                const parts = [];
                chart.data.datasets.forEach((ds, di) => {
                    if (!chart.isDatasetVisible(di) || ds.type === "line") {
                        return;
                    }
                    const raw = ds.data[i];
                    const v = typeof raw === "object" && raw ? raw.y : raw;
                    if (v > 0) {
                        const color = Array.isArray(ds.backgroundColor) ? ds.backgroundColor[i] : ds.backgroundColor;
                        parts.push({ v, color });
                    }
                });
                const total = parts.reduce((sum, p) => sum + p.v, 0);
                const cells = total > 0 ? Math.min(rows, Math.max(1, Math.round(total / unit))) : 0;
                parts.forEach((p) => {
                    const exact = (p.v / total) * cells;
                    p.n = Math.floor(exact);
                    p.rest = exact - p.n;
                });
                let left = cells - parts.reduce((sum, p) => sum + p.n, 0);
                [...parts].sort((a, b) => b.rest - a.rest).forEach((p) => {
                    if (left > 0) {
                        p.n += 1;
                        left -= 1;
                    }
                });
                const fills = [];
                for (const p of parts) {
                    for (let k = 0; k < p.n; k++) {
                        fills.push(p.color);
                    }
                }
                for (let r = 0; r < rows; r++) {
                    const top = Math.round(area.bottom - (r + 1) * pitch + (pitch - cell));
                    ctx.fillStyle = fills[r] || t.surface;
                    ctx.fillRect(x0, top, Math.round(cell), Math.round(cell));
                }
            }
            ctx.restore();
            return true;
        },
        // Столбцы уже нарисованы клетками; линии поверх них (итог «Сумма»
        // при накоплении) рисует сам Chart.js.
        beforeDatasetDraw(chart, args) {
            if (chart.data.datasets.some((ds) => values(ds).some((v) => v < 0))) {
                return true;
            }
            return args.meta.type === "line";
        },
    };
}

// ── LineChart: штриховка под главной линией ──────────────────────────
function hatch(color) {
    const size = 6;
    const c = document.createElement("canvas");
    c.width = c.height = size;
    const g = c.getContext("2d");
    g.strokeStyle = color;
    g.lineWidth = 1;
    g.beginPath();
    g.moveTo(0, size);
    g.lineTo(size, 0);
    g.stroke();
    return g.createPattern(c, "repeat");
}

function values(ds) {
    return (ds.data || []).map((v) => (typeof v === "object" && v ? v.y : v)).filter((v) => typeof v === "number");
}

function pieToBlocks(config) {
    // Круга в системе нет: доли — столбцами из клеток, подпись — под столбцом.
    config.type = "bar";
    const options = config.options || (config.options = {});
    delete options.cutout;
    delete options.rotation;
    delete options.circumference;
    options.indexAxis = "x";
    options.scales = { x: { type: "category" }, y: { type: "linear", beginAtZero: true } };
    options.plugins = options.plugins || {};
    delete options.plugins.chartShowValuesPlugin;
    options.plugins.legend = { ...(options.plugins.legend || {}), display: false };
    options.plugins.tooltip = {
        ...(options.plugins.tooltip || {}),
        callbacks: { label: (c) => `${c.label}: ${c.formattedValue}` },
    };
    config.data.datasets = (config.data.datasets || []).slice(0, 1);
}

// Оформляются только столбцы, линии и круг. Карту, плитки, воронку и
// прочие типы движка не трогаем: у них свои шкалы и данные, и правка
// роняла дашборд («Выставление счетов», карта — object is not extensible).
const STYLED = ["bar", "line", "pie", "doughnut"];

export function restyle(config, { pieToBars = false } = {}) {
    if (!config || !STYLED.includes(config.type)) {
        return config;
    }
    const t = tokens();
    const pie = ["pie", "doughnut"].includes(config.type);
    if (pie && pieToBars) {
        pieToBlocks(config);
    }
    const datasets = config.data?.datasets || [];
    const labels = config.data?.labels || [];
    const bar = config.type === "bar";
    const line = config.type === "line";
    const signed = bar && datasets.some((ds) => values(ds).some((v) => v < 0));
    const blocks = bar && !signed;

    const barSets = datasets.filter((ds) => ds.type !== "line");
    datasets.forEach((ds, di) => {
        if (bar && ds.type === "line") {
            // Итог поверх столбцов — тонкая чернильная линия.
            ds.borderColor = t.ink;
            ds.backgroundColor = t.ink;
            ds.borderWidth = 1.75;
            ds.tension = 0.4;
            ds.pointRadius = 0;
            ds.pointHoverRadius = 3;
            ds.fill = false;
            return;
        }
        if (["pie", "doughnut"].includes(config.type)) {
            const colors = labels.map((label) => t[toneFor(label)]);
            ds.backgroundColor = colors;
            ds.borderColor = t.white;
            return;
        }
        if (bar && barSets.length === 1) {
            // Одна серия — цвет по смыслу подписи столбца, иначе чернильный.
            ds.backgroundColor = labels.map((label) => t[known(label) ? toneFor(label) : "ink"]);
            ds.borderColor = ds.backgroundColor;
        } else {
            const color = t[(bar ? barSets : datasets).length === 1 ? "ink" : toneFor(ds.label)];
            ds.backgroundColor = color;
            ds.borderColor = color;
            ds.pointBackgroundColor = color;
        }
        if (bar) {
            ds.borderWidth = 0;
            ds.borderRadius = 0;
            // BarChart: тонкий столбик, вниз — встречный поток.
            ds.maxBarThickness = signed ? 5 : 16;
        }
        if (line) {
            const dashed = DASHED.test(ds.label || "");
            ds.tension = 0.4;
            ds.borderWidth = 1.75;
            ds.borderDash = dashed ? [5, 4] : [];
            ds.pointRadius = 0;
            ds.pointHoverRadius = 3;
            // Штриховка — у одного, главного ряда.
            ds.fill = di === 0 && !dashed ? "origin" : false;
            ds.backgroundColor = di === 0 && !dashed ? hatch(t["line-strong"]) : "transparent";
        }
    });

    const options = config.options || (config.options = {});
    const tick = { color: t["slate-light"], font: { family: MONO, size: 10 } };
    for (const [axis, scale] of Object.entries(options.scales || {})) {
        scale.ticks = { ...(scale.ticks || {}), ...tick };
        const across = axis.startsWith("y");
        scale.grid = {
            ...(scale.grid || {}),
            // У клеток своя сетка — пустые клетки; линейки не нужны.
            display: across && !blocks,
            drawTicks: false,
            color: (c) => (c.tick?.value === 0 ? t["line-strong"] : t.line),
        };
        scale.border = { ...(scale.border || {}), display: false };
        if (!across) {
            upper(scale);
        }
    }
    if (bar) {
        config.plugins = [...(config.plugins || []).filter((p) => p.id !== "coopBlocks"), blockPlugin(t)];
    }
    const bg = options.plugins?.background;
    if (bg && typeof bg === "object") {
        bg.color = t.white;
    }
    const legend = options.plugins?.legend;
    if (legend) {
        // Расшифровка — квадратики и прописные моноширинным, как `keys` у
        // графиков системы. Свою расшифровку движка (чёрный текст, у круга
        // — его цвета) заменяет штатная Chart.js.
        const labelsOptions = { ...(legend.labels || {}) };
        delete labelsOptions.generateLabels;
        // Расшифровка — над графиком, словами, слева (образец «Сделки»).
        legend.position = "top";
        legend.align = "start";
        legend.labels = {
            ...labelsOptions,
            color: t.slate,
            font: { family: MONO, size: 10 },
            boxWidth: 8,
            boxHeight: 8,
            usePointStyle: false,
            generateLabels(chart) {
                const Chart = globalThis.Chart;
                const own = Chart.overrides?.[chart.config.type]?.plugins?.legend?.labels?.generateLabels;
                const base = (own || Chart.defaults.plugins.legend.labels.generateLabels)(chart);
                return base.map((item) => ({
                    ...item,
                    text: String(item.text || "").toUpperCase(),
                    fontColor: t.slate,
                    lineWidth: 0,
                    fillStyle: line ? item.strokeStyle : item.fillStyle,
                }));
            },
        };
    }
    return config;
}
