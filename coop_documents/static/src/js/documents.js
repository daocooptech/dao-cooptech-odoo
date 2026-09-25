/** @odoo-module **/

import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { generatePdfThumbnail } from "@mail/utils/common/pdf_thumbnail";

// Раздел «Документы» как у облачных дисков (разбор 25.09.2026):
// первая страница PDF на плитке (п. 2), загрузка файлами и папкой (п. 7),
// скан камерой телефона в PDF (п. 8). Сервер — `models/coop_document_more.py`.

// ── Первая страница на плитке ───────────────────────────────────────

// Снимок страницы рисует браузер и держит в памяти вкладки: сервер
// миниатюр не хранит, а повторный заход на ту же страницу каталога не
// рисует их заново.
const thumbs = new Map();

export class CoopPdfThumb extends Component {
    static template = "coop_documents.PdfThumb";
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({ src: thumbs.get(this.props.record.resId) || null, failed: false });
        onWillStart(() => {
            if (!this.state.src) {
                this.load();
            }
        });
    }

    async load() {
        const id = this.props.record.resId;
        try {
            // Через `/web/content`, а не свой адрес: миниатюра — не
            // «открыл документ», в журнал её писать незачем.
            const { thumbnail } = await generatePdfThumbnail(
                `/web/content/coop.document/${id}/file`, { width: 240, height: 320 });
            if (thumbnail) {
                const src = `data:image/jpeg;base64,${thumbnail}`;
                thumbs.set(id, src);
                this.state.src = src;
            } else {
                this.state.failed = true;
            }
        } catch {
            this.state.failed = true;
        }
    }
}

registry.category("fields").add("coop_pdf_thumb", {
    component: CoopPdfThumb,
    supportedTypes: ["integer"],
});

// ── Загрузка: файлы, папка, скан ────────────────────────────────────

const MAX_BYTES = 25 * 1024 * 1024;

function readBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

/** Файлы из перетащенной папки — с путём внутри неё. */
async function walkEntry(entry, prefix, out) {
    if (entry.isFile) {
        const file = await new Promise((res, rej) => entry.file(res, rej));
        out.push({ file, path: prefix + file.name });
    } else if (entry.isDirectory) {
        const reader = entry.createReader();
        let batch;
        do {
            batch = await new Promise((res, rej) => reader.readEntries(res, rej));
            for (const child of batch) {
                await walkEntry(child, `${prefix}${entry.name}/`, out);
            }
        } while (batch.length);
    }
}

export class CoopDocumentsUpload extends Component {
    static template = "coop_documents.Upload";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.filesRef = useRef("files");
        this.folderRef = useRef("folder");
        this.cameraRef = useRef("camera");
        this.state = useState({
            folders: [], folderId: "", queue: [], scans: [], scanName: "",
            over: false, busy: false, done: 0,
        });
        onWillStart(async () => {
            this.state.folders = await this.orm.searchRead(
                "coop.document.folder", [], ["display_name"], { order: "complete_name" });
        });
    }

    add(items) {
        for (const { file, path } of items) {
            if (file.size > MAX_BYTES) {
                this.notification.add(`«${file.name}» больше 25 МБ — пропущен`, { type: "warning" });
                continue;
            }
            this.state.queue.push({ file, path: path || file.name, name: file.name, size: file.size });
        }
    }

    onPickFiles(ev) {
        this.add([...ev.target.files].map((file) => ({ file, path: file.webkitRelativePath || file.name })));
        ev.target.value = "";
    }

    async onDrop(ev) {
        ev.preventDefault();
        this.state.over = false;
        const out = [];
        const items = [...(ev.dataTransfer.items || [])];
        if (items.length && items[0].webkitGetAsEntry) {
            for (const item of items) {
                const entry = item.webkitGetAsEntry();
                if (entry) {
                    await walkEntry(entry, "", out);
                }
            }
        } else {
            for (const file of ev.dataTransfer.files) {
                out.push({ file, path: file.name });
            }
        }
        this.add(out);
    }

    remove(index) {
        this.state.queue.splice(index, 1);
    }

    sizeLabel(bytes) {
        return bytes > 1048576 ? `${(bytes / 1048576).toFixed(1)} МБ` : `${Math.ceil(bytes / 1024)} КБ`;
    }

    async upload() {
        if (!this.state.queue.length || this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.done = 0;
        const folderId = Number(this.state.folderId) || false;
        try {
            // По пять файлов за вызов: один огромный вызов на сотню файлов
            // упирается в предел размера запроса.
            const queue = [...this.state.queue];
            while (queue.length) {
                const chunk = queue.splice(0, 5);
                const files = [];
                for (const item of chunk) {
                    files.push({ name: item.name, path: item.path, data: await readBase64(item.file) });
                }
                await this.orm.call("coop.document", "coop_upload", [files, folderId]);
                this.state.done += chunk.length;
            }
            this.notification.add(`Загружено: ${this.state.done}`, { type: "success" });
            this.state.queue = [];
            this.state.folders = await this.orm.searchRead(
                "coop.document.folder", [], ["display_name"], { order: "complete_name" });
        } finally {
            this.state.busy = false;
        }
    }

    // Скан: снимки камерой по одному, потом — одним PDF.
    async onCamera(ev) {
        for (const file of ev.target.files) {
            this.state.scans.push({ url: URL.createObjectURL(file), file });
        }
        ev.target.value = "";
    }

    removeScan(index) {
        URL.revokeObjectURL(this.state.scans[index].url);
        this.state.scans.splice(index, 1);
    }

    async saveScan() {
        if (!this.state.scans.length || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const images = [];
            for (const scan of this.state.scans) {
                images.push(await readBase64(scan.file));
            }
            const id = await this.orm.call("coop.document", "coop_scan",
                [images, this.state.scanName || false, Number(this.state.folderId) || false]);
            this.state.scans.forEach((s) => URL.revokeObjectURL(s.url));
            this.state.scans = [];
            this.state.scanName = "";
            this.notification.add("Скан сохранён документом", { type: "success" });
            this.action.doAction({
                type: "ir.actions.act_window", res_model: "coop.document", res_id: id,
                views: [[false, "form"]], target: "current",
            });
        } finally {
            this.state.busy = false;
        }
    }

    openAll() {
        this.action.doAction("coop_documents.action_coop_documents");
    }
}

registry.category("actions").add("coop_documents_upload", CoopDocumentsUpload);
