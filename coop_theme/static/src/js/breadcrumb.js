/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { Breadcrumbs } from "@web/search/breadcrumbs/breadcrumbs";
import { onWillStart, useState } from "@odoo/owl";

/**
 * Путь и кнопка возврата.
 *
 * Пока полки открывали записи всплывающим окном, глубже одного уровня
 * не уходили, и путь был украшением: одна крошка, повторяющая заголовок
 * страницы. С переходом полок на страницы (решение 330) вложенность
 * стала настоящей — «Моя страница → организация → состав → членство», —
 * и выяснилось, что возвращаться нечем.
 *
 * У движка кнопка возврата есть, но это два разных существа под одним
 * именем: на узком экране (до 767 точек) — круглая стрелка вместо всего
 * пути, шире — просто класс на последней крошке-предке. Разметка при
 * этом меняется на 767, а вся наша вёрстка считает экран узким с 900:
 * в полосе между ними получается ни то ни сё.
 *
 * Поэтому кнопка здесь своя, одна на все ширины, а штатная убирается.
 *
 * Куда она ведёт — три случая:
 *
 *   1. Есть предок — к нему. Зовём его же `onSelected`, то есть идём по
 *      стеку действий в памяти, а не по адресу: имя экрана при этом не
 *      теряется (в отличие от браузерного «назад», см. вопрос о разделах
 *      с одним адресом на всех).
 *   2. Предка нет, но экран открыт по прямой ссылке и принадлежит
 *      разделу — в каталог раздела, и кнопка так и называется. Случай
 *      частый: ссылку на карточку присылают в переписке.
 *   3. Ни того, ни другого (сам каталог, «Моя страница») — кнопки нет
 *      вовсе, а не спрятана. Кнопка, ведущая туда, где ты стоишь, — ложь.
 */
patch(Breadcrumbs.prototype, {
    setup() {
        super.setup(...arguments);
        this.coopMenus = useService("menu");
        this.coopNotification = useService("notification");
        this.coopBoot = useService("coopBoot");
        this.coopActionService = useService("action");
        // Разделы бокового меню — чтобы найти раздел по модели записи,
        // когда действие не опознано (прямая ссылка). Список приходит
        // общим запросом запуска оболочки, второй раз он бесплатен.
        this.coopItems = useState({ list: [] });
        onWillStart(async () => {
            try {
                this.coopItems.list = (await this.coopBoot.get()).sidebar || [];
            } catch {
                // Не пришло — кнопка просто не найдёт раздел по модели.
                this.coopItems.list = [];
            }
        });
    },

    /** Ближайший предок в пути, если он есть. */
    get coopParent() {
        const list = this.props.breadcrumbs || [];
        return list.length > 1 ? list.at(-2) : null;
    },

    /**
     * Каталог раздела, которому принадлежит открытое действие.
     *
     * Раздел ищется так же, как его ищет строка вкладок: по действию
     * среди пунктов меню, оттуда — приложение, оттуда — первая вкладка.
     * Возвращается пусто, если мы и так в ней: вести в каталог из
     * каталога незачем.
     */
    /** Пункт меню, которому принадлежит открытое действие, если он есть. */
    /** Какое действие открыто сейчас. */
    get coopActionId() {
        // Настройка экрана знает его не всегда: в момент первой
        // отрисовки полоса управления о нём ещё не осведомлена. Служба
        // действий знает всегда — тем же запасным путём идёт и строка
        // вкладок.
        return (
            this.env.config?.actionId ||
            this.coopActionService?.currentController?.action?.id ||
            null
        );
    },

    get coopOwnMenu() {
        const actionId = this.coopActionId;
        return actionId
            ? this.coopMenus.getAll().find((menu) => menu.actionID === actionId)
            : null;
    },

    /**
     * Запасной выход нужен только с карточки записи.
     *
     * Вкладки раздела — соседи, а не предки: стоя на «Моих ресурсах»,
     * человек не «внутри каталога ресурсов», и кнопка «в каталог» там
     * читалась бы как возврат из вложенности, которой нет. Переключают
     * вкладки строкой вкладок.
     */
    get coopIsRecord() {
        return this.env.config?.viewType === "form";
    },

    get coopSection() {
        if (!this.coopIsRecord) {
            return null;
        }
        const own = this.coopOwnMenu;
        // Только по своему действию. Соблазн был спросить «какой раздел
        // открыт сейчас» (`getCurrentApp`), но служба помнит последний
        // выбранный пункт, а не тот, которому принадлежит запись: с
        // прямой ссылки на ресурс кнопка вела на «Мою страницу» — туда,
        // где человек был до того, как открыл ссылку. По модели ниже
        // ответ получается верный.
        if (!own) {
            return null;
        }
        const first = (this.coopMenus.getMenuAsTree(own.appID).childrenTree || [])[0];
        // Сравниваем действия, а не номера пунктов: то же самое действие
        // висит и на корне раздела, и на первой вкладке, и поиск по
        // номеру находил корень — выходило, что мы «не в каталоге», и
        // кнопка предлагала перейти туда, где человек стоит.
        if (!first || first.actionID === this.coopActionId) {
            return null;
        }
        return first;
    },

    /**
     * Раздел, опознанный по модели записи, — на случай прямой ссылки.
     *
     * Ссылку на карточку присылают в переписке: человек открывает
     * `/odoo/coop.resource/42` и оказывается на записи, у которой ни
     * предка, ни действия из меню, — то есть наружу не ведёт ничего.
     *
     * Ищем так же, как боковое меню ищет, какой пункт подсветить: по
     * модели. Одну модель могут делить два раздела («Люди» и
     * «Организации» оба стоят на контакте) — тогда не ведём никуда:
     * увести не туда хуже, чем не увести вовсе.
     */
    get coopSectionByModel() {
        if (!this.coopIsRecord) {
            return null;
        }
        // Действие знакомо меню — значит, вопрос уже решён выше: либо мы
        // в каталоге раздела и кнопка не нужна, либо раздел найден по
        // самому действию. Без этой проверки кнопка появлялась на самом
        // каталоге и предлагала перейти туда, где человек стоит.
        if (this.coopOwnMenu) {
            return null;
        }
        // Модель спрашиваем у службы действий, а не у настройки экрана:
        // в `env.config` лежат `actionId`, `actionType`, вкладки
        // представлений — модели там нет вовсе, и проверка по ней молча
        // не срабатывала: кнопка не появлялась, ошибки не было.
        const model =
            this.env.searchModel?.resModel ||
            this.coopActionService?.currentController?.action?.res_model ||
            this.env.config?.resModel;
        if (!model) {
            return null;
        }
        const подходящие = (this.coopItems.list || []).filter(
            (item) => item.model === model && item.actionId
        );
        return подходящие.length === 1 ? подходящие[0] : null;
    },

    /** Что показывает кнопка возврата, или пусто — если её нет. */
    get coopBack() {
        const parent = this.coopParent;
        if (parent) {
            return { label: parent.name || "", title: `Назад: ${parent.name || ""}` };
        }
        const section = this.coopSection;
        if (section) {
            return { label: section.name, title: `В ${section.name}` };
        }
        const byModel = this.coopSectionByModel;
        if (byModel) {
            return { label: byModel.label, title: `В ${byModel.label}` };
        }
        return null;
    },

    async coopGoBack() {
        const parent = this.coopParent;
        if (parent) {
            try {
                await parent.onSelected();
                return;
            } catch {
                // Предок мог быть удалён или закрыт правами — запись
                // членства, чужая организация. Человек при этом ничего
                // не сделал неверно, поэтому не «ошибка», а объяснение
                // и целый экран вместо сломанного.
                this.coopNotification.add(
                    "Страница, откуда вы пришли, больше не открывается. Вернули в раздел.",
                    { type: "info" }
                );
            }
        }
        const section = this.coopSection;
        if (section) {
            this.coopMenus.selectMenu(section);
            return;
        }
        const byModel = this.coopSectionByModel;
        if (byModel) {
            // Со сбросом следа: раздел — не углубление в запись, откуда
            // пришли, а выход из неё.
            this.coopActionService.doAction(byModel.actionId, { clearBreadcrumbs: true });
        }
    },
});
