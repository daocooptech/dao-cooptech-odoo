/** @odoo-module **/

import { NotificationPlugin } from "@web/core/notifications/notification_plugin";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { Breadcrumbs } from "@web/search/breadcrumbs/breadcrumbs";
import { proxy, usePlugin } from "@odoo/owl";
import { coopIsPlatformModel } from "@coop_theme/js/platform_page";
import { ActionPlugin } from "@web/webclient/actions/action_plugin";

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
        this.coopNotification = usePlugin(NotificationPlugin);
        this.coopBoot = useService("coopBoot");
        this.coopActionService = usePlugin(ActionPlugin);
        // Разделы бокового меню — чтобы найти раздел по модели записи,
        // когда действие не опознано (прямая ссылка). Список приходит
        // общим запросом запуска оболочки, второй раз он бесплатен.
        //
        // Спрашиваем без ожидания, и это главное здесь. Сначала запрос
        // стоял в `onWillStart` — и уронил боевую целиком: `onWillStart`
        // задерживает первую отрисовку компонента, компонент этот —
        // крошка, а крошка есть на каждом экране. Пока ответ не пришёл,
        // не рисовалось ничего: ни «Моя страница», ни каталог, ни
        // карточка. На стенде ответ мгновенный, и поломка не показалась
        // ни разу; на боевой запрос идёт по сети, и вкладка вставала
        // намертво без единой ошибки в журнале.
        //
        // Список нужен только кнопке возврата и только в одном случае из
        // трёх. Экран не должен ждать его ни секунды: придёт — кнопка
        // дорисуется сама, реактивное состояние вызовет перерисовку.
        this.coopItems = proxy({ list: [] });
        // Рубрика открытой записи для полного пути (№ 407). Приходит
        // отдельным запросом и тоже без ожидания — по той же причине.
        this.coopOrm = useService("orm");
        this.coopTrailState = proxy({ key: "", rubrics: [], name: "", isCompany: false });
        this.coopTrailKey = "";
        this.coopBoot
            .get()
            .then((data) => {
                this.coopItems.list = data.sidebar || [];
            })
            .catch(() => {
                // Не пришло — кнопка просто не найдёт раздел по модели.
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
        const matching = (this.coopItems.list || []).filter(
            (item) => item.model === model && item.actionId
        );
        return matching.length === 1 ? matching[0] : null;
    },

    /**
     * Открыта ли страница человека или организации.
     *
     * Отвечает теперь только за путь предков. Решение владельца
     * 21 сентября 2026: пройдя «мои друзья → друзья друга», он увидел
     * «Дашкевич → Соколов», стоя на странице Медведевой. Движок пишет в
     * путь предков, а имя открытой записи берёт из заголовка, которого
     * у карточки человека нет — имя стоит в самой странице, крупно.
     * Выходит путь, называющий кого угодно, кроме того, кто перед
     * глазами. Вместе с путём уходит и последняя крошка: она и есть это
     * пустое имя.
     *
     * Кнопка возврата остаётся: иначе со страницы человека некуда
     * деться, кроме как браузерной стрелкой. Она подписана тем, куда
     * ведёт, и на вопрос «откуда я пришёл» отвечает точнее списка имён.
     *
     * Карточка организации — та же модель и та же полоса, поэтому
     * правило одно на обе: `res.partner` в виде формы.
     *
     * Шестерёнку этот признак больше не прячет: она убрана на всех
     * страницах записей платформы, см. `coopHideActions`.
     */
    get coopIsPersonPage() {
        try {
            if (!this.coopIsRecord) {
                return false;
            }
            const model =
                this.env.searchModel?.resModel ||
                this.coopActionService?.currentController?.action?.res_model ||
                this.env.config?.resModel;
            return model === "res.partner";
        } catch (error) {
            console.warn("[крошка] не удалось решить, прятать ли путь:", error);
            return false;
        }
    },

    /**
     * Страница записи платформы, а не чужого справочника движка.
     *
     * От этого зависит, показывать ли шестерёнку — штатное «Меню
     * действий» записи. Решение владельца 21 сентября 2026 было о
     * странице человека, но причина в нём общая: меню предлагает
     * действия, которых в языке платформы нет. «Дублировать» участника,
     * «Удалить» чужой ресурс, «Отправить SMS» через неподключённый
     * платный сервис — всё это про таблицу в базе, а не про человека,
     * ресурс или сделку.
     *
     * Само правило — в `platform_page.js`, общее с полосой сохранения
     * внизу формы: два списка правды разошлись бы при первой же правке,
     * и разошлись бы молча.
     *
     * Печать при этом наружу выведена отдельно: у сделки договор и акт
     * были только в этом меню, и на форму добавлены свои кнопки. Если
     * к какой-то модели привяжут отчёт или действие, не заведя кнопку
     * на странице, оно станет недостижимым молча — проверять при
     * добавлении.
     */
    get coopHideActions() {
        try {
            if (!this.coopIsRecord) {
                return false;
            }
            const model =
                this.env.searchModel?.resModel ||
                this.coopActionService?.currentController?.action?.res_model ||
                this.env.config?.resModel;
            return coopIsPlatformModel(model);
        } catch (error) {
            console.warn("[крошка] не удалось решить, прятать ли меню:", error);
            return false;
        }
    },

    /**
     * Что показывает кнопка возврата, или пусто — если её нет.
     *
     * Всё вычисление обёрнуто: getter зовётся на каждой отрисовке крошки,
     * а крошка стоит на каждом экране. Брошенное отсюда исключение — это
     * не «кнопка не нарисовалась», а сорванная отрисовка всей страницы, и
     * дальше как повезёт: пустой экран или петля перерисовки. Кнопка
     * возврата не стоит такой цены — не сосчиталась, значит её нет.
     */
    get coopBack() {
        try {
            const parent = this.coopParent;
            if (parent) {
                // «Я инициатор» и «Я участвую» — вкладки раздела «Проекты», а
                // не место в пути (владелец 14.11.2026: «в пути не надо
                // инициатор или участник — проекты, дальше раздел и подраздел»).
                const name = COOP_TAB_ROOT[parent.name] || parent.name || "";
                return { label: name, title: `Назад: ${name}` };
            }
            const section = this.coopSection;
            if (section) {
                return { label: section.name, title: `В ${section.name}` };
            }
            const byModel = this.coopSectionByModel;
            if (byModel) {
                return { label: byModel.label, title: `В ${byModel.label}` };
            }
        } catch (error) {
            console.warn("[крошка] кнопка возврата не сосчиталась:", error);
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

    // ── Полный путь на странице записи (№ 407) ──────────────────────────
    //
    // Владелец 10.11.2026 на витрине «Молоковоза»: «почему я не вижу
    // полного пути?» — в шапке стояло одно «← Ресурсы ›». По эталону
    // (`ResourcePage` → `Crumbs`) путь доходит до записи через рубрику:
    // «Ресурсы › Продовольственные товары › Мёд натуральный липовый».

    /** Открытая запись платформы — модель и номер, или пусто. */
    get coopRecordRef() {
        if (!this.coopIsRecord) {
            return null;
        }
        const root = this.env.model?.root;
        const model = root?.resModel;
        const resId = root?.resId;
        // Только витрины с рубрикой: ресурс, навык, вакансия, проект,
        // человек и организация. У кошелька, сделки и прочих записей
        // пустую полосу убирали намеренно (12.10.2026).
        if (!model || !resId || !coopIsPlatformModel(model) || !COOP_RUBRICS[model]) {
            return null;
        }
        return { model, resId };
    },

    /**
     * Путь до записи, если он есть. Рубрика подгружается при смене
     * записи, а не при каждой отрисовке: запрос уходит один раз на
     * запись, ответ дорисовывает путь сам — состояние реактивное.
     */
    get coopTrail() {
        try {
            const ref = this.coopRecordRef;
            if (!ref) {
                return null;
            }
            const key = `${ref.model}:${ref.resId}`;
            if (this.coopTrailKey !== key) {
                this.coopTrailKey = key;
                // Писать в состояние посреди отрисовки нельзя — после неё.
                Promise.resolve().then(() => this.coopLoadTrail(ref, key));
            }
            return this.coopTrailState;
        } catch (error) {
            console.warn("[крошка] путь до записи не сосчитался:", error);
            return null;
        }
    },

    async coopLoadTrail({ model, resId }, key) {
        const spec = COOP_RUBRICS[model];
        const state = this.coopTrailState;
        state.key = key;
        state.rubrics = [];
        state.name = "";
        try {
            const fields = ["display_name", ...(spec ? spec.fields : [])];
            if (model === "res.partner") {
                fields.push("is_company");
            }
            const [record] = await this.coopOrm.read(model, [resId], fields);
            if (!record || this.coopTrailKey !== key) {
                return;
            }
            const rubrics = [];
            for (const field of spec ? spec.fields : []) {
                const value = record[field];
                if (!value) {
                    // Нет верхнего уровня — нижний без него не показываем:
                    // «Проекты › Раздел» без темы читается как тема.
                    break;
                }
                rubrics.push({ field, id: value[0], name: value[1], tree: false });
            }
            // Рубрика ресурса — дерево: «Транспорт › Грузовики и автобусы».
            // Предки — по `parent_path`, одним запросом.
            if (spec?.tree && rubrics.length) {
                const [own] = await this.coopOrm.read(spec.tree, [rubrics[0].id], ["parent_path"]);
                const ids = (own?.parent_path || "").split("/").filter(Boolean).map(Number);
                if (ids.length > 1 && this.coopTrailKey === key) {
                    const rows = await this.coopOrm.read(spec.tree, ids, ["name"]);
                    const byId = new Map(rows.map((row) => [row.id, row.name]));
                    rubrics.splice(0, 1, ...ids.map((id) => ({
                        field: rubrics[0].field, id, name: byId.get(id) || "", tree: true,
                    })));
                }
            }
            if (this.coopTrailKey !== key) {
                return;
            }
            // Без повторов: у навыка специализация и есть его название
            // («Бизнес-консультант › Бизнес-консультант»), у вакансии
            // сфера и специализация бывают одним словом («Разнорабочий ›
            // Разнорабочий»).
            const name = record.display_name || "";
            state.rubrics = rubrics.filter((rubric, index) =>
                rubric.name !== name && (index === 0 || rubric.name !== rubrics[index - 1].name));
            state.name = name;
            state.isCompany = Boolean(record.is_company);
        } catch (error) {
            // Не пришло — путь остаётся без рубрики, запись открыта.
            console.warn("[крошка] рубрика не подгрузилась:", error);
        }
    },

    /**
     * Раздел в начале пути, когда предков нет (прямая ссылка) или они
     * не показываются (страница человека и организации). У контакта
     * разделов два — «Люди» и «Организации», выбираем по самой записи.
     */
    get coopTrailSection() {
        try {
            const ref = this.coopRecordRef;
            if (ref?.model === "res.partner") {
                const want = this.coopTrailState.isCompany ? /организац/i : /люди/i;
                const item = (this.coopItems.list || []).find(
                    (entry) => entry.model === "res.partner" && entry.actionId && want.test(entry.label || "")
                );
                return item ? { label: item.label, actionId: item.actionId } : null;
            }
            const section = this.coopSection;
            if (section) {
                return { label: section.name, menu: section };
            }
            const byModel = this.coopSectionByModel;
            if (byModel) {
                return { label: byModel.label, actionId: byModel.actionId };
            }
            const own = this.coopOwnMenu;
            if (own) {
                const app = this.coopMenus.getMenu(own.appID);
                return app ? { label: app.name, menu: null } : null;
            }
        } catch (error) {
            console.warn("[крошка] раздел пути не сосчитался:", error);
        }
        return null;
    },

    /**
     * Рубрики ставятся между разделом и записью — если путь начинается с
     * раздела. Пришли с «Моей страницы» — путь «Моя страница › Молоковоз»:
     * рубрика между ними объясняла бы не то, откуда человек пришёл.
     */
    get coopRubricsHere() {
        const parent = this.coopParent;
        if (!parent || this.coopIsPersonPage) {
            return true;
        }
        const labels = new Set();
        const section = this.coopTrailSection;
        if (section) {
            labels.add(section.label);
        }
        const own = this.coopOwnMenu;
        if (own) {
            labels.add(own.name);
            const app = this.coopMenus.getMenu(own.appID);
            if (app) {
                labels.add(app.name);
            }
        }
        const model = this.coopRecordRef?.model;
        for (const item of this.coopItems.list || []) {
            if (item.model === model) {
                labels.add(item.label);
            }
        }
        return labels.has(parent.name);
    },

    coopOpenSection() {
        const section = this.coopTrailSection;
        if (section?.menu) {
            this.coopMenus.selectMenu(section.menu);
        } else if (section?.actionId) {
            this.coopActionService.doAction(section.actionId, { clearBreadcrumbs: true });
        } else {
            this.coopGoBack();
        }
    },

    /**
     * Рубрика ведёт в каталог, отобранный по ней. Так же, как «Смотреть
     * все» у полок: через действие с доменом, а не через строку поиска.
     * Вид и настройки каталога берутся у открытого действия — запись,
     * открытая из каталога, живёт в его же действии.
     */
    async coopOpenRubric(rubric) {
        const ref = this.coopRecordRef;
        if (!ref) {
            return;
        }
        // Отбор встаёт в путь вместо записи, а не после неё: «Ресурсы ›
        // Недвижимость», а не «Ресурсы › участок › Недвижимость». Замена
        // действия движком тут не годится — запись живёт в действии
        // каталога, и вместе с ней ушёл бы весь каталог. Поэтому сначала
        // шаг назад к предку, потом отбор.
        const parent = this.coopParent;
        const options = {};
        if (parent && !this.coopIsPersonPage) {
            try {
                const action = this.coopActionService?.currentController?.action || {};
                // `onSelected` предка обещания не возвращает — шаг назад
                // ждём через службу, иначе отбор встаёт после записи.
                await this.coopActionService.restore(parent.jsId);
                return this.coopDoRubric(rubric, ref, action, options);
            } catch {
                // Предок не открылся — открываем отбор с чистого пути.
            }
        }
        options.clearBreadcrumbs = true;
        return this.coopDoRubric(rubric, ref, this.coopActionService?.currentController?.action || {}, options);
    },

    coopDoRubric(rubric, ref, action, options) {
        const own = action.res_model === ref.model;
        const domain = [[rubric.field, rubric.tree ? "child_of" : "=", rubric.id]];
        if (own && Array.isArray(action.domain)) {
            domain.push(...action.domain);
        }
        if (ref.model === "res.partner") {
            domain.push(["is_company", "=", this.coopTrailState.isCompany]);
        }
        // Действие каталога взято до шага назад и передано сюда: после
        // шага открыт уже каталог, а не запись.
        return this.coopActionService.doAction({
            type: "ir.actions.act_window",
            name: rubric.name,
            res_model: ref.model,
            domain,
            context: own ? action.context || {} : {},
            views: [[false, "kanban"], [false, "list"], [false, "form"]],
        }, options);
    },
});

/**
 * Какие поля — рубрика записи, сверху вниз. `tree` — у рубрики есть
 * предки, их тоже показываем.
 */
// Вкладки «Моих проектов»: в пути стоит раздел, а не вкладка.
const COOP_TAB_ROOT = { "Я инициатор": "Проекты", "Я участвую": "Проекты" };

const COOP_RUBRICS = {
    "coop.resource": { fields: ["category_id"], tree: "coop.resource.category" },
    "coop.project": { fields: ["category_id", "subcategory_id"] },
    "coop.skill.offer": { fields: ["coop_specialization_category_id", "coop_specialization_id"] },
    "coop.vacancy": { fields: ["coop_specialization_category_id", "coop_specialization_id"] },
    "res.partner": { fields: ["coop_specialization_category_id", "coop_specialization_id"] },
};
