/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";

/**
 * Подключение кошелька TON.
 *
 * Ключи остаются у участника: платформа получает от кошелька только
 * адрес и запоминает его. Подписывать транзакции она не может и не
 * должна — иначе это распоряжение чужим имуществом, а не учёт.
 *
 * Библиотека лежит в модуле, а не тянется из сети: платформа должна
 * работать и там, где до внешних сайтов не дотянуться.
 */

const LIB = "/coop_tokenomics/static/src/lib/tonconnect-ui.min.js";
let loading = null;

/** Загрузить библиотеку один раз на страницу. */
function loadLibrary() {
    if (window.TON_CONNECT_UI) {
        return Promise.resolve(window.TON_CONNECT_UI);
    }
    if (!loading) {
        loading = new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src = LIB;
            script.onload = () => resolve(window.TON_CONNECT_UI);
            script.onerror = () => reject(new Error(_t("Не удалось загрузить библиотеку кошелька.")));
            document.head.appendChild(script);
        });
    }
    return loading;
}

let ui = null;

/** Единственный экземпляр на страницу: второй перехватывает события первого. */
async function getUi() {
    if (ui) {
        return ui;
    }
    const lib = await loadLibrary();
    if (!lib || !lib.TonConnectUI) {
        throw new Error(_t("Библиотека кошелька загрузилась не полностью."));
    }
    ui = new lib.TonConnectUI({
        manifestUrl: `${browser.location.origin}/tonconnect-manifest.json`,
        language: "ru",
    });
    return ui;
}

/**
 * Открыть выбор кошелька и запомнить адрес.
 *
 * Возвращает адрес или null, если участник закрыл окно. Ошибку не
 * глотаем: «ничего не произошло» после нажатия кнопки — худший из
 * возможных ответов.
 */
export async function connectTonWallet() {
    const connect = await getUi();
    if (connect.connected) {
        await connect.disconnect();
    }
    await connect.openModal();
    const wallet = await new Promise((resolve) => {
        const unsubscribe = connect.onStatusChange((w) => {
            unsubscribe();
            resolve(w);
        });
    });
    if (!wallet || !wallet.account) {
        return null;
    }
    const result = await rpc("/coop/ton/connected", {
        address: wallet.account.address,
        network: wallet.account.chain,
    });
    if (!result.ok) {
        throw new Error(result.error || _t("Платформа не приняла адрес кошелька."));
    }
    return result;
}

/** Отвязать кошелёк на стороне кошелька — адрес на сервере снимает форма. */
export async function disconnectTonWallet() {
    const connect = await getUi();
    if (connect.connected) {
        await connect.disconnect();
    }
}
