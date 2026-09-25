# -*- coding: utf-8 -*-
"""Адреса документов: просмотр, скачивание, архив и ссылка для внешней стороны.

Свои адреса, а не `/web/content`: открытие и скачивание должны попасть
в журнал документа (разбор дисков, п. 4) — движок этого не знает.
"""
import base64
import io
import mimetypes
import zipfile
from datetime import datetime, timedelta

from markupsafe import Markup, escape

from odoo import fields, http
from odoo.http import request

KINDS = {'contract': 'Договор', 'act': 'Акт приёма-передачи', 'closing': 'Закрывающий документ',
         'protocol': 'Протокол', 'other': 'Документ'}


def _content(doc):
    data = base64.b64decode(doc.file or b'')
    name = doc.file_name or ('%s.pdf' % doc.name)
    mime = mimetypes.guess_type(name)[0] or 'application/octet-stream'
    return data, name, mime


def _log_once(doc, action, minutes=10):
    """«Открыт» — не чаще раза в десять минут от одного человека: иначе
    каждая перерисовка вкладки просмотра писала бы строку в журнал."""
    Log = request.env['coop.document.log'].sudo()
    since = datetime.now() - timedelta(minutes=minutes)
    if not Log.search_count([('document_id', '=', doc.id), ('action', '=', action),
                             ('partner_id', '=', request.env.user.partner_id.id),
                             ('date', '>=', since)], limit=1):
        doc._coop_log(action)


class CoopDocumentsController(http.Controller):

    def _document(self, doc_id):
        doc = request.env['coop.document'].with_context(active_test=False).browse(doc_id).exists()
        if not doc:
            raise request.not_found()
        doc.check_access('read')
        return doc

    @http.route('/coop/document/<int:doc_id>/view', type='http', auth='user')
    def view(self, doc_id, **kw):
        doc = self._document(doc_id)
        if not doc.file:
            raise request.not_found()
        data, name, mime = _content(doc)
        _log_once(doc.sudo(), 'opened')
        return request.make_response(data, [
            ('Content-Type', mime),
            ('Content-Disposition', http.content_disposition(name, disposition_type='inline')),
        ])

    @http.route('/coop/document/<int:doc_id>/download', type='http', auth='user')
    def download(self, doc_id, **kw):
        doc = self._document(doc_id)
        if not doc.file:
            raise request.not_found()
        data, name, mime = _content(doc)
        doc.sudo()._coop_log('downloaded')
        return request.make_response(data, [
            ('Content-Type', mime),
            ('Content-Disposition', http.content_disposition(name)),
        ])

    @http.route('/coop/documents/zip', type='http', auth='user')
    def zip(self, ids='', **kw):
        """Выбранные документы одним архивом (разбор, п. 7)."""
        doc_ids = [int(x) for x in ids.split(',') if x.strip().isdigit()]
        docs = request.env['coop.document'].with_context(active_test=False).browse(doc_ids).exists()
        docs = docs._filtered_access('read').filtered('file')
        buffer = io.BytesIO()
        used = set()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for doc in docs:
                data, name, _mime = _content(doc)
                folder = (doc.folder_id.complete_name or '').replace(' / ', '/')
                path = '%s/%s' % (folder, name) if folder else name
                base, n = path, 2
                while path in used:
                    stem, dot, ext = base.rpartition('.')
                    path = '%s (%d).%s' % (stem, n, ext) if dot else '%s (%d)' % (base, n)
                    n += 1
                used.add(path)
                archive.writestr(path, data)
        docs.sudo()._coop_log('downloaded', note='архивом')
        return request.make_response(buffer.getvalue(), [
            ('Content-Type', 'application/zip'),
            ('Content-Disposition', http.content_disposition(
                'Документы %s.zip' % fields.Date.today().strftime('%d.%m.%Y'))),
        ])

    # ── Ссылка для внешней стороны ──────────────────────────────────

    def _share(self, token):
        share = request.env['coop.document.share'].sudo().search(
            [('token', '=', token)], limit=1)
        if not share or share.state != 'active' or not share.document_id.active:
            return None
        return share

    def _unlocked(self, share):
        return not share.password_hash or \
            request.session.get('coop_doc_%s' % share.id) == share.password_hash

    @http.route('/coop/doc/<string:token>', type='http', auth='public', methods=['GET', 'POST'],
                csrf=False)
    def public(self, token, password=None, **kw):
        share = self._share(token)
        if not share:
            return request.make_response(_page(
                'Ссылка недействительна',
                Markup('<p>Ссылку отозвали, срок её истёк или документа больше нет. '
                       'Попросите сторону документа выдать новую.</p>')), status=404)
        wrong = False
        if password is not None:
            if share.check_password(password):
                request.session['coop_doc_%s' % share.id] = share.password_hash
            else:
                wrong = True
        if not self._unlocked(share):
            body = Markup(
                '<p>Документ защищён паролем. Его сообщила сторона, выдавшая ссылку.</p>'
                '<form method="post"><input type="password" name="password" autofocus '
                'placeholder="Пароль" class="inp"/> <button class="btn">Открыть</button></form>%s'
            ) % (Markup('<p class="bad">Пароль не подходит.</p>') if wrong else '')
            return request.make_response(_page('Документ', body))

        doc = share.document_id
        share.views += 1
        _log_once(doc, 'external', minutes=30)
        parties = ' — '.join(p for p in (doc.party_a_id.name, doc.party_b_id.name) if p)
        file_url = '/coop/doc/%s/file' % token
        body = Markup(
            '<p class="kind">%(kind)s%(date)s</p>'
            '<p class="muted">%(parties)s</p>'
            '<div class="print"><span>Отпечаток SHA-256</span><code id="known">%(print)s</code></div>'
            '%(frame)s'
            '<div class="row">%(download)s</div>'
            '<h2>Сверить свой экземпляр</h2>'
            '<p class="muted">Выберите файл, который у вас на руках. Отпечаток считается '
            'здесь, в вашем браузере, — файл никуда не отправляется.</p>'
            '<input type="file" id="mine"/><p id="verdict"></p>'
            '<script>%(script)s</script>'
        ) % {
            'kind': KINDS.get(doc.kind, 'Документ'),
            'date': (' от %s' % doc.signed_on.strftime('%d.%m.%Y')) if doc.signed_on else '',
            'parties': parties,
            'print': doc.fingerprint or '—',
            'frame': Markup('<iframe src="%s" title="Документ"></iframe>') % file_url
            if doc.file else Markup('<p class="muted">Файл не приложен.</p>'),
            'download': Markup('<a class="btn" href="%s?download=1">Скачать</a>') % file_url
            if share.allow_download and doc.file else '',
            'script': Markup(_VERIFY_JS),
        }
        return request.make_response(_page(doc.name, body))

    @http.route('/coop/doc/<string:token>/file', type='http', auth='public')
    def public_file(self, token, download=None, **kw):
        share = self._share(token)
        if not share or not self._unlocked(share) or not share.document_id.file:
            raise request.not_found()
        if download and not share.allow_download:
            raise request.not_found()
        data, name, mime = _content(share.document_id)
        return request.make_response(data, [
            ('Content-Type', mime),
            ('Content-Disposition', http.content_disposition(
                name, disposition_type='attachment' if download else 'inline')),
        ])


_VERIFY_JS = """
document.getElementById('mine').addEventListener('change', async (ev) => {
  const file = ev.target.files[0]; const out = document.getElementById('verdict');
  if (!file) { out.textContent = ''; return; }
  const hash = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
  const hex = [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, '0')).join('');
  const known = document.getElementById('known').textContent.trim();
  out.className = hex === known ? 'good' : 'bad';
  out.textContent = hex === known
    ? 'Тот самый документ: содержимое совпадает до байта.'
    : 'Это другой файл: содержимое не совпадает. Пересохранение или повторная печать в PDF '
      + 'тоже меняют отпечаток — сверяйте именно полученный файл.';
});
"""


def _page(title, body):
    return Markup(
        '<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>%(title)s — ДАО КООПТЕХ</title><style>'
        'body{margin:0;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:#1f2328;background:#f6f6f3}'
        'main{max-width:860px;margin:0 auto;padding:24px 16px}'
        'h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 4px}'
        '.brand{font-weight:800;letter-spacing:.02em;color:#146b64;margin-bottom:16px}'
        '.kind{margin:0;font-weight:600}.muted{color:#6c757d;margin:4px 0}'
        '.print{margin:14px 0;padding:10px 12px;background:#fff;border:1px solid #e3e3de;border-radius:8px;overflow-wrap:anywhere}'
        '.print span{display:block;font-size:12px;color:#6c757d}code{font-size:13px}'
        'iframe{width:100%%;height:70vh;border:1px solid #e3e3de;border-radius:8px;background:#fff}'
        '.row{margin:12px 0}.btn{display:inline-block;padding:8px 16px;border-radius:8px;background:#146b64;color:#fff;border:0;text-decoration:none;font:inherit;cursor:pointer}'
        '.inp{padding:8px 10px;border:1px solid #ccc;border-radius:8px;font:inherit}'
        '.good{color:#146b64;font-weight:600}.bad{color:#b42318;font-weight:600}'
        '</style></head><body><main><div class="brand">ДАО КООПТЕХ</div>'
        '<h1>%(title)s</h1>%(body)s</main></body></html>'
    ) % {'title': escape(title), 'body': body}
