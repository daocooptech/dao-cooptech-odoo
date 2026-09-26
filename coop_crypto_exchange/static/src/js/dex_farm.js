/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Фарминг на DEX бирже (владелец 26.09.2026): пулы ликвидности под
 * настоящие проекты платформы. Модель — models/coop_crypto_farm.py.
 *
 * Сверху — сводка (в пулах, открытых пулов, участников, выплачено, мои
 * вложения и доход к получению); ниже — мои позиции с «забрать доход» и
 * «вывести»; дальше — пулы плитками с фильтрами по состоянию и монете и
 * сортировкой. Взнос — в раскрывающейся форме на плитке.
 */

const SORTS = [
    { key: "apr", label: "Доходность" },
    { key: "tvl", label: "Объём пула" },
    { key: "deadline", label: "Скоро закрытие" },
    { key: "progress", label: "Почти собран" },
];

export class CoopDexFarm extends Component {
    static template = "coop_crypto_exchange.DexFarm";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.sorts = SORTS;
        this.state = useState({
            data: null,
            filter: "raising",
            coin: "",
            sort: "apr",
            query: "",
            open: null,
            amount: 0,
            busy: false,
            showAll: false,
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("coop.farm.pool", "farm_overview", []);
    }

    // ── Отбор ───────────────────────────────────────────────────────

    get coins() {
        const seen = new Set();
        for (const p of (this.state.data && this.state.data.pools) || []) {
            seen.add(p.coin);
        }
        return [...seen].sort();
    }

    count(filter) {
        const pools = (this.state.data && this.state.data.pools) || [];
        return filter === "all" ? pools.length : pools.filter((p) => p.state === filter).length;
    }

    get pools() {
        let rows = (this.state.data && this.state.data.pools) || [];
        if (this.state.filter !== "all") {
            rows = rows.filter((p) => p.state === this.state.filter);
        }
        if (this.state.coin) {
            rows = rows.filter((p) => p.coin === this.state.coin);
        }
        const q = this.state.query.trim().toLowerCase();
        if (q) {
            rows = rows.filter((p) => `${p.project} ${p.city} ${p.purpose} ${p.initiator}`.toLowerCase().includes(q));
        }
        const by = {
            apr: (a, b) => b.apr - a.apr,
            tvl: (a, b) => b.tvl_rub - a.tvl_rub,
            deadline: (a, b) => (a.days_left ?? 9999) - (b.days_left ?? 9999),
            progress: (a, b) => b.progress - a.progress,
        }[this.state.sort];
        return [...rows].sort(by);
    }

    get shown() {
        return this.state.showAll ? this.pools : this.pools.slice(0, 24);
    }

    setFilter(f) {
        this.state.filter = f;
        this.state.showAll = false;
    }
    setCoin(ev) {
        this.state.coin = ev.target.value;
    }
    setSort(ev) {
        this.state.sort = ev.target.value;
    }
    onQuery(ev) {
        this.state.query = ev.target.value;
    }
    showAll() {
        this.state.showAll = true;
    }

    // ── Взнос ───────────────────────────────────────────────────────

    toggle(pool) {
        this.state.open = this.state.open === pool.id ? null : pool.id;
        this.state.amount = pool.min_stake || 0;
    }

    onAmount(ev) {
        const v = parseFloat(String(ev.target.value).replace(",", "."));
        this.state.amount = isNaN(v) ? 0 : v;
    }

    setMax(pool) {
        this.state.amount = Number(Math.max(pool.target - pool.tvl, 0).toFixed(8));
    }

    yearIncome(pool) {
        return (this.state.amount || 0) * pool.apr / 100;
    }

    async stake(pool) {
        this.state.busy = true;
        try {
            await this.orm.call("coop.farm.pool", "farm_stake", [pool.id, this.state.amount]);
            this.notification.add(
                `Внесено ${this.qty(this.state.amount)} ${pool.coin} в пул «${pool.project}». Доход начисляется с сегодняшнего дня.`,
                { type: "success" });
            this.state.open = null;
            await this.load();
        } catch (error) {
            this.notification.add(error.data?.message || String(error), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    canHarvest(pos) {
        // Кнопка — когда начисленное видно в знаках монеты, а не доли секунды.
        return this.amt(pos.pending, pos.coin) !== "0";
    }

    async harvest(pos) {
        try {
            const got = await this.orm.call("coop.farm.stake", "farm_harvest", [pos.id]);
            this.notification.add(`Доход ${this.amt(got, pos.coin)} ${pos.coin} — к переводу на ваш кошелёк.`, { type: "success" });
            await this.load();
        } catch (error) {
            this.notification.add(error.data?.message || String(error), { type: "danger" });
        }
    }

    async withdraw(pos) {
        try {
            await this.orm.call("coop.farm.stake", "farm_withdraw", [pos.id]);
            this.notification.add(`Вывод ${this.amt(pos.amount, pos.coin)} ${pos.coin} из пула оформлен.`, { type: "success" });
            await this.load();
        } catch (error) {
            this.notification.add(error.data?.message || String(error), { type: "danger" });
        }
    }

    // ── Переходы ────────────────────────────────────────────────────

    openTerminal() {
        this.action.doAction("coop_crypto_exchange.action_coop_dex_terminal");
    }
    openFarm() {}
    openNode() {
        this.action.doAction("coop_crypto_exchange.action_coop_komodo_node");
    }
    openTrades() {
        this.action.doAction("coop_crypto_exchange.action_coop_crypto_trade");
    }
    openProject(pool) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "coop.project", res_id: pool.project_id,
            views: [[false, "form"]],
        });
    }
    async newPool() {
        await this.action.doAction("coop_crypto_exchange.action_coop_farm_pool_new", {
            onClose: () => this.load(),
        });
    }

    // ── Числа ───────────────────────────────────────────────────────

    qty(v) {
        return (v || 0).toLocaleString("ru-RU", { maximumFractionDigits: 6 });
    }
    amt(v, coin) {
        // USDT и TON — до сотых, остальные монеты — до стомиллионных долей.
        const digits = /^(USDT|TON)/.test(coin || "") ? 2 : 6;
        return (v || 0).toLocaleString("ru-RU", { maximumFractionDigits: digits });
    }
    rub(v) {
        const n = v || 0;
        if (n >= 1e9) {
            return (n / 1e9).toLocaleString("ru-RU", { maximumFractionDigits: 2 }) + " млрд ₽";
        }
        if (n >= 1e6) {
            return (n / 1e6).toLocaleString("ru-RU", { maximumFractionDigits: 2 }) + " млн ₽";
        }
        return n.toLocaleString("ru-RU", { maximumFractionDigits: 0 }) + " ₽";
    }
    apr(v) {
        return (v || 0).toLocaleString("ru-RU", { maximumFractionDigits: 1 }) + "%";
    }
    dmy(d) {
        return d ? `${d.slice(8, 10)}.${d.slice(5, 7)}.${d.slice(0, 4)}` : "";
    }
    daysWord(n) {
        const a = Math.abs(n) % 100;
        const b = a % 10;
        if (a > 10 && a < 20) {
            return "дней";
        }
        return b === 1 ? "день" : b >= 2 && b <= 4 ? "дня" : "дней";
    }
}

registry.category("actions").add("coop_crypto_exchange.farm", CoopDexFarm);
