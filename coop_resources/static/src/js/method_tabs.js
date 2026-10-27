/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";

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

/** Что спрашивать у каждого способа. Подписи — как в макете и в коде. */
const LAYOUT = {
    sale: { price: "Цена, ₽", unit: true, note: "Оплата, доставка, документы" },
    rent: { price: "Цена, ₽", unit: true, deposit: true, term: "Минимальный срок",
            note: "Что входит, как вернуть" },
    installment: { price: "Цена, ₽", unit: true, term: "Срок рассрочки",
                   note: "Первый взнос, график платежей" },
    leasing: { price: "Цена, ₽", unit: true, term: "Срок лизинга",
               note: "Через кого, первый взнос" },
    barter: { price: "Оценка, ₽", note: "Что возьмёте взамен", noteFirst: true },
    free: { note: "Кому и как отдаёте", noteFirst: true },
    project: { price: "Оценка вклада, ₽", note: "В какой проект, на каких условиях" },
};

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
        if (["price", "deposit"].includes(name)) {
            value = parseFloat(String(value).replace(/\s/g, "").replace(",", ".")) || 0;
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
    ],
});
