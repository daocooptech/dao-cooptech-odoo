/** @odoo-module **/

import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

/**
 * Все свои компании учёта — сразу (решения 449, 450).
 *
 * У человека с полномочием в организации есть её компания учёта, а
 * веб-клиент по умолчанию включает одну, основную, — компанию платформы.
 * Форма записи из другой компании переключает сама, а списки и воронки
 * — нет: менеджер открывал CRM и видел пустую воронку с образцами вместо
 * лидов своей организации. Включаем все разрешённые: чужих компаний в
 * списке нет, доступ к ним выдаётся только по полномочию.
 *
 * Без перезагрузки и до первого раздела: служба стартует раньше, чем
 * открывается действие, и контекст запросов уже несёт все компании.
 */
export const coopAllCompaniesService = {
    start() {
        const allowed = user.allowedCompanies.map((c) => c.id);
        const active = user.activeCompanies.map((c) => c.id);
        const missing = allowed.filter((id) => !active.includes(id));
        if (missing.length) {
            user.activateCompanies([...active, ...missing], {
                includeChildCompanies: false,
                reload: false,
            });
        }
    },
};

registry.category("services").add("coopAllCompanies", coopAllCompaniesService);
