/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Экран DEX биржи (решение 417; владелец 26.09 — «сделай современную
 * биржу»). Раскладка терминала: сверху пара и сводка за сутки; в середине
 * график (свечи с объёмом или глубина стакана), справа стакан — продажи
 * сверху, спред, покупки снизу, — и лента сделок; под графиком две формы
 * рядом, «купить» и «продать»; внизу — мои открытые заявки, история заявок
 * и мои сделки.
 *
 * Заявка сводится со встречными сразу; исполнение — обмен, в котором рубли
 * переводит одна сторона другой, а монету — другая первой.
 *
 * Своей библиотеки графиков не подключаем: свечи и глубина — SVG.
 */

const RANGES = [
    { key: "7", label: "7д", days: 7 },
    { key: "30", label: "1м", days: 30 },
    { key: "90", label: "3м", days: 90 },
    { key: "all", label: "Всё", days: 0 },
];
const BOOK_ROWS = 14;

export class CoopDexTerminal extends Component {
    static template = "coop_crypto_exchange.DexTerminal";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.ranges = RANGES;
        this.state = useState({
            markets: [],
            current: null,
            book: null,
            pickerOpen: false,
            pairQuery: "",
            chart: "candles",
            range: "90",
            bookView: "both",
            orderType: "limit",
            buy: { price: 0, amount: 0 },
            sell: { price: 0, amount: 0 },
            methods: { sbp: true, bank: true, cash: false },
            bottom: "open",
            busy: false,
        });
        onWillStart(async () => {
            await this.loadMarkets();
            if (this.state.markets.length) {
                await this.select(this.state.markets[0]);
            }
        });
    }

    // ── Данные ──────────────────────────────────────────────────────

    async loadMarkets() {
        this.state.markets = await this.orm.call("coop.crypto.market", "markets", []);
    }

    async select(market) {
        this.state.current = market;
        this.state.pickerOpen = false;
        this.state.pairQuery = "";
        this.state.book = await this.orm.call("coop.crypto.market", "book",
            [market.asset, market.network_id]);
        const b = this.state.book;
        this.state.buy.price = b.best_ask || market.last;
        this.state.sell.price = b.best_bid || market.last;
    }

    async refresh() {
        const key = this.state.current && this.state.current.key;
        await this.loadMarkets();
        const market = this.state.markets.find((m) => m.key === key) || this.state.markets[0];
        if (market) {
            const keep = { buy: { ...this.state.buy }, sell: { ...this.state.sell } };
            await this.select(market);
            Object.assign(this.state.buy, keep.buy);
            Object.assign(this.state.sell, keep.sell);
        }
    }

    // ── Пара ────────────────────────────────────────────────────────

    togglePicker() {
        this.state.pickerOpen = !this.state.pickerOpen;
    }

    onPairQuery(ev) {
        this.state.pairQuery = ev.target.value;
    }

    get pairs() {
        const q = this.state.pairQuery.trim().toLowerCase();
        return q ? this.state.markets.filter((m) => m.label.toLowerCase().includes(q)) : this.state.markets;
    }

    // ── Стакан ──────────────────────────────────────────────────────

    get asksShown() {
        const rows = (this.state.book && this.state.book.asks) || [];
        const n = this.state.bookView === "asks" ? BOOK_ROWS * 2 : BOOK_ROWS;
        return this.withCum(rows.slice(0, n)).reverse();
    }

    get bidsShown() {
        const rows = (this.state.book && this.state.book.bids) || [];
        const n = this.state.bookView === "bids" ? BOOK_ROWS * 2 : BOOK_ROWS;
        return this.withCum(rows.slice(0, n));
    }

    withCum(rows) {
        let cum = 0;
        const max = rows.reduce((s, r) => s + r.amount, 0) || 1;
        return rows.map((r) => {
            cum += r.amount;
            return { ...r, cum, depth: `${Math.max((cum / max) * 100, 2)}%` };
        });
    }

    get spread() {
        const b = this.state.book || {};
        if (!b.best_ask || !b.best_bid) {
            return null;
        }
        const abs = b.best_ask - b.best_bid;
        return { abs, pct: (abs / b.best_ask) * 100 };
    }

    get lastUp() {
        const t = (this.state.book && this.state.book.trades) || [];
        return t.length < 2 || t[0].price >= t[1].price;
    }

    setBookView(view) {
        this.state.bookView = view;
    }

    pick(row, isAsk) {
        if (row.mine) {
            this.notification.add("Это ваша собственная заявка.", { type: "warning" });
            return;
        }
        // Щелчок по продаже — купить по её цене весь объём до этой строки.
        const side = isAsk ? "buy" : "sell";
        this.state.orderType = "limit";
        this.state[side].price = row.price;
        this.state[side].amount = Number(row.cum.toFixed(8));
    }

    // ── Формы ───────────────────────────────────────────────────────

    setType(type) {
        this.state.orderType = type;
    }

    toggleMethod(m) {
        this.state.methods[m] = !this.state.methods[m];
    }

    onNum(side, key, ev) {
        const value = parseFloat(String(ev.target.value).replace(",", "."));
        this.state[side][key] = isNaN(value) ? 0 : value;
    }

    marketPrice(side) {
        const b = this.state.book || {};
        return side === "buy" ? b.best_ask : b.best_bid;
    }

    priceFor(side) {
        return this.state.orderType === "market" ? this.marketPrice(side) : this.state[side].price;
    }

    total(side) {
        return (this.state[side].amount || 0) * (this.priceFor(side) || 0);
    }

    canTrade(side) {
        const anyMethod = Object.values(this.state.methods).some(Boolean);
        return !this.state.busy && this.state.current && this.state[side].amount > 0
            && this.priceFor(side) > 0 && anyMethod;
    }

    async placeOrder(side) {
        if (!this.canTrade(side)) {
            return;
        }
        const m = this.state.current;
        this.state.busy = true;
        try {
            const methods = Object.keys(this.state.methods).filter((k) => this.state.methods[k]);
            const res = await this.orm.call("coop.crypto.market", "place_order", [
                m.asset, m.network_id, side, this.state.orderType, this.state[side].amount,
                this.state.orderType === "limit" ? this.state[side].price : false, methods,
            ]);
            let text;
            if (res.filled > 0 && res.left > 0) {
                text = `Исполнено ${this.qty(res.filled)} ${m.asset}, остаток ждёт в стакане. Обмены — в «Мои обмены».`;
            } else if (res.filled > 0) {
                text = `Исполнено ${this.qty(res.filled)} ${m.asset}. Обмены — в «Мои обмены»: переведите и подтвердите.`;
            } else if (res.state === "closed") {
                text = "Встречных заявок с общим способом расчёта нет — заявка по рынку снята.";
            } else {
                text = "Заявка выставлена в стакан и ждёт встречной.";
            }
            this.notification.add(text, { type: res.filled > 0 ? "success" : "info" });
            this.state[side].amount = 0;
            this.state.bottom = res.left > 0 ? "open" : "trades";
            await this.refresh();
        } catch (error) {
            this.notification.add(error.data?.message || String(error), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    async cancelMine(row) {
        await this.orm.call("coop.crypto.offer", "action_close", [[row.id]]);
        await this.refresh();
    }

    setBottom(tab) {
        this.state.bottom = tab;
    }

    // ── Переходы ────────────────────────────────────────────────────

    openTrades() {
        this.action.doAction("coop_crypto_exchange.action_coop_crypto_trade");
    }

    openFarm() {
        this.action.doAction("coop_crypto_exchange.action_coop_farm");
    }

    openNode() {
        this.action.doAction("coop_crypto_exchange.action_coop_komodo_node");
    }

    // ── Числа ───────────────────────────────────────────────────────

    rub(v) {
        return (v || 0).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " ₽";
    }
    num(v) {
        return (v || 0).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    qty(v) {
        return (v || 0).toLocaleString("ru-RU", { maximumFractionDigits: 6 });
    }
    big(v) {
        const n = v || 0;
        if (n >= 1e9) {
            return (n / 1e9).toLocaleString("ru-RU", { maximumFractionDigits: 2 }) + " млрд";
        }
        if (n >= 1e6) {
            return (n / 1e6).toLocaleString("ru-RU", { maximumFractionDigits: 2 }) + " млн";
        }
        return n.toLocaleString("ru-RU", { maximumFractionDigits: 0 });
    }
    pct(v) {
        const n = (v || 0).toFixed(2);
        return v > 0 ? `+${n}%` : `${n}%`;
    }
    time(when) {
        return (when || "").slice(11, 16);
    }
    date(when) {
        const d = (when || "").slice(5, 16);
        return d.slice(3, 5) + "." + d.slice(0, 2) + d.slice(5);
    }

    // ── График ──────────────────────────────────────────────────────

    setChart(kind) {
        this.state.chart = kind;
    }

    setRange(key) {
        this.state.range = key;
    }

    get candles() {
        const all = (this.state.book && this.state.book.candles) || [];
        const range = RANGES.find((r) => r.key === this.state.range);
        return range && range.days ? all.slice(-range.days) : all;
    }

    get candleRange() {
        const c = this.candles;
        if (!c.length) {
            return { min: 0, max: 0 };
        }
        const min = Math.min(...c.map((x) => x.l));
        const max = Math.max(...c.map((x) => x.h));
        const pad = (max - min) * 0.06 || max * 0.01;
        return { min: min - pad, max: max + pad };
    }

    get priceTicks() {
        const { min, max } = this.candleRange;
        const ticks = [];
        for (let i = 0; i <= 4; i++) {
            ticks.push({ v: max - ((max - min) * i) / 4, top: `${4 + i * 17.5}%` });
        }
        return ticks;
    }

    get candleBars() {
        const c = this.candles;
        const { min, max } = this.candleRange;
        const span = max - min || 1;
        const step = 100 / Math.max(c.length, 1);
        // Цены — верхние 74% высоты, объём — нижние 20%.
        const y = (v) => 4 + (1 - (v - min) / span) * 70;
        const vmax = Math.max(...c.map((x) => x.v), 0.00000001);
        return c.map((x, i) => {
            const top = y(Math.max(x.o, x.c));
            const bottom = y(Math.min(x.o, x.c));
            const vh = (x.v / vmax) * 20;
            return {
                day: x.day, x: step * i + step / 2, w: Math.max(step * 0.62, 0.35),
                yh: y(x.h), yl: y(x.l), yt: top, hh: Math.max(bottom - top, 0.5),
                up: x.c >= x.o, vy: 100 - vh, vh,
            };
        });
    }

    get dayLabels() {
        const c = this.candles;
        if (c.length < 2) {
            return [];
        }
        const out = [];
        const n = 5;
        for (let i = 0; i < n; i++) {
            const idx = Math.round(((c.length - 1) * i) / (n - 1));
            const d = c[idx].day;
            out.push({ left: `${((idx + 0.5) / c.length) * 100}%`, label: `${d.slice(8, 10)}.${d.slice(5, 7)}` });
        }
        return out;
    }

    get depth() {
        const b = this.state.book || {};
        const bids = b.bids || [];
        const asks = b.asks || [];
        if (!bids.length && !asks.length) {
            return null;
        }
        const cum = (rows) => {
            let s = 0;
            return rows.map((r) => ({ p: r.price, c: (s += r.amount) }));
        };
        const cb = cum(bids);
        const ca = cum(asks);
        const lo = bids.length ? bids[bids.length - 1].price : asks[0].price;
        const hi = asks.length ? asks[asks.length - 1].price : bids[0].price;
        const span = hi - lo || 1;
        const cmax = Math.max(cb.length ? cb[cb.length - 1].c : 0, ca.length ? ca[ca.length - 1].c : 0) || 1;
        const x = (p) => ((p - lo) / span) * 100;
        const y = (c) => 96 - (c / cmax) * 88;
        const path = (points, close) => {
            if (!points.length) {
                return "";
            }
            let d = `M ${x(points[0].p)} 96`;
            for (const pt of points) {
                d += ` L ${x(pt.p)} ${y(pt.c)}`;
            }
            return d + ` L ${close} ${y(points[points.length - 1].c)} L ${close} 96 Z`;
        };
        return {
            bids: path(cb, 0), asks: path(ca, 100), lo, hi,
            mid: b.best_ask && b.best_bid ? (b.best_ask + b.best_bid) / 2 : 0,
            bidTotal: cb.length ? cb[cb.length - 1].c : 0,
            askTotal: ca.length ? ca[ca.length - 1].c : 0,
        };
    }
}

registry.category("actions").add("coop_crypto_exchange.terminal", CoopDexTerminal);
