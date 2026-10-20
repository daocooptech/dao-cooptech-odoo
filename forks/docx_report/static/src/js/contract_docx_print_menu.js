/** @odoo-module **/

import {FormController} from "@web/views/form/form_controller";
import {patch} from "@web/core/utils/patch";

let docxReportMap = null;
let docxReportMapLoading = false;

async function loadDocxReportMap(env) {
    const orm = env.services.orm;
    const templates = await orm.searchRead("docx.template", [], [
        "id",
        "report_id",
        "global_template",
        "docx_model_id",
    ]);

    const byReportId = {};
    for (const t of templates) {
        const reportId = t.report_id && t.report_id[0];
        if (!reportId) continue;

        byReportId[reportId] = {
            templateId: t.id,
            globalTemplate: !!t.global_template,
            isDocxBased: !!t.docx_model_id,
        };
    }

    return { byReportId };
}

patch(FormController.prototype, {
    get actionMenuItems() {
        const items = super.actionMenuItems;
        const record = this.model?.root;

        if (!record || !("docx_template_id" in (record.data || {}))) {
            return items;
        }

        if (!docxReportMap && !docxReportMapLoading) {
            docxReportMapLoading = true;

            loadDocxReportMap(this.env)
                .then((map) => {
                    docxReportMap = map;
                    docxReportMapLoading = false;
                })
                .catch((e) => {
                    docxReportMapLoading = false;
                });

            return items;
        }

        if (!docxReportMap) {
            return items;
        }

        const tplVal = record.data.docx_template_id;
        // Odoo 20: many2one в record.data — объект {id, display_name}, не пара.
        const currentTemplateId = tplVal && (tplVal.id ?? tplVal[0]);
        const hasTemplate = !!currentTemplateId;

        if (!items.print?.length) {
            return items;
        }

        items.print = items.print.filter((entry) => {
            const reportId = entry.id;
            const info = docxReportMap.byReportId[reportId];

            if (!info || !info.isDocxBased) {
                return true;
            }

            if (info.globalTemplate) {
                return true;
            }

            if (!hasTemplate) {
                return false;
            }

            return info.templateId === currentTemplateId;
        });

        return items;
    },
});
