/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, proxy, signal, useProps } from "@odoo/owl";

/**
 * Фото и видео записи в шапке витрины (`coop_media`).
 *
 * Владелец 12.11.2026 (задача 424): «везде два слайдера — фото и видео;
 * добавлять при создании и правке; нет фото или видео — заглушка; в
 * конце ленты — „+“». Уточнение того же дня: «слайдера два, но
 * отображение должно быть в одном превью» — один большой кадр, под ним
 * две ленты: миниатюры фото и плитки видео. Кадр показывает то, что
 * выбрано в любой из лент; стрелки идут по всем подряд — сначала фото,
 * потом видео. Видео — файлом или ссылкой (решение 654).
 *
 * Раскладка — дизайн-система, `Gallery`: кадр 4:3, лента миниатюр,
 * номер «2 / 5». «+» — последней плиткой ленты: видна, когда ленту
 * прокрутили до конца; только тому, кто может править запись. Новую
 * запись перед добавлением сохраняем.
 *
 * Ставится на `coop_media_data` (примесь `coop.media.mixin`).
 */
export class CoopMedia extends Component {
    static template = "coop_theme.Media";
    props = useProps(standardFieldProps);

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({ index: 0, videoForm: false, url: "", busy: false });
        this.photoStrip = signal.ref();
        this.videoStrip = signal.ref();
        this.photoInput = signal.ref();
        this.videoInput = signal.ref();
    }

    get data() {
        return this.props.record.data.coop_media_data || {};
    }
    get photos() {
        return this.data.photos || [];
    }
    get videos() {
        return this.data.videos || [];
    }
    /** Все подряд: фото, затем видео — по ним ходят стрелки. */
    get items() {
        return [
            ...this.photos.map((item) => ({ ...item, kind: "photo" })),
            ...this.videos.map((item) => ({ ...item, kind: "video" })),
        ];
    }
    get current() {
        const items = this.items;
        return items[Math.min(this.state.index, items.length - 1)] || false;
    }
    get canAdd() {
        return Boolean(this.data.can_add);
    }
    get canAddPhoto() {
        return this.canAdd && this.photos.length < 1 + ((this.data.limits || {}).photo || 12);
    }
    get canAddVideo() {
        return this.canAdd && this.videos.length < ((this.data.limits || {}).video || 8);
    }

    isOn(kind, index) {
        return this.state.index === (kind === "photo" ? index : this.photos.length + index);
    }

    select(kind, index) {
        this.state.index = kind === "photo" ? index : this.photos.length + index;
        const strip = (kind === "photo" ? this.photoStrip : this.videoStrip)();
        const thumb = strip?.children[index];
        if (strip && thumb) {
            const left = thumb.offsetLeft - strip.offsetLeft;
            if (left < strip.scrollLeft || left + thumb.offsetWidth > strip.scrollLeft + strip.clientWidth) {
                strip.scrollTo({ left: left - (strip.clientWidth - thumb.offsetWidth) / 2, behavior: "smooth" });
            }
        }
    }

    step(delta) {
        const count = this.items.length;
        if (count) {
            const next = (this.state.index + delta + count) % count;
            const photos = this.photos.length;
            this.select(next < photos ? "photo" : "video", next < photos ? next : next - photos);
        }
    }

    onKeydown(ev) {
        if (ev.target.closest("input")) {
            return;
        }
        if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
            this.step(ev.key === "ArrowRight" ? 1 : -1);
            ev.preventDefault();
        }
    }

    pickPhoto() {
        this.photoInput()?.click();
    }
    openVideoForm() {
        this.state.videoForm = true;
        this.state.url = "";
    }
    closeVideoForm() {
        this.state.videoForm = false;
    }
    pickVideoFile() {
        this.videoInput()?.click();
    }

    readFile(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(file);
        });
    }

    /** Новую запись сохраняем: фото и видео вешаются на её номер. */
    async ensureSaved() {
        const record = this.props.record;
        if (record.isNew || record.dirty) {
            const saved = await record.save();
            if (saved === false || record.isNew) {
                return false;
            }
        }
        return record.resId;
    }

    async add(kind, values) {
        this.state.busy = true;
        try {
            const resId = await this.ensureSaved();
            if (!resId) {
                return false;
            }
            await this.orm.call(this.props.record.resModel, "coop_media_add", [[resId]], { kind, ...values });
            await this.props.record.load();
            return true;
        } catch (error) {
            const message = error?.data?.message || error?.message || String(error);
            this.notification.add(message, { type: "danger" });
            return false;
        } finally {
            this.state.busy = false;
        }
    }

    async onPhotoFiles(ev) {
        const files = [...(ev.target.files || [])];
        ev.target.value = "";
        let added = false;
        for (const file of files) {
            if (!file.type.startsWith("image/")) {
                this.notification.add(`«${file.name}» — не снимок.`, { type: "warning" });
                continue;
            }
            if (!(await this.add("photo", { data: await this.readFile(file), name: file.name }))) {
                break;
            }
            added = true;
        }
        if (added) {
            this.select("photo", Math.max(0, this.photos.length - 1));
        }
    }

    async onVideoFile(ev) {
        const file = ev.target.files?.[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        const limit = this.data.video_mb || 50;
        if (file.size > limit * 1024 * 1024) {
            this.notification.add(`Файл видео — не больше ${limit} МБ. Большое видео лучше дать ссылкой.`, { type: "warning" });
            return;
        }
        const ok = await this.add("video", {
            data: await this.readFile(file), name: file.name, mimetype: file.type || "video/mp4",
        });
        if (ok) {
            this.state.videoForm = false;
            this.select("video", Math.max(0, this.videos.length - 1));
        }
    }

    async addVideoUrl() {
        const url = this.state.url.trim();
        if (!url) {
            return;
        }
        if (await this.add("video", { url })) {
            this.state.videoForm = false;
            this.select("video", Math.max(0, this.videos.length - 1));
        }
    }

    onUrlKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.addVideoUrl();
        } else if (ev.key === "Escape") {
            this.closeVideoForm();
        }
    }
}

registry.category("fields").add("coop_media", {
    component: CoopMedia,
    supportedTypes: ["json"],
});
