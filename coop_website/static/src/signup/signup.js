import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

const LEVELS = ["", "Слабый пароль", "Средний пароль", "Хороший пароль", "Надёжный пароль"];

/** Надёжность 0–4: длина, разные знаки. Короче восьми — всегда «слабый». */
export function passwordLevel(value) {
    if (!value) {
        return 0;
    }
    if (value.length < 8) {
        return 1;
    }
    const kinds = [/\p{Ll}/u, /\p{Lu}/u, /\d/, /[^\p{L}\d]/u].filter((re) => re.test(value)).length;
    return Math.min(4, 1 + (value.length >= 12) + (kinds >= 2) + (kinds >= 3));
}

/** Шаг 1: индикатор пароля; без согласия кнопка неактивна. */
export class CoopSignupAccount extends Interaction {
    static selector = ".coop-signup_account";
    dynamicContent = {
        "input[name='password']": { "t-on-input": this.onPassword },
        ".coop-signup_meter": { "t-att-data-level": () => this.level },
        ".coop-signup_hint": { "t-out": () => LEVELS[this.level] || this.hint },
        "input[name='pd_consent']": { "t-on-change": () => {} },
        "button[type='submit']": { "t-att-disabled": () => !this.consent.checked },
    };

    setup() {
        this.consent = this.el.querySelector("input[name='pd_consent']");
        this.hint = this.el.querySelector(".coop-signup_hint").textContent;
        this.level = passwordLevel(this.el.querySelector("input[name='password']").value);
    }

    onPassword(ev) {
        this.level = passwordLevel(ev.target.value);
    }
}

/** Шаг 2: превью фото и подсказка, с какого раздела начать. */
export class CoopSignupAbout extends Interaction {
    static selector = ".coop-signup_about";
    dynamicContent = {
        "input[name='photo']": { "t-on-change": this.onPhoto },
        ".coop-signup_interests input": { "t-on-change": this.onInterest },
    };

    onPhoto(ev) {
        const file = ev.target.files[0];
        if (file) {
            const url = URL.createObjectURL(file);
            this.registerCleanup(() => URL.revokeObjectURL(url));
            this.el.querySelector(".coop-signup_photo img").src = url;
        }
    }

    onInterest() {
        const start = this.el.querySelector(".coop-signup_start");
        const boxes = this.el.querySelectorAll(".coop-signup_interests input:checked");
        const links = [...boxes].map((box) => {
            const link = document.createElement("a");
            link.href = box.dataset.url;
            link.target = "_blank";
            link.textContent = `«${box.dataset.label}»`;
            return link;
        });
        start
            .querySelector("span")
            .replaceChildren(...links.flatMap((link, index) => (index ? [", ", link] : [link])));
        start.classList.toggle("d-none", !links.length);
    }
}

registry.category("public.interactions").add("coop_website.signup_account", CoopSignupAccount);
registry.category("public.interactions").add("coop_website.signup_about", CoopSignupAbout);
