/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Экран DEX биржи (решение 417): пары слева, справа — свечи по дням,
 * стакан, форма заявки и последние сделки. Заявка сводится со встречными
 * сразу; исполнение — обмен, в котором рубли переводит одна сторона
 * другой, а монету — другая первой, и обе подтверждают.
 *
 * Своей библиотеки графиков не подключаем: свечи — прямоугольники SVG.
 */
export class CoopDexTerminal extends Component {
    static template = "coop_crypto_exchange.DexTerminal";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            markets: [],
            current: null,
            book: null,
            side: "buy",
            orderType: "limit",
            price: 0,
            amount: 0,
            methods: { sbp: true, bank: true, cash: false },
        });
        onWillStart(async () => {
            await this.loadMarkets();
            if (this.state.markets.length) {
                await this.select(this.state.markets[0]);
            }
        });
    }

    async loadMarkets() {
        this.state.markets = await this.orm.call("coop.crypto.market", "markets", []);
    }

    async select(market) {
        this.state.current = market;
        this.state.book = await this.orm.call("coop.crypto.market", "book",
            [market.asset, market.network_id]);
        this.state.price = this.state.side === "buy"
            ? (this.state.book.best_ask || market.last) : (this.state.book.best_bid || market.last);
    }

    pick(row, isAsk) {
        if (row.mine) {
            this.notification.add("Это ваша собственная заявка.", { type: "warning" });
            return;
        }
        this.state.side = isAsk ? "buy" : "sell";
        this.state.orderType = "limit";
        this.state.price = row.price;
        this.state.amount = row.amount;
    }

    setSide(side) { this.state.side = side; }
    setType(type) { this.state.orderType = type; }
    toggleMethod(m) { this.state.methods[m] = !this.state.methods[m]; }

    onNum(key, ev) {
        const value = parseFloat(String(ev.target.value).replace(",", "."));
        this.state[key] = isNaN(value) ? 0 : value;
    }

    get marketPrice() {
        const b = this.state.book || {};
        return this.state.side === "buy" ? b.best_ask : b.best_bid;
    }

    get total() {
        const price = this.state.orderType === "market" ? this.marketPrice : this.state.price;
        return (this.state.amount || 0) * (price || 0);
    }

    get canTrade() {
        const price = this.state.orderType === "market" ? this.marketPrice : this.state.price;
        const anyMethod = Object.values(this.state.methods).some(Boolean);
        return this.state.current && this.state.amount > 0 && price > 0 && anyMethod;
    }

    async placeOrder() {
        if (!this.canTrade) {
            return;
        }
        const m = this.state.current;
        try {
            const methods = Object.keys(this.state.methods).filter((k) => this.state.methods[k]);
            const res = await this.orm.call("coop.crypto.market", "place_order", [
                m.asset, m.network_id, this.state.side, this.state.orderType,
                this.state.amount, this.state.orderType === "limit" ? this.state.price : false,
                methods,
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
            await this.loadMarkets();
            await this.select(this.state.markets.find((x) => x.key === m.key) || m);
        } catch (error) {
            this.notification.add(error.data?.message || String(error), { type: "danger" });
        }
    }

    async cancelMine(row) {
        await this.orm.call("coop.crypto.offer", "action_close", [[row.id]]);
        await this.select(this.state.current);
    }

    openTrades() {
        this.action.doAction("coop_crypto_exchange.action_coop_crypto_trade");
    }

    openNode() {
        this.action.doAction("coop_crypto_exchange.action_coop_komodo_node");
    }

    // ── Числа и график ──────────────────────────────────────────────

    rub(v) {
        return (v || 0).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " ₽";
    }
    qty(v) {
        return (v || 0).toLocaleString("ru-RU", { maximumFractionDigits: 8 });
    }
    pct(v) {
        const n = (v || 0).toFixed(2);
        return v > 0 ? `+${n}%` : `${n}%`;
    }
    depth(row, rows) {
        const max = Math.max(...rows.map((r) => r.amount), 0.00000001);
        return `${Math.max((row.amount / max) * 100, 4)}%`;
    }

    get candles() {
        return (this.state.book && this.state.book.candles) || [];
    }
    get candleRange() {
        const c = this.candles;
        if (!c.length) {
            return { min: 0, max: 0 };
        }
        return { min: Math.min(...c.map((x) => x.l)), max: Math.max(...c.map((x) => x.h)) };
    }
    get candleBars() {
        const c = this.candles;
        const { min, max } = this.candleRange;
        const span = max - min || 1;
        const step = 100 / Math.max(c.length, 1);
        const y = (v) => 95 - ((v - min) / span) * 90;
        return c.map((x, i) => {
            const top = y(Math.max(x.o, x.c));
            const bottom = y(Math.min(x.o, x.c));
            return {
                day: x.day, x: step * i + step / 2, w: Math.max(step * 0.6, 0.4),
                yh: y(x.h), yl: y(x.l), yt: top, hh: Math.max(bottom - top, 0.6), up: x.c >= x.o,
            };
        });
    }
}

registry.category("actions").add("coop_crypto_exchange.terminal", CoopDexTerminal);
