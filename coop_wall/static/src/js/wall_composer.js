/** @odoo-module **/

import { toRaw, useState } from "@odoo/owl";
import { checkFileSize } from "@web/core/utils/files";
import { isHtmlEmpty } from "@web/core/utils/html";
import { patch } from "@web/core/utils/patch";
import { Composer } from "@mail/core/common/composer";
import { markEventHandled } from "@web/core/utils/misc";
import {
    composerActionsRegistry,
    registerComposerAction,
} from "@mail/core/common/composer_actions";
// Голосовые действия заводит модуль переписки; наши правки к ним должны
// лечь после них, а не раньше, — отсюда явный импорт.
import "@mail/discuss/voice_message/common/composer_actions_patch";
import { WALL_MODELS } from "@coop_theme/js/wall";

// Кнопки под полем записи на стене: Фото, Видео, Аудио, Голосовое, Файл.
//
// Владелец 24 сентября 2026: «а где иконки картинки, видео, аудио возле
// поля ввода текста при публикации поста на стену?» У движка под полем
// одна скрепка на всё и два служебных значка — «Вставить готовый ответ»
// (шаблоны писем) и «Открыть полный редактор» (письмо с темой и
// получателями). Для стены это инструменты чужой работы, а нужного —
// сказать «вот фото», «вот видео» — нет.
//
// Кнопки — действия того же реестра, что и скрепка: движок сам рисует их
// в ряд, с подсказками и на телефоне. Только на стенах (`WALL_MODELS`);
// в переписке и в ленте склада всё как было.
//
// Как добавляется снимок, решает кнопка, а не окно «картинкой или
// файлом» (`js/wall_photo.js`): «Фото» — картинкой, «Файл» — файлом.
// Окно остаётся для перетаскивания и вставки — там кнопки не было.

const onWall = ({ composer }) => WALL_MODELS.includes(composer?.targetThread?.model);

/**
 * Окно выбора файлов с заданным фильтром.
 *
 * Поле выбора — своё на каждый щелчок, а не одно общее в разметке: у
 * четырёх кнопок четыре разных фильтра, и держать четыре скрытых поля в
 * чужом шаблоне ради этого — лишняя правка разметки движка.
 */
function pickFiles(owner, composer, accept, optionsFor) {
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    if (accept) {
        input.accept = accept;
    }
    input.addEventListener(
        "change",
        () => {
            const notification = owner.env.services.notification;
            for (const file of input.files) {
                if (!checkFileSize(file.size, notification)) {
                    continue;
                }
                owner.attachmentUploader.uploadFile(file, optionsFor(file));
            }
        },
        { once: true }
    );
    input.click();
    toRaw(composer).autofocus++;
}

const isImage = (file) => Boolean(file.type?.startsWith("image/"));

registerComposerAction("coop-wall-photo", {
    condition: (p) => onWall(p) && p.owner.allowUpload,
    icon: "fa fa-picture-o",
    name: "Фото",
    onSelected: ({ composer, owner }, ev) => {
        markEventHandled(ev, "composer.clickOnAddAttachment");
        pickFiles(owner, composer, "image/*", () => ({ coopAsFile: false }));
    },
    sequence: 11,
});

registerComposerAction("coop-wall-video", {
    condition: (p) => onWall(p) && p.owner.allowUpload,
    icon: "fa fa-video-camera",
    name: "Видео",
    onSelected: ({ composer, owner }, ev) => {
        markEventHandled(ev, "composer.clickOnAddAttachment");
        pickFiles(owner, composer, "video/*", (f) => ({ coopAsFile: isImage(f) }));
    },
    sequence: 12,
});

registerComposerAction("coop-wall-audio", {
    condition: (p) => onWall(p) && p.owner.allowUpload,
    icon: "fa fa-music",
    name: "Аудио",
    onSelected: ({ composer, owner }, ev) => {
        markEventHandled(ev, "composer.clickOnAddAttachment");
        pickFiles(owner, composer, "audio/*", (f) => ({ coopAsFile: isImage(f) }));
    },
    sequence: 13,
});

/**
 * Переопределить действие движка, сохранив его прочие свойства.
 * `force` — запись под тем же именем в реестре; без него реестр
 * отказывается от дубля.
 */
function override(id, changes) {
    const definition = composerActionsRegistry.get(id);
    composerActionsRegistry.add(id, { ...definition, ...changes(definition) }, { force: true });
}

// Голосовое: у движка оно есть только в переписке (`discuss.channel`).
// Записанное голосовое на стене показывается тем же проигрывателем с
// волной — отметку голосового сервер ставит при загрузке, где бы она ни
// была (`mail/models/discuss/ir_attachment.py`).
// Условия те же, что у движка, с заменой переписки на стену.
const recording = ({ owner }) => Boolean(owner.voiceRecorder?.recording);
override("voice-start", (d) => ({
    condition: (p) =>
        d.condition(p) ||
        (onWall(p) && Boolean(p.owner.voiceRecorder) && !recording(p) && !p.composer.voiceAttachment),
    name: (p) => (onWall(p) ? "Голосовое" : d.name),
    sequence: 14,
}));
for (const id of ["voice-stop", "voice-recording"]) {
    override(id, (d) => ({
        condition: (p) => d.condition(p) || (onWall(p) && recording(p)),
    }));
}

// Скрепка на стене — «Файл»: всё, что выбрано ею, идёт файлом, снимки
// тоже.
override("upload-files", (d) => ({
    name: (p) => (onWall(p) ? "Файл" : d.name),
    onSelected: (p, ev) => {
        if (!onWall(p)) {
            return d.onSelected(p, ev);
        }
        markEventHandled(ev, "composer.clickOnAddAttachment");
        pickFiles(p.owner, p.composer, "", (f) => ({ coopAsFile: isImage(f) }));
    },
    sequence: 15,
}));

// Служебные значки движка на стене не нужны.
for (const id of ["add-canned-response", "open-full-composer"]) {
    override(id, (d) => ({
        condition: (p) => !onWall(p) && (typeof d.condition === "function" ? d.condition(p) : true),
    }));
}

/**
 * Телефон: «Опубликовать» — галочкой, рядом крестик «Очистить».
 * Разметка — `xml/wall_composer.xml`.
 *
 * Крестик снимает и загруженные в черновик файлы — тем же путём, что
 * корзинка на самом вложении: иначе они остались бы на сервере
 * ничьими. Движковый `clear()` чистит только поле в браузере.
 */
patch(Composer.prototype, {
    setup() {
        super.setup(...arguments);
        // Свой признак фокуса: движковый `composer.isFocused` при входе в
        // поле ставится мимо реактивности (`toRaw`) — нарочно, чтобы не
        // перерисовывать поле на каждый фокус, — и кнопки по нему не
        // появлялись, пока не набран первый знак.
        this.coopFocus = useState({ on: false });
    },

    onFocusin(ev) {
        super.onFocusin(ev);
        if (WALL_MODELS.includes(this.thread?.model)) {
            this.coopFocus.on = true;
        }
    },

    onFocusout(ev) {
        super.onFocusout(ev);
        if (this.coopFocus.on) {
            this.coopFocus.on = false;
        }
    },

    get coopWallSmall() {
        return this.ui.isSmall && WALL_MODELS.includes(this.thread?.model) && !this.props.composer.message;
    },

    // Пишут запись: поле в фокусе или черновик не пуст. Второе нужно
    // затем, что касание галочки снимает фокус с поля раньше, чем
    // срабатывает само касание, — без него кнопка исчезала бы из-под
    // пальца.
    get coopEditing() {
        return this.coopFocus.on || !this.coopDraftEmpty;
    },

    get coopDraftEmpty() {
        return isHtmlEmpty(this.props.composer.composerHtml) && !this.props.composer.attachments.length;
    },

    async coopDiscard() {
        for (const attachment of [...this.props.composer.attachments]) {
            await this.attachmentUploader.unlink(attachment);
        }
        this.clear();
    },
});
