/** @odoo-module **/

import {download} from "@web/core/network/download";
import {registry} from "@web/core/registry";

function getReportUrl(action) {

    let url = `/report/xml/${action.report_name}`;

    const actionContext = action.context || {};

    if (action.data && JSON.stringify(action.data) !== "{}") {

        const encodedOptions = encodeURIComponent(
            JSON.stringify(action.data)
        );

        const encodedContext = encodeURIComponent(
            JSON.stringify(actionContext)
        );

        return `${url}?options=${encodedOptions}&context=${encodedContext}`;
    }

    if (actionContext.active_ids) {
        url += `/${actionContext.active_ids.join(",")}`;
    }

    return `${url}?context=${encodeURIComponent(JSON.stringify(actionContext))}`;
}
async function triggerDownload(action) {

    const data = JSON.stringify([
        getReportUrl(action),
        action.report_type,
    ]);

    const context = JSON.stringify(action.context || {});

    await download({
        url: "/report/download",
        data: { data, context },
    });
}
registry
    .category("ir.actions.report handlers")
    .add("xml_handler", async function (action, options) {

        if (action.report_type !== "qweb-xml") {
            return false;
        }

        await triggerDownload(action);

        return true;
    });