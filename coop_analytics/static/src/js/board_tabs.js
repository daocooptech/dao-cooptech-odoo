/** @odoo-module **/

import { BoardController } from "@board/board_controller";
import { CoopTabs } from "@coop_theme/js/shell";

/**
 * Вкладки раздела «Аналитика» над «Моей панелью» (решение 420).
 *
 * У вида панели нет панели управления, а вкладки платформы живут в ней
 * (`coop_theme`, catalog_view.js) — над панелью их не было, и из «Моей
 * панели» в «Деньги» или «Сделки» было не перейти. Компонент дописывается
 * в список, как это сделано в теме для панели управления; разметка — в
 * xml/board_tabs.xml.
 */
BoardController.components = { ...BoardController.components, CoopTabs };
