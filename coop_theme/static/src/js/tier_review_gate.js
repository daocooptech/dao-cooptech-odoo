/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Значок «Проверки» (карандаш на блокноте) — только тому, у кого есть что
 * согласовывать (решение 415, п. 1).
 *
 * Значок — из модуля OCA `base_tier_validation` (многоуровневое
 * согласование документов), его тянут модули Rudoo. На узле модуль
 * стоит, а правил согласования нет ни одного, и значок висел у всех
 * впустую. Владелец: «надо, чтобы иконка появлялась тогда, когда
 * пользователь подключил этот модуль».
 *
 * Не заплаткой на компонент, а заменой записи в реестре — наследником с
 * шаблоном-воротами: так значок появляется сам, как только на человека
 * придёт первая проверка. Службой, а не кодом модуля: к запуску служб
 * реестр уже собран из всех модулей, в каком бы порядке ни грузились
 * пакеты. Модуля нет — делать нечего.
 */
const KEY = "base_tier_validation.ReviewerMenu";

registry.category("services").add("coop_tier_review_gate", {
    start() {
        const systray = registry.category("systray");
        if (!systray.contains(KEY)) {
            return;
        }
        const item = systray.get(KEY);
        const Base = item.Component;
        class CoopTierReviewMenu extends Base {
            static template = "coop_theme.TierReviewGate";
        }
        systray.add(KEY, { ...item, Component: CoopTierReviewMenu }, { force: true });
    },
});
