/** @odoo-module **/

import { Component, onWillStart, proxy, usePlugin, useProps } from "@odoo/owl";
import { NotificationPlugin } from "@web/core/notifications/notification_plugin";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ActionPlugin } from "@web/webclient/actions/action_plugin";

/**
 * Пулы проектов (решения 434–436, 28.09.2026) — бывший «Фарминг». Модель —
 * models/coop_crypto_farm.py.
 *
 * Два вида вкладками: в монете и в рублях (ЦФА, учебный выпуск). Сводка —
 * числа пулов и людей, без рублей. «Мои пулы как инициатора» — записать
 * выплату из выручки; «Мои взносы» — получено, ждёт подтверждения
 * («получил» / «спор»), потолок. Пулы плитками: доля выручки и потолок,
 * ход сбора или выплат, просрочка. «Доходности» нет ни в плитке, ни в
 * сортировке.
 */

const SORTS = [
    { key: "new", label: "Новые" },
    { key: "deadline", label: "Скоро закрытие сбора" },
    { key: "progress", label: "Почти собран" },
    { key: "paid", label: "Больше выплачено" },
    { key: "size", label: "Размер сбора" },
];

export class CoopDexFarm extends Component {
    static template = "coop_crypto_exchange.DexFarm";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.action = usePlugin(ActionPlugin);
        this.notification = usePlugin(NotificationPlugin);
        this.sorts = SORTS;
        this.state = proxy({
            data: null,
            kind: "coin",
            filter: "raising",
            coin: "",
            sort: "new",
            query: "",
            open: null,
            amount: 0,
            pay: null,
            revenue: 0,
            tx: "",
            busy: false,
            showAll: false,
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("coop.farm.pool", "farm_overview", []);
    }

    // ── Отбор ───────────────────────────────────────────────────────

    get ofKind() {
        return ((this.state.data && this.state.data.pools) || []).filter((p) => p.kind === this.state.kind);
    }

    get totals() {
        return (this.state.data && this.state.data.totals[this.state.kind]) || {};
    }

    get coins() {
        return [...new Set(this.ofKind.map((p) => p.coin))].sort();
    }

    kindCount(kind) {
        return ((this.state.data && this.state.data.pools) || []).filter((p) => p.kind === kind).length;
    }

    match(p, filter) {
        if (filter === "all") {
            return true;
        }
        if (filter === "overdue") {
            return p.overdue > 0;
        }
        return p.state === filter;
    }

    count(filter) {
        return this.ofKind.filter((p) => this.match(p, filter)).length;
    }

    get pools() {
        let rows = this.ofKind.filter((p) => this.match(p, this.state.filter));
        if (this.state.coin && this.state.kind === "coin") {
            rows = rows.filter((p) => p.coin === this.state.coin);
        }
        const q = this.state.query.trim().toLowerCase();
        if (q) {
            rows = rows.filter((p) => `${p.project} ${p.city} ${p.purpose} ${p.initiator}`.toLowerCase().includes(q));
        }
        const by = {
            new: (a, b) => b.id - a.id,
            deadline: (a, b) => (a.days_left ?? 9999) - (b.days_left ?? 9999),
            progress: (a, b) => b.progress - a.progress,
            paid: (a, b) => b.paid_pct - a.paid_pct,
            size: (a, b) => b.target * b.price_rub - a.target * a.price_rub,
        }[this.state.sort];
        return [...rows].sort(by);
    }

    get shown() {
        return this.state.showAll ? this.pools : this.pools.slice(0, 24);
    }

    get myPools() {
        return this.ofKind.filter(
            (p) => p.is_initiator && ["active", "default", "raising"].includes(p.state));
    }

    get myStakes() {
        return ((this.state.data && this.state.data.mine) || []).filter((m) => m.kind === this.state.kind);
    }

    setKind(kind) {
        this.state.kind = kind;
        this.state.coin = "";
        this.state.showAll = false;
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

    capFor(pool) {
        return (this.state.amount || 0) * (pool.cap_multiple || 1);
    }

    async stake(pool) {
        this.state.busy = true;
        try {
            await this.orm.call("coop.farm.pool", "farm_stake", [pool.id, this.state.amount]);
            this.notification.add(
                `Внесено ${this.qty(this.state.amount)} ${pool.coin} в пул «${pool.project}». Выплаты начнутся, когда пул соберётся.`,
                { type: "success" });
            this.state.open = null;
            await this.load();
        } catch (error) {
            this.notification.add(error.data?.message || String(error), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    async withdraw(pos) {
        try {
            await this.orm.call("coop.farm.stake", "farm_withdraw", [pos.id]);
            this.notification.add(`Возврат ${this.amt(pos.amount, pos.coin)} ${pos.coin} из несобранного пула оформлен.`, { type: "success" });
            await this.load();
        } catch (error) {
            this.notification.add(error.data?.message || String(error), { type: "danger" });
        }
    }

    // ── Подтверждение выплат ────────────────────────────────────────

    async confirmLine(line) {
        try {
            await this.orm.call("coop.farm.payout.line", "farm_confirm", [line.id]);
            this.notification.add("Получение подтверждено.", { type: "success" });
            await this.load();
        } catch (error) {
            this.notification.add(error.data?.message || String(error), { type: "danger" });
        }
    }

    async disputeLine(line) {
        const note = window.prompt("Что не так с выплатой? Инициатор увидит ваш ответ.", "Перевод не пришёл");
        if (note === null) {
            return;
        }
        try {
            await this.orm.call("coop.farm.payout.line", "farm_dispute", [line.id, note]);
            this.notification.add("Спор открыт — выплата не засчитана, пока вы её не подтвердите.", { type: "warning" });
            await this.load();
        } catch (error) {
            this.notification.add(error.data?.message || String(error), { type: "danger" });
        }
    }

    // ── Выплата инициатора ──────────────────────────────────────────

    togglePay(pool) {
        this.state.pay = this.state.pay === pool.id ? null : pool.id;
        this.state.revenue = 0;
        this.state.tx = "";
    }
    onRevenue(ev) {
        const v = parseFloat(String(ev.target.value).replace(",", "."));
        this.state.revenue = isNaN(v) ? 0 : v;
    }
    onTx(ev) {
        this.state.tx = ev.target.value;
    }
    payShare(pool) {
        const left = Math.max(pool.cap - pool.paid, 0);
        return Math.min((this.state.revenue || 0) * pool.revenue_share / 100, left);
    }

    async recordPayout(pool) {
        this.state.busy = true;
        try {
            await this.orm.call("coop.farm.pool", "farm_record_payout", [pool.id, this.state.revenue, this.state.tx]);
            this.notification.add(
                `Выплата ${this.amt(this.payShare(pool), pool.coin)} ${pool.coin} записана — участники подтвердят получение.`,
                { type: "success" });
            this.state.pay = null;
            await this.load();
        } catch (error) {
            this.notification.add(error.data?.message || String(error), { type: "danger" });
        } finally {
            this.state.busy = false;
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
            additionalContext: { default_kind: this.state.kind },
            onClose: () => this.load(),
        });
    }

    // ── Числа ───────────────────────────────────────────────────────

    qty(v) {
        return (v || 0).toLocaleString("ru-RU", { maximumFractionDigits: 6 });
    }
    amt(v, coin) {
        // Рубли, USDT и TON — до сотых (рубли — целыми), прочие монеты — до миллионных.
        if (coin === "₽") {
            return (v || 0).toLocaleString("ru-RU", { maximumFractionDigits: 0 });
        }
        const digits = /^(USDT|TON)/.test(coin || "") ? 2 : 6;
        return (v || 0).toLocaleString("ru-RU", { maximumFractionDigits: digits });
    }
    pct(v) {
        return (v || 0).toLocaleString("ru-RU", { maximumFractionDigits: 1 }) + " %";
    }
    mult(v) {
        return (v || 0).toLocaleString("ru-RU", { maximumFractionDigits: 2 }) + "×";
    }
    short(hash) {
        return hash.length > 16 ? `${hash.slice(0, 8)}…${hash.slice(-6)}` : hash;
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
    payoutsWord(n) {
        const a = Math.abs(n) % 100;
        const b = a % 10;
        if (a > 10 && a < 20) {
            return "выплат";
        }
        return b === 1 ? "выплата" : b >= 2 && b <= 4 ? "выплаты" : "выплат";
    }
}

registry.category("actions").add("coop_crypto_exchange.farm", CoopDexFarm);
