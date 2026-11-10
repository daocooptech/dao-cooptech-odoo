/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, proxy, signal, useProps } from "@odoo/owl";

/**
 * Снимки объявления на витрине — дизайн-система, `Gallery`: большой
 * снимок 4:3, под ним лента миниатюр, номер «2 / 5».
 *
 * Владелец 10.11.2026: «под главным фото сделай снизу слайдер из
 * маленьких фото 2–5 в зависимости от разрешения». Сколько миниатюр
 * видно разом, решает ширина самой галереи (контейнерный запрос в
 * `gallery.scss`), остальные — прокруткой ленты и стрелками.
 *
 * Ставится на `gallery_data` (адреса собирает сервер, главный снимок
 * первым). Лента рисуется только при двух снимках и больше.
 */
export class CoopGallery extends Component {
    static template = "coop_resources.Gallery";
    props = useProps(standardFieldProps);

    setup() {
        this.state = proxy({ index: 0 });
        this.strip = signal.ref();
    }

    get images() {
        return this.props.record.data.gallery_data || [];
    }

    get current() {
        const images = this.images;
        return images[Math.min(this.state.index, images.length - 1)] || false;
    }

    select(index) {
        this.state.index = index;
        // Выбранная миниатюра — в поле зрения ленты, если ушла за край.
        const strip = this.strip();
        const thumb = strip?.children[index];
        if (strip && thumb) {
            const left = thumb.offsetLeft - strip.offsetLeft;
            if (left < strip.scrollLeft || left + thumb.offsetWidth > strip.scrollLeft + strip.clientWidth) {
                strip.scrollTo({ left: left - (strip.clientWidth - thumb.offsetWidth) / 2, behavior: "smooth" });
            }
        }
    }

    step(delta) {
        const count = this.images.length;
        if (count) {
            this.select((this.state.index + delta + count) % count);
        }
    }

    onKeydown(ev) {
        if (ev.key === "ArrowRight") {
            this.step(1);
            ev.preventDefault();
        } else if (ev.key === "ArrowLeft") {
            this.step(-1);
            ev.preventDefault();
        }
    }
}

registry.category("fields").add("coop_gallery", {
    component: CoopGallery,
    supportedTypes: ["json"],
});
