/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useInputField } from "@web/views/fields/input_field_hook";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { CharField } from "@web/views/fields/char/char_field";

import { Component, signal, t, useProps } from "@odoo/owl";

export class SearchField extends Component {
    static template = "dadata_connector.SearchField";
    props = useProps({
        ...standardFieldProps,
        placeholder: t.string().optional(),
    });
    // Owl 3: ссылка — сигнал, а не имя в t-ref (как у CharField в 20).
    input = signal.ref();

    setup() {
        useInputField({
            getValue: () => this.props.record.data[this.props.name] || "",
            ref: this.input,
        });
        this.action = null;
    }

    async search() {
        const record = this.props.record;
        this.action = await this.env.services.orm.call(
            "res.partner",
            "get_legal_entity_data",
            [record.resId],
            {
                vat: record.data[this.props.name],
            }
        );
        await this.env.services.action.doAction(this.action, {
            onClose: async (closeInfo) => {
                if (closeInfo && closeInfo.update) {
                    const { management, ...rawData } = this.action.context;
                    // Only update fields that exist in the current record's field definitions.
                    // Many2one fields must be passed as [id, display_name] tuples for OWL record.update().
                    const newRecordData = {};
                    for (const [key, value] of Object.entries(rawData)) {
                        const field = record.fields[key];
                        if (!field) continue;
                        if (field.type === "many2one" && typeof value === "number") {
                            newRecordData[key] = [value, ""];
                        } else {
                            newRecordData[key] = value;
                        }
                    }
                    await record.update({
                        ...newRecordData,
                        is_company: true,
                    });
                    await record.save();

                    const recordChildren = record.data.child_ids.records;
                    if (management && !this._checkManagerExists(recordChildren, management)) {
                        await this._createManager(management);
                    }

                    await record.load();

                    this.env.services.notification.add(_t("Data updated."), {
                        type: "info",
                    });
                }
            },
        });
    }

    _checkManagerExists(recordChildren, management) {
        const managerName = management.manager_name;
        const managerFunction = management.manager_position;
        for (let rec of recordChildren) {
            if (
                rec.data.name.toUpperCase() === managerName.toUpperCase() &&
                rec.data.function.toUpperCase() === managerFunction.toUpperCase()
            )
                return true;
        }
        return null;
    }

    async _createManager(management) {
        const record = this.props.record;
        await this.env.services.orm.call("res.partner", "create", [
            {
                name: management.manager_name,
                function: management.manager_position,
                parent_id: record.resId,
                type: "contact",
            },
        ]);
    }
}

export const searchField = {
    component: SearchField,
    displayName: _t("DaData Search"),
    supportedTypes: ["char"],
    extractProps: ({ attrs, placeholder }) => ({
        placeholder: attrs.placeholder || placeholder,
    }),
};

registry.category("fields").add("dadata_search", searchField);
