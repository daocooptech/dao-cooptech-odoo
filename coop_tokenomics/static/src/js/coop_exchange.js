/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { connectTonWallet } from "@coop_tokenomics/js/coop_ton_connect";

/**
 * Торговый экран биржи.
 *
 * Устроен как площадка обмена, к которой участник привык по внешним
 * биржам: категории над списком рынков, сортировка по любой колонке,
 * группировки, стакан двумя колонками, линия цены и форма сделки.
 *
 * Два отличия от привычного, и оба намеренные.
 *
 * **Встречные заявки не сводятся сами.** Покупатель выбирает конкретную
 * заявку и подтверждает покупку. Автоматическое сведение по цене — это
 * организованные торги, которые вправе проводить только биржа по
 * лицензии Банка России (ст. 5 ФЗ «Об организованных торгах»). Внешне
 * разница в один щелчок, юридически — принципиальная.
 *
 * **Рынок — не пара валют, а партия товара.** Поэтому у каждой строки
 * стоят качество, место и срок: «морковь» без этих трёх слов — не товар,
 * а обещание вообще. По той же причине группировки идут по типу товара,
 * сроку, месту и поставщику: покупателю зерна и покупателю смен
 * экскаватора нужны разные списки.
 */
export class CoopExchange extends Component {
    static template = "coop_tokenomics.Exchange";
    static props = ["*"];

    static CATEGORIES = [
        { key: "all", label: "Все рынки" },
        { key: "soon", label: "Скоро поставка" },
        { key: "new", label: "Новые выпуски" },
        { key: "up", label: "Дорожают" },
        { key: "down", label: "Дешевеют" },
    ];

    static GROUPINGS = [
        { key: "none", label: "Без группировки" },
        { key: "type", label: "По типу товара" },
        { key: "due", label: "По сроку поставки" },
        { key: "place", label: "По месту передачи" },
        { key: "issuer", label: "По поставщику" },
    ];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            data: null,
            book: null,
            wallet: null,
            currentId: null,
            search: "",
            category: "all",
            grouping: "none",
            sort: "due",
            desc: false,
            openGroups: {},
            amount: 0,
            selectedOrder: null,
            showScore: false,
            loading: true,
        });

        onWillStart(async () => {
            await this.load();
        });
    }

    async load() {
        const [data, wallet] = await Promise.all([
            this.orm.call("coop.exchange", "markets", [], {
                category: this.state.category,
                grouping: this.state.grouping,
            }),
            this.orm.call("coop.exchange", "wallet", []),
        ]);
        this.state.data = data;
        this.state.wallet = wallet;
        this.state.loading = false;
        const rows = this.sortedRows;
        if (rows.length && !rows.some((r) => r.id === this.state.currentId)) {
            await this.select(rows[0].id);
        }
    }

    get rows() {
        return this.state.data ? this.state.data.rows : [];
    }

    get counts() {
        return this.state.data ? this.state.data.counts : {};
    }

    get groups() {
        return this.state.data ? this.state.data.groups : [];
    }

    /** Рынки после поиска и сортировки.
     *
     * Ищем по названию, поставщику, месту и качеству разом: участник
     * помнит партию по-разному — кто по товару, кто по хозяйству, кто по
     * тому, что забирать во Владивостоке.
     */
    get sortedRows() {
        const q = this.state.search.trim().toLowerCase();
        let rows = this.rows;
        if (q) {
            rows = rows.filter((m) =>
                [m.name, m.issuer, m.place, m.quality, m.city]
                    .filter(Boolean)
                    .some((v) => v.toLowerCase().includes(q))
            );
        }
        const key = this.state.sort;
        const sign = this.state.desc ? -1 : 1;
        return [...rows].sort((a, b) => {
            const va = key === "due" ? a.days_left : a[key];
            const vb = key === "due" ? b.days_left : b[key];
            if (typeof va === "string") {
                return sign * va.localeCompare(vb, "ru");
            }
            return sign * ((va || 0) - (vb || 0));
        });
    }

    /** Строки одной группы — в том же порядке сортировки, что и общий список. */
    groupRows(group) {
        const ids = new Set(group.ids);
        return this.sortedRows.filter((r) => ids.has(r.id));
    }

    isGroupOpen(group) {
        return this.state.openGroups[group.key] !== false;
    }

    toggleGroup(group) {
        this.state.openGroups[group.key] = !this.isGroupOpen(group);
    }

    get current() {
        return this.state.book ? this.state.book.claim : null;
    }

    get currentRow() {
        return this.rows.find((r) => r.id === this.state.currentId) || null;
    }

    async setCategory(key) {
        this.state.category = key;
        await this.load();
    }

    async setGrouping(ev) {
        this.state.grouping = ev.target.value;
        await this.load();
    }

    /** Сортировка щелчком по заголовку — как в биржевых таблицах.
     *
     * Повторный щелчок по той же колонке переворачивает порядок; это
     * ожидаемое поведение, и объяснять его подписью не нужно.
     */
    sortBy(key) {
        if (this.state.sort === key) {
            this.state.desc = !this.state.desc;
        } else {
            this.state.sort = key;
            this.state.desc = key !== "due" && key !== "name";
        }
    }

    sortMark(key) {
        if (this.state.sort !== key) {
            return "";
        }
        return this.state.desc ? " ↓" : " ↑";
    }

    async select(claimId) {
        this.state.currentId = claimId;
        this.state.selectedOrder = null;
        this.state.amount = 0;
        this.state.book = await this.orm.call("coop.exchange", "book", [claimId]);
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
    }

    toggleScore() {
        this.state.showScore = !this.state.showScore;
    }

    /** Выбрать заявку в стакане.
     *
     * Щелчок по строке подставляет её цену и остаток в форму — так же,
     * как на биржах, где клик по стакану заполняет ордер. Своя заявка не
     * выбирается: купить у себя нельзя, и предлагать это бессмысленно.
     */
    pick(order) {
        if (order.mine) {
            this.notification.add("Это ваша собственная заявка.", { type: "warning" });
            return;
        }
        this.state.selectedOrder = order;
        this.state.amount = order.quantity;
    }

    onAmount(ev) {
        const value = parseFloat(ev.target.value.replace(",", "."));
        this.state.amount = isNaN(value) ? 0 : value;
    }

    get total() {
        if (!this.state.selectedOrder) {
            return 0;
        }
        return this.state.amount * this.state.selectedOrder.price;
    }

    get canTrade() {
        return (
            this.state.wallet &&
            this.state.wallet.connected &&
            this.state.selectedOrder &&
            this.state.amount > 0 &&
            this.state.amount <= this.state.selectedOrder.quantity
        );
    }

    /** Подтвердить сделку по выбранной заявке.
     *
     * Сервер готовит сделку, подписывает её кошелёк участника. Пока
     * подпись не пришла из сети, сделка висит в состоянии «ждёт подписи»
     * — и показывается именно так: считать её состоявшейся по записи в
     * нашей базе нельзя, база знает лишь то, что ей сказали.
     */
    async trade() {
        if (!this.canTrade) {
            return;
        }
        const order = this.state.selectedOrder;
        try {
            await this.orm.call("coop.token.order", "action_prepare_trade",
                [[order.id], this.state.amount]);
            this.notification.add(
                "Сделка подготовлена и ждёт подписи в кошельке.",
                { type: "success" }
            );
            await this.select(this.state.currentId);
            await this.load();
        } catch (error) {
            this.notification.add(
                error.data && error.data.message ? error.data.message : String(error),
                { type: "danger" }
            );
        }
    }

    openClaim() {
        if (!this.state.currentId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "coop.token.claim",
            res_id: this.state.currentId,
            views: [[false, "form"]],
        });
    }

    /** Подключить кошелёк, не уходя с торгов.
     *
     * Раньше кнопка уводила на страницу участника: человек нажимал
     * «купить», попадал в профиль и терял место, на котором стоял.
     * Кошелёк подключается здесь же, а на странице участника остаётся
     * то же действие для тех, кто пришёл туда сам.
     */
    async connectWallet() {
        try {
            const result = await connectTonWallet();
            if (!result) {
                return;
            }
            this.notification.add("Кошелёк подключён.", { type: "success" });
            await this.load();
        } catch (error) {
            this.notification.add(
                error && error.message ? error.message : String(error),
                { type: "danger" }
            );
        }
    }

    // ── Отрисовка чисел ──────────────────────────────────────────────────

    money(value, currency) {
        const num = (value || 0).toLocaleString("ru-RU", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        const sign = { usdt: "USDT", ton: "TON", rub: "₽" }[currency] || "";
        return sign ? `${num} ${sign}` : num;
    }

    qty(value) {
        return (value || 0).toLocaleString("ru-RU", { maximumFractionDigits: 3 });
    }

    percent(value) {
        const num = (value || 0).toFixed(1);
        return value > 0 ? `+${num}%` : `${num}%`;
    }

    /** Срок словами: до чего считать дни, участник понимает сразу. */
    dueLabel(row) {
        const d = row.days_left;
        if (d < 0) {
            return "срок прошёл";
        }
        if (d === 0) {
            return "сегодня";
        }
        if (d <= 30) {
            return `через ${d} дн.`;
        }
        return row.due;
    }

    /** Ширина полоски объёма в стакане.
     *
     * На биржах за ценой стоит полоса — по ней видно, где стена, а где
     * одна заявка на килограмм. Считается от самой крупной заявки в
     * колонке, а не от общего объёма: иначе при одной большой заявке все
     * остальные схлопываются в нить.
     */
    depth(order, rows) {
        const max = Math.max(...rows.map((r) => r.quantity), 1);
        return `${Math.max((order.quantity / max) * 100, 4)}%`;
    }

    /** Линия цены по сделкам — координаты для SVG.
     *
     * Своей библиотеки графиков не подключаем: линия из десятка точек
     * рисуется двумя строками, а зависимость тянула бы за собой вес,
     * который на этом экране нечем оправдать.
     */
    get chartPath() {
        const points = (this.state.book && this.state.book.chart) || [];
        if (points.length < 2) {
            return "";
        }
        const prices = points.map((p) => p.price);
        const min = Math.min(...prices);
        const max = Math.max(...prices);
        const span = max - min || 1;
        const step = 100 / (points.length - 1);
        return points
            .map((p, i) => {
                const x = (i * step).toFixed(2);
                const y = (100 - ((p.price - min) / span) * 90 - 5).toFixed(2);
                return `${i === 0 ? "M" : "L"}${x},${y}`;
            })
            .join(" ");
    }

    get chartRange() {
        const points = (this.state.book && this.state.book.chart) || [];
        if (!points.length) {
            return null;
        }
        const prices = points.map((p) => p.price);
        return { min: Math.min(...prices), max: Math.max(...prices), count: points.length };
    }
}

registry.category("actions").add("coop_tokenomics.exchange", CoopExchange);
