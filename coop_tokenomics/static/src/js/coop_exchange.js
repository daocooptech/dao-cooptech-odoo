/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Торговый экран биржи.
 *
 * Устроен как площадка обмена, к которой участник привык по внешним
 * биржам: слева список рынков с ценой и изменением, справа выбранный
 * рынок — заявки на продажу и на покупку двумя колонками, под ними
 * прошедшие сделки, сбоку форма покупки.
 *
 * Одно отличие от привычного, и оно намеренное: **встречные заявки не
 * сводятся сами**. Покупатель выбирает конкретную заявку и подтверждает
 * покупку. Автоматическое сведение по цене — это организованные торги,
 * которые вправе проводить только биржа по лицензии Банка России
 * (ст. 5 ФЗ «Об организованных торгах»). Внешне разница в один щелчок,
 * юридически — принципиальная.
 *
 * Второе отличие: рынок здесь — не пара валют, а партия товара. Поэтому
 * у каждой строки списка стоят качество, место и срок: «морковь» без
 * этих трёх слов — не товар, а обещание вообще.
 */
export class CoopExchange extends Component {
    static template = "coop_tokenomics.Exchange";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            markets: [],
            book: null,
            wallet: null,
            currentId: null,
            search: "",
            side: "buy",
            amount: 0,
            selectedOrder: null,
            loading: true,
        });

        onWillStart(async () => {
            await this.load();
        });
    }

    async load() {
        const [markets, wallet] = await Promise.all([
            this.orm.call("coop.exchange", "markets", []),
            this.orm.call("coop.exchange", "wallet", []),
        ]);
        this.state.markets = markets;
        this.state.wallet = wallet;
        this.state.loading = false;
        if (markets.length) {
            await this.select(markets[0].id);
        }
    }

    /** Рынки, отфильтрованные строкой поиска.
     *
     * Ищем по названию, поставщику и месту передачи разом: участник
     * помнит партию по-разному — кто по товару, кто по хозяйству, кто по
     * тому, что забирать во Владивостоке.
     */
    get visibleMarkets() {
        const q = this.state.search.trim().toLowerCase();
        if (!q) {
            return this.state.markets;
        }
        return this.state.markets.filter((m) =>
            [m.name, m.issuer, m.place, m.quality]
                .filter(Boolean)
                .some((v) => v.toLowerCase().includes(q))
        );
    }

    get current() {
        return this.state.book ? this.state.book.claim : null;
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

    setSide(side) {
        this.state.side = side;
        this.state.selectedOrder = null;
        this.state.amount = 0;
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
            await this.refreshWallet();
        } catch (error) {
            this.notification.add(
                error.data && error.data.message ? error.data.message : String(error),
                { type: "danger" }
            );
        }
    }

    async refreshWallet() {
        this.state.wallet = await this.orm.call("coop.exchange", "wallet", []);
    }

    /** Открыть карточку выпуска — там подробности и действия поставщика. */
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

    /** Подключение кошелька — на странице участника, где оно и живёт. */
    openWallet() {
        this.action.doAction("coop_profile.action_coop_my_page");
    }

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
}

registry.category("actions").add("coop_tokenomics.exchange", CoopExchange);
