# -*- coding: utf-8 -*-
"""Очистка базы от служб Odoo S.A. — решения 439 (п. 4) и 441.

Запуск на старом дереве движка, пока код удаляемых модулей ещё на диске:

    odoo-bin shell -c <conf> -d <db> --no-http < deploy/engine_cleanup.py

Скрипт идемпотентен: повторный запуск ничего не меняет.

Что делает:
1. Удаляет задание «Publisher: Update Notification» и возвращает списку
   запланированных действий пустой отбор (mail прятал задание отбором).
2. Удаляет параметры iap_vies.* — ключи, выданные облаком Odoo.
3. Отмечает мастер сайта пройденным: иначе он зовёт облачную службу.
4. Выключает еженедельный дайджест: письма со сводкой больше не уходят.
5. Снимает модули служб (deploy/engine.remove). Защита: если удаление
   потянет модуль не из этого списка, скрипт останавливается до удаления.
"""
import logging
import os

_logger = logging.getLogger('coop.engine_cleanup')

HERE = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else None


def _removal_list():
    # Под `odoo-bin shell < файл` переменной __file__ нет, поэтому путь
    # к списку ищется от адреса модулей в конфигурации.
    from odoo.tools import config
    candidates = []
    if HERE:
        candidates.append(os.path.join(HERE, 'engine.remove'))
    paths = config.get('addons_path') or []
    if isinstance(paths, str):
        paths = paths.split(',')
    for path in paths:
        path = str(path).strip()
        if path.rstrip('/\\').endswith('coop-addons'):
            candidates.append(os.path.join(path, 'deploy', 'engine.remove'))
    for candidate in candidates:
        if os.path.exists(candidate):
            with open(candidate, encoding='utf-8') as fh:
                return [line.split('#')[0].strip() for line in fh
                        if line.split('#')[0].strip()]
    raise SystemExit('engine.remove не найден: %s' % candidates)


def say(msg, *args):
    print('[engine_cleanup] ' + (msg % args if args else msg))


def cleanup_data(env):
    Cron = env['ir.cron'].sudo().with_context(active_test=False)
    publisher = Cron.search([('model_name', '=', 'publisher_warranty.contract')])
    if publisher:
        say('задание Publisher: удаляю %s', publisher.ids)
        publisher.unlink()

    act = env.ref('base.ir_cron_act', raise_if_not_found=False)
    if act and act.domain not in (False, '', '[]'):
        say('отбор списка заданий: %r → []', act.domain)
        act.sudo().domain = '[]'

    params = env['ir.config_parameter'].sudo().search([('key', '=like', 'iap_vies.%')])
    if params:
        say('параметры облака: удаляю %s', params.mapped('key'))
        params.unlink()

    if 'website' in env:
        todo = env['website'].sudo().search([('configurator_done', '=', False)])
        if todo:
            say('мастер сайта: отмечаю пройденным у %s', todo.ids)
            todo.configurator_done = True

    if 'digest.digest' in env:
        digests = env['digest.digest'].sudo().search([('state', '=', 'activated')])
        if digests:
            say('дайджест: выключаю %s', digests.ids)
            digests.write({'state': 'deactivated'})
        ICP = env['ir.config_parameter'].sudo()
        if ICP.get_bool('digest.default_digest_emails'):
            ICP.set_bool('digest.default_digest_emails', False)
            say('дайджест: выключен для новых пользователей')
        cron = env.ref('digest.ir_cron_digest_scheduler_action', raise_if_not_found=False)
        if cron and cron.active:
            cron.sudo().active = False
            say('дайджест: задание рассылки выключено')

    env.cr.commit()


def removal_closure(env, names):
    Module = env['ir.module.module'].sudo()
    roots = Module.search([('name', 'in', names),
                           ('state', 'in', ('installed', 'to upgrade'))])
    if not roots:
        return roots, roots
    # Тот же обход, что делает button_uninstall: все установленные модули,
    # зависящие от удаляемых.
    closure = roots
    while True:
        deps = env['ir.module.module.dependency'].sudo().search([
            ('name', 'in', closure.mapped('name'))])
        more = deps.mapped('module_id').filtered(
            lambda m: m.state in ('installed', 'to upgrade')) - closure
        if not more:
            break
        closure |= more
    return roots, closure


def remove_modules(env, names):
    roots, closure = removal_closure(env, names)
    if not roots:
        say('модули служб: уже сняты')
        return False
    extra = sorted(set(closure.mapped('name')) - set(names))
    if extra:
        raise SystemExit('ОСТАНОВЛЕНО: удаление потянет модули не из списка: %s' % extra)
    say('модули служб: снимаю %s', sorted(closure.mapped('name')))
    roots.button_immediate_uninstall()
    return True


def mark_stripped(env):
    """Этап 2: движок из форка, каталоги модулей служб удалены.

    `update_list()` строки удалённых с диска модулей не трогает — они так и
    остаются `uninstalled` (замер 29.09 на копии: 153 из 154), и авто-
    установка может попытаться поставить такой модуль, когда ставится его
    зависимость. `uninstallable` закрывает это: авто-установка берёт только
    `uninstalled`. Помечаются только модули из списка форка
    (.coop/removed-modules.txt), и только если их правда нет на диске.
    """
    from odoo import release
    from odoo.modules.module import get_manifest
    listed = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(release.__file__))),
                          '.coop', 'removed-modules.txt')
    if not os.path.exists(listed):
        return  # движок не из форка
    with open(listed, encoding='utf-8') as fh:
        names = [l.split()[0] for l in fh if l.strip() and not l.startswith('#')]
    Module = env['ir.module.module'].sudo()
    Module.update_list()
    gone = Module.search([('name', 'in', names), ('state', '=', 'uninstalled')]) \
        .filtered(lambda m: not get_manifest(m.name))
    if gone:
        say('удалённые из движка модули: помечаю неустанавливаемыми %s', len(gone))
        gone.write({'state': 'uninstallable'})
    env.cr.commit()


def refresh_engine_changes(env):
    """Виды и шаблоны писем, изменённые в форке (слой В решения 441).

    Они лежат в базе, и `-u` их не обновит: шаблоны писем — noupdate, а
    `-u web`/`-u mail` тянет почти все модули. Форк сам перечисляет, что
    изменил (.coop/refresh-views.txt, refresh-templates.txt); здесь виды
    перечитываются из файла (reset_arch hard), шаблоны — штатным сбросом
    с переводами. Один раз на каждый коммит движка: сброс затирает правки
    шаблонов, сделанные в интерфейсе, и повторять его без нужды нельзя.
    """
    from odoo import release
    root = os.path.dirname(os.path.dirname(os.path.abspath(release.__file__)))
    head = os.path.join(root, '.git', 'HEAD')
    if not os.path.exists(os.path.join(root, '.coop')) or not os.path.exists(head):
        return
    with open(head, encoding='utf-8') as fh:
        sha = fh.read().strip()
    if sha.startswith('ref:'):
        # Рабочая копия на ветке (стенд): коммит — в файле ветки или в
        # packed-refs. На сервере клон по метке, и там в HEAD сам коммит.
        ref = sha.split(':', 1)[1].strip()
        loose = os.path.join(root, '.git', *ref.split('/'))
        if os.path.exists(loose):
            with open(loose, encoding='utf-8') as fh:
                sha = fh.read().strip()
        else:
            packed = os.path.join(root, '.git', 'packed-refs')
            if os.path.exists(packed):
                with open(packed, encoding='utf-8') as fh:
                    for line in fh:
                        if line.strip().endswith(' ' + ref):
                            sha = line.split()[0]
    ICP = env['ir.config_parameter'].sudo()
    if ICP.get_str('coop_engine.refreshed_for') == sha:
        return

    def listed(name):
        path = os.path.join(root, '.coop', name)
        if not os.path.exists(path):
            return []
        with open(path, encoding='utf-8') as fh:
            return [l.split()[0] for l in fh if l.strip() and not l.startswith('#')]

    views = env['ir.ui.view'].sudo()
    for xmlid in listed('refresh-views.txt'):
        view = env.ref(xmlid, raise_if_not_found=False)
        if view and view._name == 'ir.ui.view':
            views |= view
    if views:
        say('виды из форка: перечитываю %s', len(views))
        views.reset_arch(mode='hard')

    templates = env['mail.template'].sudo() if 'mail.template' in env else None
    if templates is not None:
        for xmlid in listed('refresh-templates.txt'):
            tpl = env.ref(xmlid, raise_if_not_found=False)
            if tpl and tpl._name == 'mail.template':
                templates |= tpl
        if templates:
            say('шаблоны писем из форка: перезаливаю %s', len(templates))
            templates.reset_template()

    ICP.set_str('coop_engine.refreshed_for', sha)
    env.cr.commit()


removal = _removal_list()
cleanup_data(env)  # noqa: F821 — env задаёт odoo-bin shell
remove_modules(env, removal)  # noqa: F821
mark_stripped(env)  # noqa: F821
refresh_engine_changes(env)  # noqa: F821
say('готово')
