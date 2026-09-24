/** @odoo-module **/

import { Component, onWillUnmount, reactive, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { download } from "@web/core/network/download";
import { patch } from "@web/core/utils/patch";
import { Attachment } from "@mail/core/common/attachment_model";
import { AttachmentList } from "@mail/core/common/attachment_list";
import { AttachmentUploadService } from "@mail/core/common/attachment_upload_service";
import { AttachmentUploader } from "@mail/core/common/attachment_uploader_hook";
import { fields } from "@mail/core/common/record";
import { WALL_MODELS } from "@coop_theme/js/wall";

// Фото на стене — картинкой или файлом.
//
// Владелец 24 сентября 2026: «и фото ещё — как надо сделать, чтобы
// спрашивал: загрузить как файл или картинкой». Как в мессенджерах:
// картинкой — снимок виден в записи миниатюрой, файлом — в записи лежит
// карточка с именем, и снимок скачивают целиком.
//
// Спрашивается только на стенах (`WALL_MODELS`) и только про картинки:
// документ, видео и голосовое всегда идут файлом, спрашивать там нечего.
// Три входа файла в поле ленты — скрепка, перетаскивание и вставка —
// сходятся в `AttachmentUploader.uploadFile`, там и спрашиваем.
//
// Выбор хранится на вложении (`coop_as_file`, `models/ir_attachment.py`)
// и приходит в браузер вместе с прочими его полями.

/**
 * Окно выбора. Одно на пачку: выбрал человек пять снимков скрепкой —
 * движок читает их по одному и по одному отдаёт загрузчику, и спросить
 * пять раз подряд было бы издевательством. Пока окно открыто, следующие
 * снимки ложатся в ту же пачку, и счёт в заголовке растёт вместе с ней.
 */
class CoopPhotoModeDialog extends Component {
    static components = { Dialog };
    static props = ["batch", "choose", "close"];
    static template = "coop_theme.PhotoModeDialog";

    setup() {
        this.batch = useState(this.props.batch);
        this.urls = new Map();
        onWillUnmount(() => {
            for (const url of this.urls.values()) {
                URL.revokeObjectURL(url);
            }
        });
    }

    get title() {
        const n = this.batch.files.length;
        return n > 1 ? `Как добавить ${n} фото?` : "Как добавить фото?";
    }

    // Снимков в окне не больше четырёх: окно спрашивает «как», а не
    // показывает альбом. Остальные — числом.
    get previews() {
        return this.batch.files.slice(0, 4).map((file) => {
            if (!this.urls.has(file)) {
                this.urls.set(file, URL.createObjectURL(file));
            }
            return { file, url: this.urls.get(file) };
        });
    }

    get more() {
        return Math.max(0, this.batch.files.length - 4);
    }

    choose(asFile) {
        this.props.choose(asFile);
        this.props.close();
    }
}

function isWallImage(thread, file) {
    return WALL_MODELS.includes(thread?.model) && Boolean(file?.type?.startsWith("image/"));
}

// Открытая пачка у каждого поля ленты своя.
const batches = new WeakMap();

patch(AttachmentUploader.prototype, {
    uploadFile(file, options) {
        const thread = options?.thread || this.thread;
        if (options?.coopAsFile !== undefined || !isWallImage(thread, file)) {
            return super.uploadFile(file, options);
        }
        const key = this.composer || this;
        let batch = batches.get(key);
        if (batch) {
            batch.files.push(file);
            return batch.done;
        }
        batch = reactive({ files: [file] });
        batches.set(key, batch);
        let chosen = null;
        let finish;
        batch.done = new Promise((resolve) => (finish = resolve));
        const upload = (asFile) => {
            chosen = asFile;
            batches.delete(key);
            const files = [...batch.files];
            Promise.all(
                files.map((f) => super.uploadFile(f, { ...options, coopAsFile: asFile }))
            ).then(finish, finish);
        };
        this.attachmentUploadService.store.env.services.dialog.add(
            CoopPhotoModeDialog,
            { batch, choose: upload },
            {
                // Крестик и Esc — «передумал»: ничего не загружаем, как в
                // мессенджере при отмене отправки.
                onClose: () => {
                    if (chosen === null) {
                        batches.delete(key);
                        finish();
                    }
                },
            }
        );
        return batch.done;
    },
});

patch(AttachmentUploadService.prototype, {
    _buildFormData(formData, tmpURL, thread, composer, tmpId, options) {
        super._buildFormData(...arguments);
        if (options?.coopAsFile) {
            formData.append("coop_as_file", "1");
        }
        return formData;
    },

    // Пока снимок грузится, в поле уже лежит его заготовка — пусть и она
    // выглядит так, как выбрано, а не мелькает миниатюрой.
    _makeAttachmentData(upload) {
        const data = super._makeAttachmentData(...arguments);
        if (upload.data.get("coop_as_file")) {
            data.coop_as_file = true;
        }
        return data;
    },
});

patch(Attachment.prototype, {
    setup() {
        super.setup(...arguments);
        this.coop_as_file = fields.Attr(false);
    },

    // Весь показ вложения в ленте движок решает одним признаком: картинка
    // — миниатюра, всё прочее — карточка. Снимок, отправленный файлом,
    // для ленты не картинка.
    get isImage() {
        return !this.coop_as_file && super.isImage;
    },
});

patch(AttachmentList.prototype, {
    // Карточку файла движок по щелчку открывает в просмотре, а снимок,
    // переставший быть картинкой, просмотр не берёт — щелчок уходил в
    // пустоту. Файл по щелчку скачивается, как в мессенджере.
    onClickAttachment(attachment) {
        if (attachment.coop_as_file && !this.env.inComposer) {
            download({ data: {}, url: attachment.downloadUrl });
            return;
        }
        super.onClickAttachment(attachment);
    },
});
