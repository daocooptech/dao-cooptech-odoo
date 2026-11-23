import { patch } from "@web/core/utils/patch";
import { ProjectTaskControlPanel } from "@project/views/project_task_control_panel/project_task_control_panel";

// Панель задач — с правками темы (`xml/task_control_panel.xml`, № 480).
patch(ProjectTaskControlPanel, { template: "coop_projects.ProjectTaskControlPanel" });
