# -*- coding: utf-8 -*-
from . import lib
from .lib import crypto  # noqa: F401 — подменяет эталонную подпись на cryptography
from . import models
from . import controllers


def _post_init(env):
    """Узел, ключ и первое событие журнала — сразу при установке."""
    identity = env['coop.fed.identity']._ensure()
    env['coop.fed.event']._seal()
    return identity
