/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { imageUrl } from "@web/core/utils/urls";
import { session } from "@web/session";
import { BurgerMenu } from "@web/webclient/burger_menu/burger_menu";
import { UserMenu } from "@web/webclient/user_menu/user_menu";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";

/**
 * Выбор, от чьего имени человек действует, — в меню под аватаром.
 *
 * Раньше это был отдельный список в боковом меню, а рядом, в шапке,
 * движок показывал название компании. Два списка организаций в разных
 * углах экрана отвечали на один вопрос разными словами, и понять, чем
 * они отличаются, было нельзя.
 *
 * Теперь выбор один и лежит там, где его ищут, — под своим аватаром,
 * рядом с выходом и настройками. Строки — с фотографией и названием:
 * человека и кооператив различают в лицо, а не по строчке текста.
 */
export class CoopActingMenu extends Component {
    static template = "coop_theme.ActingMenu";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.boot = useService("coopBoot");
        this.state = proxy({ actors: [], acting: null });
        onWillStart(() => this.load());
    }

    async load() {
        try {
            // Тот же запуск, что и у бокового меню: список лиц
            // спрашивался дважды — здесь и там.
            const info = (await this.boot.get()).acting || {};
            this.state.actors = info.options || [];
            this.state.acting = info.current || null;
        } catch {
            // Права или сеть — выбора просто не будет, меню от этого не
            // ломается.
            this.state.actors = [];
        }
    }

    avatar(actor) {
        return `/web/image/res.partner/${actor.id}/avatar_128`;
    }

    async select(actor) {
        if (actor.id === this.state.acting) {
            return;
        }
        await this.orm.call("coop.shell", "set_acting", [actor.id]);
        // Перезагрузка целиком: от имени зависит почти всё на экране —
        // своя страница, кошелёк, каталоги «мои». Досчитывать это по
        // кусочкам значило бы держать вторую копию тех же правил.
        //
        // «Моя страница» в адресе несёт номер карточки (`/my-page/11`), и
        // перезагрузка того же адреса снова открывала прежнее лицо:
        // выбрали ПК «Родник» — а на экране страница человека (владелец
        // 12.10.2026). Без номера страницу выбирает сервер — по новому лицу.
        //
        // Номер держит и сам движок: последнее действие с его ответом он
        // хранит во вкладке (`current_action`, `current_state`) и после
        // перезагрузки берёт оттуда, не спрашивая сервер. Сбрасываем.
        try {
            window.sessionStorage.removeItem("current_action");
            window.sessionStorage.removeItem("current_state");
        } catch {
            // Хранилище закрыто — помнить движку тоже нечем.
        }
        const path = window.location.pathname;
        const myPage = path.match(/^(.*\/my-page)\/\d+/);
        if (myPage) {
            window.location.assign(myPage[1]);
        } else {
            window.location.reload();
        }
    }
}

/**
 * Аватар в шапке — того, от чьего имени действуешь (задача 299).
 *
 * Движок и `mail` рисуют там человека всегда: выбрал организацию — а в
 * углу по-прежнему своё лицо, и «кто я сейчас» видно только в меню.
 * Действуешь от себя — остаётся аватар `mail` с отметкой «в сети»;
 * от организации — её знак, без отметки: «в сети» у кооператива не бывает.
 * Лицо берётся из `session_info` (`coop_acting`), а не запросом: шапка
 * рисуется сразу, и до ответа в углу мелькнул бы человек.
 */
function actingAvatar() {
    const acting = session.coop_acting;
    return acting
        ? imageUrl("res.partner", acting.id, "avatar_128", { unique: acting.write_date })
        : null;
}

patch(UserMenu.prototype, {
    setup() {
        super.setup();
        this.coopActingAvatar = actingAvatar();
    },
});

// Та же картинка на телефоне — кнопка выдвижного меню в шапке.
patch(BurgerMenu.prototype, {
    setup() {
        super.setup();
        this.coopActingAvatar = actingAvatar();
    },
});

// Первым в меню: это ответ на вопрос «кто я сейчас», а он предшествует
// всему остальному — настройкам, справке и выходу.
registry.category("user_menuitems").add("coop_theme.acting", () => ({
    type: "component",
    contentComponent: CoopActingMenu,
    sequence: 1,
}));

// «О платформе» (до 20.10.2026 — «О программе») — лицензия движка и ссылка на исходник той версии, что
// работает (решение 442; LGPL-3, GPL-3 §5(d), §6(d)). Страница публичная,
// открывается в новой вкладке, чтобы не терять место в кабинете.
registry.category("user_menuitems").add("coop_theme.about", () => ({
    type: "item",
    id: "coop_about",
    description: "О платформе",
    href: "/about/software",
    callback: () => window.open("/about/software", "_blank"),
    sequence: 65,
}));

// Переключатель компаний движка убран: он отвечает на тот же вопрос
// «от чьего имени я работаю», но словами учётной системы, и рядом с
// нашим выглядел вторым, непонятно чем отличающимся списком.
registry.category("systray").remove("SwitchCompanyMenu");
