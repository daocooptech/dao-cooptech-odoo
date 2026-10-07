import { registry } from "@web/core/registry";
import {
    BooleanToggleField,
    booleanToggleField,
} from "@web/views/fields/boolean_toggle/boolean_toggle_field";

/**
 * Переключатель, который сохраняет себя сам.
 *
 * Поля на страницах платформы сохраняются сразу (`coop_inline`), а
 * штатный `boolean_toggle` движка 20 только меняет запись и ждёт общего
 * «Сохранить», которого на странице нет: приложения организации
 * переключались на экране и не доходили до сервера (замер 08.10.2026).
 */
export class CoopAutosaveToggleField extends BooleanToggleField {
    async onChange(newValue) {
        await super.onChange(newValue);
        await this.props.record.save();
    }
}

// Класс штатного переключателя — вручную: движок вешает на поле класс
// по имени виджета, и без `o_field_boolean_toggle` вместо переключателя
// рисовался флажок.
registry.category("fields").add("coop_autosave_toggle", {
    ...booleanToggleField,
    component: CoopAutosaveToggleField,
    additionalClasses: [...booleanToggleField.additionalClasses, "o_field_boolean_toggle"],
});
