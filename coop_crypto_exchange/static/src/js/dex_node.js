/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Свой узел Komodo (решение 417, этап 5 плана биржи): страница-клиент к
 * Komodo DeFi Framework, запущенному на компьютере участника. Браузер
 * участника сам ходит на 127.0.0.1:7783 — сервер платформы в этом не
 * участвует и не видит ни пароля RPC, ни ключей, ни заявок узла. Пароль
 * хранится только в localStorage этого браузера.
 *
 * Методы — устаревший (legacy) JSON-RPC KDF, сверено с документацией
 * komodoplatform.com/en/docs/komodo-defi-framework/api/legacy/:
 * version, get_enabled_coins, electrum, my_balance, orderbook, buy, sell,
 * setprice, my_orders, cancel_order, my_recent_swaps. Ответ — либо
 * {result: …}, либо {error: "…"}; orderbook отвечает без обёртки result.
 *
 * Запрос уходит как text/plain — «простой» запрос без предварительного
 * OPTIONS; KDF отвечает заголовком Access-Control-Allow-Origin из
 * параметра rpccors в MM2.json.
 */

const KEY_URL = "coop_kdf_url";
const KEY_PASS = "coop_kdf_userpass";
const DEFAULT_URL = "http://127.0.0.1:7783";

function load(key, fallback) {
    try {
        return browser.localStorage.getItem(key) || fallback;
    } catch {
        return fallback;
    }
}

function save(key, value) {
    try {
        if (value) {
            browser.localStorage.setItem(key, value);
        } else {
            browser.localStorage.removeItem(key);
        }
    } catch {
        // Хранилище закрыто (приватное окно) — пароль живёт до перезагрузки.
    }
}

export class CoopKomodoNode extends Component {
    static template = "coop_crypto_exchange.KomodoNode";
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            url: load(KEY_URL, DEFAULT_URL),
            pass: load(KEY_PASS, ""),
            remember: !!load(KEY_PASS, ""),
            status: "idle", // idle | connecting | online | error
            error: "",
            version: "",
            coins: [],
            balances: {},
            base: "",
            rel: "",
            book: null,
            orders: [],
            swaps: [],
            side: "buy",
            mode: "take", // take — взять из стакана (buy/sell); make — выставить свою (setprice)
            price: "",
            volume: "",
            busy: false,
            activate: { coin: "", server: "" },
            showGuide: false,
        });
        onWillStart(async () => {
            if (this.state.pass) {
                await this.connect();
            } else {
                this.state.showGuide = true;
            }
        });
    }

    // ── Соединение ──────────────────────────────────────────────────

    get origin() {
        return browser.location.origin;
    }

    get secure() {
        return window.isSecureContext;
    }

    get mm2json() {
        return JSON.stringify({
            gui: "coop-dao",
            netid: 8762,
            rpcport: 7783,
            rpcip: "127.0.0.1",
            rpccors: this.origin,
            rpc_password: "придумайте-пароль-8-32-знака",
            seednodes: ["seed01.kmdefi.net", "seed02.kmdefi.net"],
            passphrase: "ваша фраза восстановления — только в этом файле",
        }, null, 2);
    }

    async rpc(method, params = {}) {
        let response;
        try {
            response = await fetch(this.state.url, {
                method: "POST",
                body: JSON.stringify({ userpass: this.state.pass, method, ...params }),
            });
        } catch {
            throw new Error(this.secure
                ? "Узел не отвечает: не запущен, другой адрес или порт, либо в rpccors не указан адрес платформы, либо браузер не разрешил доступ к локальной сети."
                : "Узел не отвечает. Платформа открыта по http, и Chrome с версии 142 такие запросы к 127.0.0.1 не пропускает — нужен https или другой браузер.");
        }
        let data;
        try {
            data = await response.json();
        } catch {
            throw new Error(`Узел ответил не JSON (код ${response.status}).`);
        }
        if (data.error) {
            throw new Error(typeof data.error === "string" ? data.error : JSON.stringify(data.error));
        }
        return data;
    }

    async connect() {
        this.state.status = "connecting";
        this.state.error = "";
        save(KEY_URL, this.state.url === DEFAULT_URL ? "" : this.state.url);
        save(KEY_PASS, this.state.remember ? this.state.pass : "");
        try {
            const v = await this.rpc("version");
            this.state.version = v.result;
            this.state.status = "online";
            this.state.showGuide = false;
            await this.refresh();
        } catch (error) {
            this.state.status = "error";
            this.state.error = error.message;
        }
    }

    forget() {
        save(KEY_PASS, "");
        save(KEY_URL, "");
        Object.assign(this.state, {
            pass: "", remember: false, url: DEFAULT_URL, status: "idle", version: "",
            coins: [], balances: {}, book: null, orders: [], swaps: [],
        });
    }

    onField(key, ev) {
        this.state[key] = ev.target.type === "checkbox" ? ev.target.checked : ev.target.value;
    }

    onActivate(key, ev) {
        this.state.activate[key] = ev.target.value.trim();
    }

    // ── Данные узла ─────────────────────────────────────────────────

    async refresh() {
        await this.loadCoins();
        await Promise.all([this.loadBook(), this.loadOrders(), this.loadSwaps()]);
    }

    async loadCoins() {
        const res = await this.rpc("get_enabled_coins");
        this.state.coins = res.result || [];
        const tickers = this.state.coins.map((c) => c.ticker);
        if (!tickers.includes(this.state.base)) {
            this.state.base = tickers[0] || "";
        }
        if (!tickers.includes(this.state.rel) || this.state.rel === this.state.base) {
            this.state.rel = tickers.find((t) => t !== this.state.base) || "";
        }
        const balances = {};
        for (const c of this.state.coins) {
            try {
                const b = await this.rpc("my_balance", { coin: c.ticker });
                balances[c.ticker] = { balance: b.balance, locked: b.unspendable_balance };
            } catch {
                balances[c.ticker] = { balance: "—" };
            }
        }
        this.state.balances = balances;
    }

    async loadBook() {
        const { base, rel } = this.state;
        if (!base || !rel || base === rel) {
            this.state.book = null;
            return;
        }
        const res = await this.rpc("orderbook", { base, rel });
        const row = (o) => ({
            uuid: o.uuid,
            price: o.price,
            volume: o.base_max_volume || o.maxvolume,
            address: o.address || "",
            mine: !!o.is_mine,
        });
        this.state.book = {
            asks: (res.asks || []).map(row).sort((a, b) => a.price - b.price),
            bids: (res.bids || []).map(row).sort((a, b) => b.price - a.price),
        };
    }

    async loadOrders() {
        const res = await this.rpc("my_orders");
        const r = res.result || {};
        const maker = Object.entries(r.maker_orders || {}).map(([uuid, o]) => ({
            uuid, kind: "выставлена", base: o.base, rel: o.rel, price: o.price,
            volume: o.available_amount || o.max_base_vol, created: o.created_at,
            cancellable: o.cancellable !== false,
        }));
        const taker = Object.entries(r.taker_orders || {}).map(([uuid, o]) => {
            const q = o.request || {};
            return {
                uuid, kind: q.action === "Sell" ? "продажа из стакана" : "покупка из стакана",
                base: q.base, rel: q.rel,
                price: q.base_amount ? Number(q.rel_amount) / Number(q.base_amount) : "",
                volume: q.base_amount, created: o.created_at, cancellable: o.cancellable !== false,
            };
        });
        this.state.orders = [...maker, ...taker].sort((a, b) => (b.created || 0) - (a.created || 0));
    }

    async loadSwaps() {
        const res = await this.rpc("my_recent_swaps", { limit: 20 });
        const swaps = (res.result && res.result.swaps) || [];
        this.state.swaps = swaps.map((s) => {
            const types = (s.events || []).map((e) => e.event && e.event.type);
            const failed = types.some((t) => (s.error_events || []).includes(t));
            const finished = types.includes("Finished");
            const info = s.my_info || {};
            return {
                uuid: s.uuid,
                role: s.type === "Maker" ? "по вашей заявке" : "из стакана",
                gave: `${this.qty(info.my_amount)} ${info.my_coin || ""}`,
                got: `${this.qty(info.other_amount)} ${info.other_coin || ""}`,
                started: info.started_at,
                state: failed ? "не удался, средства возвращаются" : finished ? "завершён" : "идёт",
                cls: failed ? "o_coop_dext_down" : finished ? "o_coop_dext_up" : "",
            };
        });
    }

    async pickPair(key, ev) {
        this.state[key] = ev.target.value;
        try {
            await this.loadBook();
        } catch (error) {
            this.notification.add(error.message, { type: "danger" });
        }
    }

    pick(row, isAsk) {
        if (row.mine) {
            this.notification.add("Это ваша собственная заявка.", { type: "warning" });
            return;
        }
        this.state.side = isAsk ? "buy" : "sell";
        this.state.mode = "take";
        this.state.price = String(row.price);
        this.state.volume = String(row.volume);
    }

    // ── Действия ────────────────────────────────────────────────────

    get canTrade() {
        const p = Number(this.state.price);
        const v = Number(this.state.volume);
        return this.state.base && this.state.rel && this.state.base !== this.state.rel
            && p > 0 && v > 0 && !this.state.busy;
    }

    get total() {
        const t = Number(this.state.price) * Number(this.state.volume);
        return t > 0 ? this.qty(t) : "0";
    }

    async placeOrder() {
        if (!this.canTrade) {
            return;
        }
        const { base, rel, side, mode, price, volume } = this.state;
        this.state.busy = true;
        try {
            let res;
            if (mode === "take") {
                res = await this.rpc(side, { base, rel, price, volume });
                this.notification.add(`Запрос отправлен в сеть (${res.result.uuid.slice(0, 8)}…). Обмен начнётся, когда встречная сторона ответит.`, { type: "success" });
            } else if (side === "sell") {
                res = await this.rpc("setprice", { base, rel, price, volume, cancel_previous: false });
                this.notification.add(`Заявка выставлена (${res.result.uuid.slice(0, 8)}…) и видна всей сети Komodo.`, { type: "success" });
            } else {
                // Выставить покупку base — это продать rel по обратной цене.
                const relVolume = String(Number(price) * Number(volume));
                const inverse = String(1 / Number(price));
                res = await this.rpc("setprice", { base: rel, rel: base, price: inverse, volume: relVolume, cancel_previous: false });
                this.notification.add(`Заявка на покупку выставлена (${res.result.uuid.slice(0, 8)}…).`, { type: "success" });
            }
            await Promise.all([this.loadBook(), this.loadOrders()]);
        } catch (error) {
            this.notification.add(error.message, { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    async cancel(order) {
        try {
            await this.rpc("cancel_order", { uuid: order.uuid });
            await Promise.all([this.loadBook(), this.loadOrders()]);
        } catch (error) {
            this.notification.add(error.message, { type: "danger" });
        }
    }

    async activateCoin() {
        const { coin, server } = this.state.activate;
        if (!coin || !server) {
            return;
        }
        try {
            await this.rpc("electrum", { coin, servers: [{ url: server }] });
            this.notification.add(`${coin} подключена.`, { type: "success" });
            this.state.activate.coin = "";
            this.state.activate.server = "";
            await this.refresh();
        } catch (error) {
            this.notification.add(error.message, { type: "danger" });
        }
    }

    async reload() {
        try {
            await this.refresh();
        } catch (error) {
            this.notification.add(error.message, { type: "danger" });
        }
    }

    toggleGuide() {
        this.state.showGuide = !this.state.showGuide;
    }

    async copyConfig() {
        try {
            await browser.navigator.clipboard.writeText(this.mm2json);
            this.notification.add("MM2.json скопирован.", { type: "info" });
        } catch {
            this.notification.add("Буфер обмена недоступен — выделите текст и скопируйте вручную.", { type: "warning" });
        }
    }

    openTerminal() {
        this.action.doAction("coop_crypto_exchange.action_coop_dex_terminal");
    }

    // ── Числа ───────────────────────────────────────────────────────

    qty(v) {
        const n = Number(v);
        return isNaN(n) ? (v || "—") : n.toLocaleString("ru-RU", { maximumFractionDigits: 8 });
    }

    when(ts) {
        if (!ts) {
            return "";
        }
        // KDF отдаёт created_at в миллисекундах, started_at — в секундах.
        const ms = ts > 1e12 ? ts : ts * 1000;
        return new Date(ms).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
    }
}

registry.category("actions").add("coop_crypto_exchange.komodo_node", CoopKomodoNode);
