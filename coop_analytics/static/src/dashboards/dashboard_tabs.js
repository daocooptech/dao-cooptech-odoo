/** @odoo-module **/

import { SpreadsheetDashboardAction } from "@spreadsheet_dashboard/bundle/dashboard_action/dashboard_action";
import { CoopTabs } from "@coop_theme/js/shell";

/**
 * Вкладки раздела «Аналитика» над готовыми дашбордами (решение 420, слой 2).
 *
 * Экран дашбордов движка — клиентское действие без модели поиска, и
 * признак раздела (`coop_section`), по которому панель управления рисует
 * вкладки, ему не достаётся: из «Дашбордов» было бы не вернуться в «Мою
 * панель» или «Деньги». Как и над «Моей панелью» (js/board_tabs.js),
 * компонент дописывается в список, разметка — в dashboard_tabs.xml.
 * Экран грузится лениво, бандлом `spreadsheet.o_spreadsheet`, — туда же и
 * эти файлы (манифест).
 */
SpreadsheetDashboardAction.components = { ...SpreadsheetDashboardAction.components, CoopTabs };
