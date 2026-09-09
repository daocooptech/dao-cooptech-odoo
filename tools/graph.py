# -*- coding: utf-8 -*-
"""Граф кода наших модулей: что где объявлено и что чем пользуется.

Зачем. Ответ на вопрос «где определён класс o_coop_listing» или «какие
канбаны рисуют карточку своим семейством классов» добывался грепом по
восемнадцати модулям и занимал десятки минут. Здесь то же самое —
за секунду и точно.

Что индексируется: модули, модели, поля, представления, действия,
классы в разметке и селекторы в стилях, плюс связи между ними. Никакой
языковой модели: разбор исходников, детерминированно и бесплатно.

    python tools/graph.py build              собрать индекс (tools/graph.json)
    python tools/graph.py stats              что в индексе

    python tools/graph.py model coop.event   модель: файл, поля, представления
    python tools/graph.py field signup_label где объявлено поле
    python tools/graph.py view coop.event    представления модели
    python tools/graph.py class o_coop_listing
                                             где селектор задан и кто им пользуется
    python tools/graph.py cards              карточки канбанов: кто на каком семействе
    python tools/graph.py naked              классы разметки, к которым нет стилей
    python tools/graph.py action Люди        действие по названию или xml id
    python tools/graph.py grep запись        поиск по всему индексу
"""
import ast
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # coop-addons
INDEX = os.path.join(HERE, "graph.json")


def rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


# ── разбор python ────────────────────────────────────────────────────────

FIELD_TYPES = {
    "Char", "Text", "Html", "Integer", "Float", "Monetary", "Boolean", "Date",
    "Datetime", "Binary", "Image", "Selection", "Many2one", "One2many",
    "Many2many", "Reference", "Json", "Properties",
}


def parse_python(path, module, out):
    try:
        tree = ast.parse(io.open(path, encoding="utf-8").read())
    except SyntaxError as e:
        out["ошибки"].append({"файл": rel(path), "что": "python: %s" % e.msg})
        return

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        name = inherit = None
        fields = []
        for item in node.body:
            if isinstance(item, ast.Assign) and item.targets:
                target = item.targets[0]
                key = getattr(target, "id", None)
                if key == "_name" and isinstance(item.value, ast.Constant):
                    name = item.value.value
                elif key == "_inherit":
                    if isinstance(item.value, ast.Constant):
                        inherit = item.value.value
                    elif isinstance(item.value, (ast.List, ast.Tuple)):
                        inherit = [e.value for e in item.value.elts
                                   if isinstance(e, ast.Constant)]
                elif key and isinstance(item.value, ast.Call):
                    func = item.value.func
                    if (isinstance(func, ast.Attribute)
                            and func.attr in FIELD_TYPES
                            and getattr(func.value, "id", "") == "fields"):
                        label = compute = None
                        for kw in item.value.keywords:
                            if kw.arg in ("string",) and isinstance(kw.value, ast.Constant):
                                label = kw.value.value
                            if kw.arg == "compute" and isinstance(kw.value, ast.Constant):
                                compute = kw.value.value
                        if not label and item.value.args:
                            first = item.value.args[0]
                            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                                label = first.value
                        fields.append({
                            "имя": key, "тип": func.attr, "подпись": label,
                            "вычисляемое": compute, "строка": item.lineno,
                        })
        if name or fields:
            out["модели"].append({
                "модель": name or (inherit if isinstance(inherit, str) else None),
                "объявлена": bool(name),
                "наследует": inherit,
                "класс": node.name,
                "модуль": module,
                "файл": rel(path),
                "строка": node.lineno,
                "поля": fields,
            })


# ── разбор xml ───────────────────────────────────────────────────────────

CLASS_RE = re.compile(r'class="([^"]+)"')
# Из t-att-class берём только целые имена. Склейка вида «'o_coop_deal_ico_'
# + record.subject.raw_value» даёт обрубок, которого в стилях нет и быть
# не может, — такие отбрасываем по хвостовому подчёркиванию.
TATT_RE = re.compile(r"t-att-class=\"[^\"]*?'([a-z_][a-z0-9_ ]*[a-z0-9])'")


def parse_xml(path, module, out):
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        out["ошибки"].append({"файл": rel(path), "что": "xml: %s" % e})
        return
    raw = io.open(path, encoding="utf-8").read()

    for rec in tree.iter("record"):
        model = rec.get("model")
        xmlid = rec.get("id")
        if model == "ir.ui.view":
            fields = {f.get("name"): f for f in rec.findall("field")}
            arch = fields.get("arch")
            target = fields.get("model")
            kind = None
            classes = []
            card_root = None
            if arch is not None and len(arch):
                kind = arch[0].tag
                chunk = ET.tostring(arch[0], encoding="unicode")
                classes = sorted({c for blob in CLASS_RE.findall(chunk)
                                  for c in blob.split() if c.startswith("o_")})
                card = re.search(r't t-name="card"\s*>\s*<div class="([^"]+)"', chunk)
                if card:
                    card_root = card.group(1).split()[0]
            out["представления"].append({
                "xmlid": "%s.%s" % (module, xmlid) if xmlid else None,
                "модель": target.text if target is not None else None,
                "вид": kind,
                "модуль": module,
                "файл": rel(path),
                "карточка": card_root,
                "классы": classes,
            })
        elif model == "ir.actions.act_window":
            fields = {f.get("name"): f for f in rec.findall("field")}
            out["действия"].append({
                "xmlid": "%s.%s" % (module, xmlid) if xmlid else None,
                "название": (fields.get("name").text
                             if fields.get("name") is not None else None),
                "модель": (fields.get("res_model").get("eval")
                           or fields.get("res_model").text
                           if fields.get("res_model") is not None else None),
                "модуль": module,
                "файл": rel(path),
            })

    # классы, встреченные в шаблонах qweb вне записей представлений
    for blob in CLASS_RE.findall(raw):
        for c in blob.split():
            if c.startswith("o_coop"):
                out["использование_классов"].setdefault(c, set()).add(rel(path))
    for c in TATT_RE.findall(raw):
        if c.startswith("o_coop"):
            out["использование_классов"].setdefault(c, set()).add(rel(path))


# ── разбор стилей ────────────────────────────────────────────────────────

# Селектор ловится и когда правило записано в одну строку: «.o_coop_fact_key
# { color: … }» — на такой записи первая версия разборщика молчала, и
# инструмент показывал написанные стили как отсутствующие.
SEL_RE = re.compile(r"^\s*([.&][A-Za-z0-9_.\-&:> ,\[\]=\"']+?)\s*\{")


def parse_scss(path, module, out):
    for i, line in enumerate(io.open(path, encoding="utf-8"), 1):
        m = SEL_RE.match(line.rstrip("\n"))
        if not m:
            continue
        for part in m.group(1).split(","):
            for cls in re.findall(r"\.([A-Za-z0-9_\-]+)", part):
                if cls.startswith("o_"):
                    out["селекторы"].setdefault(cls, []).append({
                        "модуль": module, "файл": rel(path), "строка": i,
                    })


# ── сборка ───────────────────────────────────────────────────────────────

def build():
    out = {
        "модули": [], "модели": [], "представления": [], "действия": [],
        "селекторы": {}, "использование_классов": {}, "ошибки": [],
    }
    for name in sorted(os.listdir(ROOT)):
        mdir = os.path.join(ROOT, name)
        if not os.path.isdir(mdir) or not os.path.exists(
                os.path.join(mdir, "__manifest__.py")):
            continue
        depends = []
        try:
            manifest = ast.literal_eval(
                io.open(os.path.join(mdir, "__manifest__.py"),
                        encoding="utf-8").read())
            depends = manifest.get("depends", [])
        except Exception:
            pass
        out["модули"].append({"модуль": name, "зависит": depends})

        for base, dirs, files in os.walk(mdir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
            for f in files:
                p = os.path.join(base, f)
                if f.endswith(".py") and f != "__manifest__.py":
                    parse_python(p, name, out)
                elif f.endswith(".xml"):
                    parse_xml(p, name, out)
                elif f.endswith(".scss"):
                    parse_scss(p, name, out)

    out["использование_классов"] = {k: sorted(v) for k, v
                                    in out["использование_классов"].items()}
    io.open(INDEX, "w", encoding="utf-8", newline="\n").write(
        json.dumps(out, ensure_ascii=False, indent=1))
    stats(out)


def load():
    if not os.path.exists(INDEX):
        sys.exit("Индекса нет. Собери: python tools/graph.py build")
    return json.load(io.open(INDEX, encoding="utf-8"))


def stats(g=None):
    g = g or load()
    поля = sum(len(m["поля"]) for m in g["модели"])
    связи = (поля
             + sum(len(m["зависит"]) for m in g["модули"])
             + sum(len(v["классы"]) for v in g["представления"])
             + sum(len(v) for v in g["использование_классов"].values()))
    print("модулей:", len(g["модули"]))
    print("моделей:", len({m["модель"] for m in g["модели"] if m["модель"]}),
          "· описаний классов:", len(g["модели"]))
    print("полей:", поля)
    print("представлений:", len(g["представления"]),
          "· действий:", len(g["действия"]))
    print("селекторов:", len(g["селекторы"]),
          "· классов в разметке:", len(g["использование_классов"]))
    print("связей:", связи)
    if g["ошибки"]:
        print("не разобрано файлов:", len(g["ошибки"]))
        for e in g["ошибки"][:5]:
            print("  ", e["файл"], "—", e["что"][:80])


# ── запросы ──────────────────────────────────────────────────────────────

def q_model(g, name):
    for m in g["модели"]:
        if m["модель"] == name:
            метка = "объявлена" if m["объявлена"] else "дополняет"
            print("%s %s · %s:%d · модуль %s"
                  % (метка, m["класс"], m["файл"], m["строка"], m["модуль"]))
            for f in m["поля"]:
                вычисл = " ← %s" % f["вычисляемое"] if f["вычисляемое"] else ""
                print("   %-28s %-12s %s%s"
                      % (f["имя"], f["тип"], f["подпись"] or "", вычисл))
    views = [v for v in g["представления"] if v["модель"] == name]
    if views:
        print("\nпредставления:")
        for v in views:
            print("   %-8s %-45s карточка: %s"
                  % (v["вид"] or "?", v["xmlid"] or v["файл"], v["карточка"] or "—"))


def q_field(g, name):
    for m in g["модели"]:
        for f in m["поля"]:
            if name.lower() in f["имя"].lower():
                print("%-24s %-12s %-22s %s:%d"
                      % (f["имя"], f["тип"], m["модель"] or m["класс"],
                         m["файл"], f["строка"]))


def q_view(g, name):
    for v in g["представления"]:
        if name in (v["модель"] or "") or name in (v["xmlid"] or ""):
            print("%-8s %-40s %s карточка: %s"
                  % (v["вид"] or "?", v["xmlid"], v["файл"], v["карточка"] or "—"))
            if v["классы"]:
                print("        классы:", " ".join(v["классы"][:12]))


def q_class(g, name):
    места = g["селекторы"].get(name)
    if места:
        print("задан:")
        for m in места:
            print("   %s:%d" % (m["файл"], m["строка"]))
    else:
        print("в стилях не найден")
    польз = g["использование_классов"].get(name)
    if польз:
        print("используется в разметке:")
        for f in польз:
            print("  ", f)


def q_cards(g):
    """Кто каким семейством карточек рисует канбан — главный вопрос дня."""
    семьи = {}
    for v in g["представления"]:
        if v["вид"] != "kanban" or not v["карточка"]:
            continue
        семьи.setdefault(v["карточка"], []).append(
            "%s (%s)" % (v["модель"], v["модуль"]))
    for корень in sorted(семьи, key=lambda k: -len(семьи[k])):
        где = g["селекторы"].get(корень)
        адрес = где[0]["файл"] if где else "стиль не найден"
        print("%-22s %-42s %d: %s"
              % (корень, адрес, len(семьи[корень]), ", ".join(семьи[корень])))


def q_naked(g):
    """Классы, на которые разметка ссылается, а правил к ним нет нигде.

    Так нашлись обе выдачи токеномики: разметка была написана, стилей
    к o_coop_fact* не существовало ни в одном файле, и карточки рисовались
    голым столбиком текста.

    Не всякая находка — поломка: класс-крючок рядом с общим (o_coop_res_meta
    при o_coop_listing_meta) правил не требует, оформление ему приходит
    от соседа. Смотреть надо те, у которых соседа нет.
    """
    селекторы = set(g["селекторы"])
    голые = {c: f for c, f in g["использование_классов"].items()
             if c not in селекторы and not c.endswith("_")}
    print("ссылок без своих правил:", len(голые))
    for cls in sorted(голые):
        соседи = [s for s in селекторы if cls.startswith(s) or s.startswith(cls)]
        пометка = "" if соседи else "  ← правил нет и рядом"
        print("  %-32s %-28s%s" % (cls, ", ".join(sorted({f.split("/")[0]
              for f in голые[cls]}))[:26], пометка))


def q_action(g, name):
    for a in g["действия"]:
        if name.lower() in (a["название"] or "").lower() or name in (a["xmlid"] or ""):
            print("%-46s %-24s %s" % (a["xmlid"], a["модель"] or "?", a["название"]))
            print("        /odoo/action-%s" % a["xmlid"])


def q_grep(g, needle):
    n = needle.lower()
    for m in g["модели"]:
        if n in (m["модель"] or "").lower() or n in m["класс"].lower():
            print("модель  %s  %s:%d" % (m["модель"], m["файл"], m["строка"]))
        for f in m["поля"]:
            if n in f["имя"].lower() or n in (f["подпись"] or "").lower():
                print("поле    %s.%s  %s:%d"
                      % (m["модель"], f["имя"], m["файл"], f["строка"]))
    for v in g["представления"]:
        if n in (v["xmlid"] or "").lower():
            print("вид     %s  %s" % (v["xmlid"], v["файл"]))
    for cls, места in g["селекторы"].items():
        if n in cls.lower():
            print("класс   %s  %s:%d" % (cls, места[0]["файл"], места[0]["строка"]))


COMMANDS = {
    "build": lambda g, a: build(),
    "stats": lambda g, a: stats(g),
    "model": lambda g, a: q_model(g, a),
    "field": lambda g, a: q_field(g, a),
    "view": lambda g, a: q_view(g, a),
    "class": lambda g, a: q_class(g, a),
    "cards": lambda g, a: q_cards(g),
    "naked": lambda g, a: q_naked(g),
    "action": lambda g, a: q_action(g, a),
    "grep": lambda g, a: q_grep(g, a),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return
    cmd = sys.argv[1]
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    g = None if cmd == "build" else load()
    if cmd in ("model", "field", "view", "class", "action", "grep") and not arg:
        sys.exit("Нужен аргумент: python tools/graph.py %s <что>" % cmd)
    COMMANDS[cmd](g, arg)


main()
