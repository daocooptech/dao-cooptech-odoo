"""Реестр Python-резолверов маппинга РСБУ.

Резолвер — функция fn(doc, template) -> list[dict], возвращающая
сбалансированный набор значений строк rsbu.move.line (Дт/Кт + субконто).
Резолверы регистрируются декоратором @resolver(key) при импорте модуля
и не редактируются пользователем.
"""

RESOLVER_REGISTRY = {}


def resolver(key):
    """Декоратор регистрации резолвера по ключу."""
    def deco(fn):
        RESOLVER_REGISTRY[key] = fn
        return fn
    return deco


def get_resolver(key):
    return RESOLVER_REGISTRY.get(key)


def resolver_selection():
    """Список ключей резолверов для Selection-поля шаблона."""
    return [(key, key) for key in sorted(RESOLVER_REGISTRY)]
