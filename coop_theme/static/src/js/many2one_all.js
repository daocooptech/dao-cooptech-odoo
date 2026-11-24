/** @odoo-module **/
// Выбор из короткого справочника целиком (№ 487). Движок показывает восемь
// строк и прячет остальное под «Искать больше…»: владелец 25.11.2026 не
// нашёл в списке форм акционерных обществ. Справочник форм невелик —
// показываем весь.
import { registry } from "@web/core/registry";
import { Many2One } from "@web/views/fields/many2one/many2one";
import { buildM2OFieldDescription, Many2OneField } from "@web/views/fields/many2one/many2one_field";

class Many2OneAll extends Many2One {
    get many2XAutocompleteProps() {
        return { ...super.many2XAutocompleteProps, searchLimit: 200 };
    }
}

class Many2OneAllField extends Many2OneField {
    static components = { ...Many2OneField.components, Many2One: Many2OneAll };
}

registry.category("fields").add("coop_many2one_all", {
    ...buildM2OFieldDescription(Many2OneAllField),
    // Стили движка и темы висят на классе по имени виджета.
    additionalClasses: ["o_field_many2one"],
});
