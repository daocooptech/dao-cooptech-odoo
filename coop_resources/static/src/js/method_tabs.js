/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";

const { DateTime } = luxon;

/**
 * «На каких условиях» — способы передачи вкладками.
 *
 * Владелец 27.10.2026: «должно быть как в браузере вкладками (продажа,
 * аренда и тп) и в конце + . там вносятся данные о стоимости, и тд ни
 * каких таблиц». Вкладка — способ из «Способов передачи», внутри —
 * условия этого способа (строка `coop.resource.term`, решение 412, Н5):
 * у продажи цена, у аренды ещё залог и срок, у обмена — что взамен.
 *
 * Ставится на `term_ids`. «+» отмечает способ в `method_ids` и сразу
 * заводит строку условий на странице, не дожидаясь сохранения: иначе
 * вкладка была бы пустой до записи, а продажа без цены не сохраняется.
 * «×» снимает и то и другое.
 */

/**
 * Что спрашивать у каждого способа (решение 629, владелец 27.10.2026:
 * «продумай какие данные нужно вносить во вкладках»). `fields` — поля
 * строки условий: [имя, вид, подпись, доп.]; в доп. — `request` (подпись у
 * спроса), `offer` (только у предложения), `ph`, `options`, `when`.
 * Подписи выборов — как в модели.
 */
const DOCUMENTS = [["none", "без документов"], ["receipt", "чек"], ["upd", "УПД"]];
const OPERATOR = [["no", "без оператора"], ["yes", "с оператором"], ["option", "оператор за доплату"]];
const PAY_EVERY = [["week", "раз в неделю"], ["month", "раз в месяц"], ["quarter", "раз в квартал"]];
const OWNERSHIP = [["now", "сразу"], ["end", "после последнего платежа"]];
const LESSOR = [["self", "я сам"], ["partner", "партнёрская лизинговая компания"]];
const INSURANCE = [["lessee", "лизингополучатель"], ["lessor", "лизингодатель"], ["none", "без страховки"]];
const CONTRIBUTION = [["own", "насовсем в проект"], ["use", "в пользование на срок проекта"]];
const EXPECT = [["share", "долю"], ["product", "часть продукции"], ["costs", "возмещение расходов"]];
const SURCHARGE = [["none", "без доплаты"], ["pay", "готов доплатить"], ["want", "жду доплату"]];
const FREE_MODE = [["forever", "насовсем"], ["loan", "на время, с возвратом"]];
const FREE_TO = [["any", "любому"], ["org", "организациям"], ["project", "проектам"]];
const RENT_PERIODS = ["час", "сутки", "неделя", "месяц"];
const INCLUDED = ["топливо", "расходники", "доставка"];

const LAYOUT = {
    sale: {
        price: "Цена, ₽", request: "Готов заплатить, ₽", unit: "шт., кг, м³, комплект",
        fields: [
            ["min_qty", "num", "Наименьшая партия", { request: "Сколько нужно" }],
            ["bulk_qty", "num", "Опт от, единиц", { offer: true }],
            ["bulk_price", "money", "Оптовая цена, ₽", { offer: true }],
            ["prepay_pct", "int", "Предоплата, %", { request: "Готов внести предоплату, %" }],
            ["warranty", "text", "Гарантия", { offer: true, ph: "Например, 6 месяцев" }],
            ["documents", "seg", "Документы", { options: DOCUMENTS, request: "Нужны документы" }],
        ],
        note: "Оплата, доставка",
    },
    rent: {
        price: "Ставка, ₽", request: "Готов платить, ₽", period: true, deposit: true,
        fields: [
            ["min_term", "text", "Наименьший срок", { request: "На какой срок", ph: "Например, 3 дня" }],
            ["max_term", "text", "Наибольший срок", { offer: true, ph: "Например, 2 месяца" }],
            ["operator", "seg", "Оператор", { options: OPERATOR }],
            ["included", "chips", "Входит в цену", { options: INCLUDED }],
            ["available_from", "date", "Свободно с", { request: "Нужно с" }],
            ["long_discount", "text", "Скидка за длинный срок", { offer: true, ph: "От месяца — 15 %" }],
        ],
        note: "Что ещё важно, как вернуть",
    },
    installment: {
        price: "Полная цена, ₽", request: "Готов заплатить всего, ₽", unit: "шт., комплект",
        calc: true,
        fields: [
            ["down_pct", "pct", "Первый взнос, %", { request: "Готов внести сразу, %" }],
            ["months", "int", "Срок, месяцев"],
            ["pay_every", "seg", "Платежи", { options: PAY_EVERY }],
            ["markup_pct", "pct", "Наценка, %", { offer: true, ph: "0 — без наценки" }],
            ["ownership", "seg", "Право собственности переходит", { options: OWNERSHIP }],
        ],
        note: "График, что при просрочке",
    },
    leasing: {
        price: "Стоимость предмета, ₽", request: "Готов взять предмет стоимостью до, ₽", calc: true,
        fields: [
            ["down_pct", "pct", "Аванс, %", { request: "Какой аванс готов внести, %" }],
            ["months", "int", "Срок, месяцев"],
            ["markup_pct", "pct", "Удорожание, %", { offer: true }],
            ["buyout", "money", "Выкупная стоимость, ₽"],
            ["payment_manual", "money", "Платёж в месяц, ₽", { offer: true, ph: "Пусто — посчитаем сами" }],
            ["lessor", "seg", "Лизингодатель", { options: LESSOR, offer: true }],
            ["lessor_name", "text", "Лизинговая компания", { offer: true, when: (t) => t.data.lessor === "partner" }],
            ["insurance", "seg", "Страховку платит", { options: INSURANCE }],
        ],
        note: "Что ещё важно",
    },
    project: {
        price: "Оценка вклада, ₽", request: "Оценка нужного, ₽",
        help: "По оценке вклада считается доля в проекте.",
        fields: [
            ["contribution", "seg", "Как вношу", { options: CONTRIBUTION, request: "Как нужно" }],
            ["expect", "seg", "Что жду взамен", { options: EXPECT, request: "Что даём взамен" }],
            ["project_scope", "text", "В какие проекты", { ph: "Любые, направление или название проекта" }],
        ],
        note: "Условия",
    },
    barter: {
        price: "Оценка, ₽", note: "Приму взамен", requestNote: "Что дам взамен", noteFirst: true,
        fields: [
            ["surcharge", "seg", "Доплата", { options: SURCHARGE }],
            ["surcharge_amount", "money", "Сумма доплаты, ₽",
             { when: (t) => ["pay", "want"].includes(t.data.surcharge) }],
        ],
    },
    free: {
        estimate: "Оценка, ₽ — по желанию", note: "Как забрать", requestNote: "Как заберу",
        noteFirst: true,
        fields: [
            ["free_mode", "seg", "Отдаю", { options: FREE_MODE, request: "Возьму" }],
            ["free_to", "seg", "Кому", { options: FREE_TO, offer: true }],
        ],
    },
};

const NUMERIC = ["num", "int", "pct", "money"];

/** «от / до / ровно / по договорённости» — у каждой вкладки своё. */
const PRICE_KINDS = [
    ["from", "от"],
    ["to", "до"],
    ["exact", "ровно"],
    ["none", "по договорённости"],
];

export class CoopMethodTabs extends Component {
    static template = "coop_resources.MethodTabs";
    props = useProps(standardFieldProps);

    setup() {
        this.orm = useService("orm");
        this.ui = proxy({ active: false, menu: false, busy: false });
        onWillStart(async () => {
            this.methods = await this.orm.searchRead(
                "coop.resource.method", [], ["name", "code", "sequence"], { order: "sequence, id" });
        });
    }

    get record() {
        return this.props.record;
    }

    get terms() {
        return this.record.data[this.props.name];
    }

    get chosenIds() {
        return this.record.data.method_ids.currentIds || [];
    }

    /** Вкладки — отмеченные способы по порядку справочника. */
    get tabs() {
        const chosen = new Set(this.chosenIds);
        return this.methods.filter((method) => chosen.has(method.id));
    }

    get rest() {
        const chosen = new Set(this.chosenIds);
        return this.methods.filter((method) => !chosen.has(method.id));
    }

    get current() {
        const tabs = this.tabs;
        return tabs.find((tab) => tab.id === this.ui.active) || tabs[0] || false;
    }

    get layout() {
        return (this.current && LAYOUT[this.current.code]) || { note: "Условия" };
    }

    /** Спрос — те же вкладки, подписи от лица того, кто ищет. */
    get isRequest() {
        return this.record.data.listing_type === "request";
    }

    get priceLabel() {
        const lay = this.layout;
        return (this.isRequest && lay.request) || lay.price || lay.estimate;
    }

    get noteLabel() {
        const lay = this.layout;
        return (this.isRequest && lay.requestNote) || lay.note || "Условия";
    }

    get rentPeriods() {
        return RENT_PERIODS;
    }

    /** Поля вкладки: [имя, вид, подпись, доп.] — без чужих спросу и скрытых условием. */
    get extraFields() {
        const term = this.term;
        return (this.layout.fields || [])
            .filter(([, , , opt = {}]) => !(opt.offer && this.isRequest))
            .filter(([, , , opt = {}]) => !opt.when || (term && opt.when(term)))
            .map(([name, kind, label, opt = {}]) => ({
                name, kind, opt,
                label: (this.isRequest && opt.request) || label,
            }));
    }

    inputValue(field) {
        const value = this.value(field.name);
        if (field.kind === "date") {
            return value && value.toISODate ? value.toISODate() : "";
        }
        if (NUMERIC.includes(field.kind)) {
            return value ? String(value) : "";
        }
        return value;
    }

    chips(field) {
        const have = String(this.value(field.name) || "").split(",").map((v) => v.trim()).filter(Boolean);
        return field.opt.options.map((option) => ({ option, on: have.includes(option) }));
    }

    async toggleChip(field, option) {
        const term = await this.ensureTerm();
        if (!term) {
            return;
        }
        const have = this.chips(field).filter((c) => c.on).map((c) => c.option);
        const next = have.includes(option) ? have.filter((v) => v !== option) : [...have, option];
        // Порядок — как в списке меток, а не как нажимали.
        const ordered = field.opt.options.filter((v) => next.includes(v));
        await term.update({ [field.name]: ordered.join(", ") || false });
    }

    async setChoice(name, choice) {
        const term = await this.ensureTerm();
        if (term) {
            // Повторное нажатие на выбранное снимает выбор: пустое не показывается.
            await term.update({ [name]: term.data[name] === choice ? false : choice });
        }
    }

    /** Платёж и итог — как в модели (`_compute_payment`), чтобы видеть их до сохранения. */
    get calc() {
        const term = this.term;
        const code = this.current && this.current.code;
        if (!term || !this.layout.calc) {
            return false;
        }
        const d = term.data;
        if (!d.price || !(d.months > 0)) {
            return false;
        }
        const down = (d.price * (d.down_pct || 0)) / 100;
        const markup = 1 + (d.markup_pct || 0) / 100;
        let payment, total, every;
        if (code === "installment") {
            const per = { week: 52 / 12, month: 1, quarter: 1 / 3 }[d.pay_every || "month"];
            const periods = Math.max(1, Math.round(d.months * per));
            const rest = (d.price - down) * markup;
            payment = rest / periods;
            total = down + rest;
            every = { week: "в неделю", quarter: "в квартал" }[d.pay_every] || "в месяц";
        } else {
            payment = d.payment_manual || (Math.max(0, d.price - down - (d.buyout || 0)) * markup) / d.months;
            total = down + payment * d.months + (d.buyout || 0);
            every = "в месяц";
        }
        const rub = (v) => Math.round(v).toLocaleString("ru-RU") + " ₽";
        return { payment: rub(payment), total: rub(total), down: rub(down), every };
    }

    termOf(method) {
        return method && this.terms.records.find((term) => {
            const value = term.data.method_id;
            return value && value.id === method.id;
        });
    }

    get term() {
        return this.termOf(this.current);
    }

    value(name) {
        const term = this.term;
        const value = term ? term.data[name] : false;
        return value === false || value === undefined || value === null ? "" : value;
    }

    toggleMenu() {
        this.ui.menu = !this.ui.menu;
    }

    get priceKinds() {
        return PRICE_KINDS;
    }

    get priceKind() {
        return this.value("price_kind") || "exact";
    }

    async setKind(kind) {
        const term = await this.ensureTerm();
        if (term) {
            // Сумму при «по договорённости» не обнуляем: она просто не
            // показывается, а вернулся к «от» — она на месте.
            await term.update({ price_kind: kind });
        }
    }

    select(method) {
        this.ui.active = method.id;
        this.ui.menu = false;
    }

    async add(method) {
        if (this.ui.busy) {
            return;
        }
        this.ui.busy = true;
        try {
            await this.record.data.method_ids.addAndRemove({ add: [method.id] });
            if (!this.termOf(method)) {
                await this.terms.addNewRecord({
                    context: { default_method_id: method.id },
                    position: "bottom",
                });
            }
            this.select(method);
        } finally {
            this.ui.busy = false;
        }
    }

    async remove(method) {
        if (this.ui.busy) {
            return;
        }
        this.ui.busy = true;
        try {
            const term = this.termOf(method);
            if (term) {
                await this.terms.delete(term);
            }
            await this.record.data.method_ids.addAndRemove({ remove: [method.id] });
            if (this.ui.active === method.id) {
                this.ui.active = false;
            }
        } finally {
            this.ui.busy = false;
        }
    }

    /** Строки условий у старых объявлений могло не быть — заводим по первому вводу. */
    async ensureTerm() {
        let term = this.term;
        if (!term && this.current) {
            term = await this.terms.addNewRecord({
                context: { default_method_id: this.current.id },
                position: "bottom",
            });
        }
        return term;
    }

    async onInput(name, ev) {
        const term = await this.ensureTerm();
        if (!term) {
            return;
        }
        let value = ev.target.value;
        const field = this.extraFields.find((f) => f.name === name);
        const kind = field ? field.kind : ["price", "deposit"].includes(name) ? "money" : "text";
        if (NUMERIC.includes(kind)) {
            value = parseFloat(String(value).replace(/\s/g, "").replace(",", ".")) || 0;
            if (kind === "int") {
                value = Math.round(value);
            }
        } else if (kind === "date") {
            value = value ? DateTime.fromISO(value) : false;
        } else if (!value) {
            value = false;
        }
        await term.update({ [name]: value });
    }
}

registry.category("fields").add("coop_method_tabs", {
    component: CoopMethodTabs,
    supportedTypes: ["one2many"],
    relatedFields: [
        { name: "method_id", type: "many2one", relation: "coop.resource.method" },
        { name: "price_kind", type: "selection" },
        { name: "price", type: "monetary" },
        { name: "price_unit_label", type: "char" },
        { name: "deposit", type: "monetary" },
        { name: "min_term", type: "char" },
        { name: "note", type: "char" },
        { name: "currency_id", type: "many2one", relation: "res.currency" },
        ...[["min_qty", "float"], ["bulk_qty", "float"], ["bulk_price", "monetary"],
            ["prepay_pct", "integer"], ["warranty", "char"], ["documents", "selection"],
            ["max_term", "char"], ["operator", "selection"], ["included", "char"],
            ["available_from", "date"], ["long_discount", "char"], ["down_pct", "float"],
            ["months", "integer"], ["pay_every", "selection"], ["markup_pct", "float"],
            ["ownership", "selection"], ["buyout", "monetary"], ["payment_manual", "monetary"],
            ["lessor", "selection"], ["lessor_name", "char"], ["insurance", "selection"],
            ["contribution", "selection"], ["expect", "selection"], ["project_scope", "char"],
            ["surcharge", "selection"], ["surcharge_amount", "monetary"],
            ["free_mode", "selection"], ["free_to", "selection"]].map(([name, type]) => ({ name, type })),
    ],
});
