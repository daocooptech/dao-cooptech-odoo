/** @odoo-module **/

import { reactive } from "@odoo/owl";

/**
 * Порядок в каталоге.
 *
 * По умолчанию — сначала новые. Раньше проекты шли по готовности убыв., и
 * первая страница была сплошь стопроцентная: со стороны это выглядело
 * так, будто полоса готовности сломана и всегда полная.
 *
 * Признаки перечислены по разделам: у проекта осмысленна готовность, у
 * сообщества — число участников, у ресурса — цена. Общий список из
 * «названия и даты» не дал бы найти ни самый собранный проект, ни самое
 * людное сообщество.
 *
 * Живёт отдельным файлом, потому что порядок выбирают в панели фильтров,
 * а применяет его представление: держи это состояние в любом из двух —
 * получишь круговой импорт, и модуль загрузится наполовину собранным.
 */
const SORT_OPTIONS = {
    "coop.project": [
        ["id desc", "Сначала новые"],
        ["name asc", "По названию"],
        ["city asc", "По городу"],
        ["readiness desc", "Сначала собранные"],
        ["readiness asc", "Сначала те, где нужна помощь"],
    ],
    "coop.community": [
        ["id desc", "Сначала новые"],
        ["name asc", "По названию"],
        ["city asc", "По городу"],
        ["member_count desc", "Сначала людные"],
    ],
    "coop.resource": [
        ["id desc", "Сначала новые"],
        ["name asc", "По названию"],
        ["city asc", "По городу"],
    ],
    "coop.skill.offer": [
        ["id desc", "Сначала новые"],
        ["name asc", "По названию"],
        ["city asc", "По городу"],
    ],
    "coop.vacancy": [
        ["id desc", "Сначала новые"],
        ["name asc", "По названию"],
        ["city asc", "По городу"],
    ],
    "coop.deal": [
        ["id desc", "Сначала новые"],
        ["name asc", "По номеру"],
    ],
    "res.partner": [
        ["id desc", "Сначала новые"],
        ["name asc", "По имени"],
        ["city asc", "По городу"],
    ],
};

const DEFAULT_SORT = [["id desc", "Сначала новые"], ["name asc", "По названию"]];

export function coopSortOptionsFor(resModel) {
    return SORT_OPTIONS[resModel] || DEFAULT_SORT;
}

// Выбранный порядок — по разделу: возвращаясь в каталог, человек
// рассчитывает увидеть тот же порядок, а не сброшенный.
export const coopSort = reactive({ orders: {} });

export function setCoopSort(resModel, order) {
    coopSort.orders = { ...coopSort.orders, [resModel]: order };
}

export function parseOrder(order) {
    return order.split(",").map((part) => {
        const [name, direction] = part.trim().split(/\s+/);
        return { name, asc: direction !== "desc" };
    });
}
