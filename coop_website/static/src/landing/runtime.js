/** @odoo-module ignore */
/*
 * Отрисовщик лендинга.
 *
 * Макет лендинга — шаблон с привязками `{{путь}}`, циклами `sc-for`,
 * условиями `sc-if` и обработчиками `onClick`/`onChange`, а данные даёт
 * `renderVals()` класса `Component` (см. landing_page.js, собирается
 * tools/build_landing.py). Здесь — ровно столько движка, сколько этому
 * шаблону нужно: отрисовать дерево по данным и при каждом `setState`
 * сверить его с тем, что уже на странице, меняя только отличия. Полная
 * перерисовка сбрасывала бы ползунок под пальцем и раскрытые вопросы.
 */
(function () {
    "use strict";

    const EXPR = /\{\{\s*([^}]+?)\s*\}\}/g;
    const ONE = /^\{\{\s*([^}]+?)\s*\}\}$/;
    const EVENTS = { onclick: "click", onchange: "input" };

    function lookup(scope, path) {
        if (path === "true") return true;
        if (path === "false") return false;
        let value = scope;
        for (const key of path.split(".")) {
            if (value == null) return undefined;
            value = value[key];
        }
        return value;
    }

    function text(value) {
        return value == null || value === false ? "" : String(value);
    }

    function interpolate(str, scope) {
        return str.replace(EXPR, (_, path) => text(lookup(scope, path)));
    }

    function renderChildren(node, scope, out) {
        for (const child of node.childNodes) {
            renderNode(child, scope, out);
        }
        return out;
    }

    function renderNode(node, scope, out) {
        if (node.nodeType === Node.TEXT_NODE) {
            out.push(document.createTextNode(interpolate(node.data, scope)));
            return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        const tag = node.localName;
        if (tag === "sc-for") {
            const list = lookup(scope, node.getAttribute("list").match(ONE)[1]) || [];
            const as = node.getAttribute("as");
            for (const item of list) {
                renderChildren(node, Object.assign(Object.create(scope), { [as]: item }), out);
            }
            return;
        }
        if (tag === "sc-if") {
            if (lookup(scope, node.getAttribute("value").match(ONE)[1])) {
                renderChildren(node, scope, out);
            }
            return;
        }
        // localName, а не tagName: у HTML-элемента tagName в верхнем
        // регистре, и созданный по нему `SECTION` не ловят ни стили
        // `section`, ни querySelector.
        const el = document.createElementNS(node.namespaceURI, node.localName);
        el.__on = {};
        for (const attr of node.attributes) {
            const name = attr.name;
            if (name.startsWith("hint-")) continue;
            const one = attr.value.match(ONE);
            if (EVENTS[name.toLowerCase()] && one) {
                el.__on[EVENTS[name.toLowerCase()]] = lookup(scope, one[1]);
                continue;
            }
            el.setAttribute(name, one ? text(lookup(scope, one[1])) : interpolate(attr.value, scope));
        }
        renderChildren(node, scope, []).forEach((c) => el.appendChild(c));
        out.push(el);
    }

    function patchAttrs(old, fresh) {
        for (const attr of [...old.attributes]) {
            // Раскрытый вопрос — состояние посетителя, а не шаблона.
            if (old.localName === "details" && attr.name === "open") continue;
            if (!fresh.hasAttribute(attr.name)) old.removeAttribute(attr.name);
        }
        for (const attr of fresh.attributes) {
            if (old.getAttribute(attr.name) !== attr.value) old.setAttribute(attr.name, attr.value);
        }
        if (old.localName === "input" && fresh.hasAttribute("value")) {
            const value = fresh.getAttribute("value");
            if (old.value !== value) old.value = value;
        }
        old.__on = fresh.__on;
    }

    function patch(parent, nodes) {
        let i = 0;
        for (; i < nodes.length; i++) {
            const fresh = nodes[i];
            const old = parent.childNodes[i];
            if (!old) {
                parent.appendChild(fresh);
            } else if (old.nodeType !== fresh.nodeType || old.nodeName !== fresh.nodeName) {
                parent.replaceChild(fresh, old);
            } else if (old.nodeType === Node.TEXT_NODE) {
                if (old.data !== fresh.data) old.data = fresh.data;
            } else {
                patchAttrs(old, fresh);
                patch(old, [...fresh.childNodes]);
            }
        }
        while (parent.childNodes.length > i) parent.removeChild(parent.lastChild);
    }

    class DCLogic {
        constructor(props) {
            this.props = props || {};
            this.state = {};
        }
        setState(part) {
            Object.assign(this.state, part);
            if (this.__render) this.__render();
        }
    }

    function mount(markup, Component) {
        // Пакет ресурсов подключается в <head>, до разметки страницы.
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", () => mount(markup, Component));
            return;
        }
        const host = document.getElementById("coop-landing");
        if (!host) return;
        const tpl = document.createElement("template");
        tpl.innerHTML = markup;
        const props = {
            variant: Number(host.dataset.variant) || 0,
            role: Number(host.dataset.role) || 0,
            dark: false,
        };
        const comp = new Component(props);
        const extra = { contactHref: host.dataset.contact || "/" };
        comp.__render = () => {
            const vals = Object.assign({}, extra, comp.renderVals());
            patch(host, renderChildren(tpl.content, vals, []));
        };
        for (const type of ["click", "input"]) {
            host.addEventListener(type, (ev) => {
                for (let el = ev.target; el && el !== host; el = el.parentNode) {
                    const fn = el.__on && el.__on[type];
                    if (fn) {
                        fn(ev);
                        return;
                    }
                }
            });
        }
        comp.__render();
        // Переход по якорю из адреса — после отрисовки: до неё якорей нет.
        if (location.hash.length > 1) {
            const target = document.getElementById(location.hash.slice(1));
            if (target) target.scrollIntoView();
        }
    }

    window.CoopLandingRuntime = { DCLogic, mount };
})();
