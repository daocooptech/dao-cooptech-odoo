# -*- coding: utf-8 -*-
"""Правило владения: авторитетен тот узел, о ком факт.

Подпись доказывает, кто написал событие, но не то, что он вправе о нём
писать. Узел A может честно подписать «предложение B снято с продажи» — и
подпись сойдётся. Поэтому после проверки подписи идёт вторая проверка: чей
это предмет.

Для односторонних фактов предмет начинается с идентификатора автора:
`did:web:a.example/offer/17` вправе менять только `did:web:a.example`.
События об узле (`node.*`) говорят о самом узле, и их предмет — сам DID.

Двусторонние объекты — сделка, линия обязательства, раунд зачёта, отзыв,
членство между узлами, совместная собственность — авторитетного узла не
имеют. По конверту их не рассудить: нужен список сторон, а он в теле или в
самом объекте. Для них функция отвечает «нужен контекст», а решает модуль
объекта (`deal.py`, `line.py`, `review.py`).
"""

# Двусторонние и многосторонние семейства: автора проверяет модуль объекта.
BILATERAL = ('deal.', 'line.', 'clearing.', 'review.', 'membership.', 'joint.')

# Семейства с одним владельцем. Неизвестный тип сюда не попадает: его узел
# сохраняет как есть и не применяет, а судить о владении не берётся.
UNILATERAL = ('node.', 'catalog.', 'trust.', 'document.', 'org.')

NEEDS_CONTEXT = 'needs_context'
UNKNOWN = 'unknown'


def owns(event):
    """True — автор вправе; False — событие о чужом предмете, отбросить;
    NEEDS_CONTEXT — двусторонний объект, решает его модуль;
    UNKNOWN — тип незнаком, сохранить и не применять."""
    type_, node, subject = event.get('type', ''), event.get('node'), event.get('subject', '')
    if type_.startswith(BILATERAL):
        return NEEDS_CONTEXT
    if type_.startswith('node.'):
        return subject == node
    if type_.startswith(UNILATERAL):
        return subject.startswith(node + '/')
    return UNKNOWN


def deal_author_ok(event, parties):
    """Вправе ли автор писать о сделке: он одна из сторон, а предложить может
    только тот, кто выпустил предмет. Остальные правила — в `deal.py`."""
    node = event.get('node')
    if node not in parties:
        return False
    if event.get('type') == 'deal.proposed':
        return event.get('subject', '').startswith(node + '/')
    return True
