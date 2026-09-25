# -*- coding: utf-8 -*-
"""Документы как у облачных дисков — но про документы сделок.

Владелец 25 сентября 2026 выбрал все восемь предложений разбора
(`Матчасть/2026-09-25 — Облачные диски и раздел документов — что взять`):

1. версии, у каждой свой отпечаток; подписанную можно закрепить;
2. просмотр в браузере и первая страница на плитке;
3. разделы: все, недавние, избранное, жду подписи, доступные мне, корзина;
4. журнал действий по документу;
5. ссылка для внешней стороны со сроком, паролем и сверкой;
6. корзина на 30 дней;
7. загрузка папкой и действия над многими сразу;
8. скан камерой телефона в PDF.
"""
import base64
import hashlib
import io
import secrets
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

TRASH_DAYS = 30


def _sha256_b64(value):
    if not value:
        return False
    raw = value.encode('ascii', errors='ignore') if isinstance(value, str) else value
    try:
        content = base64.b64decode(raw)
    except Exception:
        content = raw
    return hashlib.sha256(content).hexdigest()


class CoopDocumentVersion(models.Model):
    """Редакция документа. Новая не затирает старую."""
    _name = 'coop.document.version'
    _description = 'Версия документа'
    _order = 'document_id, number desc'

    document_id = fields.Many2one('coop.document', required=True, index=True,
                                  ondelete='cascade')
    number = fields.Integer(string='Редакция', required=True)
    file = fields.Binary(string='Файл', attachment=True)
    file_name = fields.Char(string='Имя файла')
    fingerprint = fields.Char(string='Отпечаток', index=True)
    author_id = fields.Many2one('res.partner', string='Кто загрузил',
                                default=lambda self: self.env.user.partner_id)
    date = fields.Datetime(string='Когда', default=fields.Datetime.now, required=True)
    pinned = fields.Boolean(
        string='Закреплена',
        help='Закреплённую редакцию не удалить — так хранится подписанная.')
    note = fields.Char(string='Что изменилось')

    def unlink(self):
        if any(v.pinned for v in self) and not self.env.context.get('coop_purge'):
            raise UserError(_('Закреплённая редакция не удаляется.'))
        return super().unlink()


class CoopDocumentLog(models.Model):
    """Журнал действий: кто и что делал с документом. Для спора он ценнее
    самого файла. Пишется только кодом, правки нет."""
    _name = 'coop.document.log'
    _description = 'Действие с документом'
    _order = 'date desc, id desc'

    document_id = fields.Many2one('coop.document', required=True, index=True,
                                  ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Кто')
    action = fields.Selection([
        ('uploaded', 'Загружен'),
        ('version', 'Новая редакция'),
        ('opened', 'Открыт'),
        ('downloaded', 'Скачан'),
        ('signed', 'Подписан'),
        ('checked_ok', 'Сверен — совпал'),
        ('checked_bad', 'Сверен — не совпал'),
        ('shared', 'Выдана ссылка'),
        ('external', 'Открыт по ссылке'),
        ('trashed', 'В корзине'),
        ('restored', 'Восстановлен'),
        ('moved', 'Переложен'),
    ], string='Что', required=True)
    date = fields.Datetime(string='Когда', default=fields.Datetime.now, required=True)
    note = fields.Char(string='Подробности')


class CoopDocumentShare(models.Model):
    """Ссылка для внешней стороны: только просмотр, срок и пароль по выбору.

    Контрагент без учётной записи открывает документ и сверяет свой
    экземпляр — отпечаток считается в его браузере, файл никуда не уходит.
    """
    _name = 'coop.document.share'
    _description = 'Ссылка на документ'
    _order = 'create_date desc'

    document_id = fields.Many2one('coop.document', required=True, index=True,
                                  ondelete='cascade')
    token = fields.Char(required=True, index=True, copy=False,
                        default=lambda self: secrets.token_urlsafe(18))
    expires_on = fields.Date(string='Действует до')
    password_hash = fields.Char()
    has_password = fields.Boolean(compute='_compute_has_password')
    allow_download = fields.Boolean(string='Можно скачать', default=True)
    active = fields.Boolean(default=True)
    views = fields.Integer(string='Открыта раз', readonly=True)
    url = fields.Char(string='Ссылка', compute='_compute_url')
    state = fields.Selection([('active', 'Действует'), ('expired', 'Истекла'),
                              ('revoked', 'Отозвана')], compute='_compute_state')

    _token_uniq = models.Constraint('unique(token)', 'Такая ссылка уже есть.')

    def _compute_has_password(self):
        for share in self:
            share.has_password = bool(share.password_hash)

    def _compute_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for share in self:
            share.url = '%s/coop/doc/%s' % (base, share.token)

    def _compute_state(self):
        today = fields.Date.context_today(self)
        for share in self:
            if not share.active:
                share.state = 'revoked'
            elif share.expires_on and share.expires_on < today:
                share.state = 'expired'
            else:
                share.state = 'active'

    @staticmethod
    def _hash_password(token, password):
        return hashlib.sha256(('%s:%s' % (token, password)).encode()).hexdigest()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            password = vals.pop('password', None)
            vals.setdefault('token', secrets.token_urlsafe(18))
            if password:
                vals['password_hash'] = self._hash_password(vals['token'], password)
        shares = super().create(vals_list)
        for share in shares:
            share.document_id._coop_log('shared', note=share.expires_on and _(
                'до %s', share.expires_on) or _('без срока'))
        return shares

    def check_password(self, password):
        self.ensure_one()
        if not self.password_hash:
            return True
        return self._hash_password(self.token, password or '') == self.password_hash

    def action_revoke(self):
        self.write({'active': False})


class CoopDocument(models.Model):
    _inherit = 'coop.document'

    active = fields.Boolean(default=True, index=True)
    trashed_on = fields.Date(string='В корзине с', readonly=True)
    purge_on = fields.Date(string='Удалится', compute='_compute_purge_on')
    version_ids = fields.One2many('coop.document.version', 'document_id', string='Редакции')
    version_count = fields.Integer(string='Редакций', compute='_compute_version_count')
    log_ids = fields.One2many('coop.document.log', 'document_id', string='Журнал')
    share_ids = fields.One2many('coop.document.share', 'document_id', string='Ссылки',
                                context={'active_test': False})
    is_pdf = fields.Boolean(compute='_compute_is_pdf')
    preview_html = fields.Html(compute='_compute_preview_html', sanitize=False)
    awaits_me = fields.Boolean(string='Жду подписи', compute='_compute_awaits_me',
                               search='_search_awaits_me')
    shared_with_me = fields.Boolean(string='Доступные мне', compute='_compute_shared_with_me',
                                    search='_search_shared_with_me')
    coop_is_favorite = fields.Boolean(string='В избранном', compute='_compute_favorite',
                                      search='_search_favorite')

    # ── Вычисления ──────────────────────────────────────────────────

    def _compute_purge_on(self):
        for doc in self:
            doc.purge_on = doc.trashed_on + timedelta(days=TRASH_DAYS) if doc.trashed_on else False

    def _compute_version_count(self):
        for doc in self:
            doc.version_count = len(doc.version_ids)

    def _compute_is_pdf(self):
        for doc in self:
            doc.is_pdf = (doc.file_name or '').lower().endswith('.pdf')

    def _compute_preview_html(self):
        for doc in self:
            if not doc.id or not doc.file:
                doc.preview_html = False
                continue
            # Через свой адрес, а не `/web/content`: открытие пишется в журнал.
            doc.preview_html = Markup(
                '<iframe class="o_coop_doc_preview" src="/coop/document/%d/view" '
                'title="Просмотр"></iframe>') % doc.id

    def _compute_awaits_me(self):
        mine = self.env.user.coop_actor_partner_ids
        for doc in self:
            doc.awaits_me = (doc.state == 'draft' and bool(doc.file)
                             and (doc.party_a_id in mine or doc.party_b_id in mine))

    def _search_awaits_me(self, operator, value):
        ids = self.env.user.coop_actor_partner_ids.ids
        found = self.search([('state', '=', 'draft'), ('file', '!=', False), '|',
                             ('party_a_id', 'in', ids), ('party_b_id', 'in', ids)]).ids
        positive = (operator == '=') == bool(value)
        return [('id', 'in' if positive else 'not in', found)]

    def _compute_shared_with_me(self):
        mine = self.env.user.coop_actor_partner_ids
        for doc in self:
            doc.shared_with_me = doc.party_b_id in mine and doc.party_a_id not in mine

    def _search_shared_with_me(self, operator, value):
        ids = self.env.user.coop_actor_partner_ids.ids
        found = self.search([('party_b_id', 'in', ids), ('party_a_id', 'not in', ids)]).ids
        positive = (operator == '=') == bool(value)
        return [('id', 'in' if positive else 'not in', found)]

    def _compute_favorite(self):
        ids = set(self.env['coop.favorite'].coop_ids_for(self._name))
        for doc in self:
            doc.coop_is_favorite = doc.id in ids

    def _search_favorite(self, operator, value):
        ids = self.env['coop.favorite'].coop_ids_for(self._name)
        positive = (operator == '=') == bool(value)
        return [('id', 'in' if positive else 'not in', ids)]

    # ── Журнал и редакции ───────────────────────────────────────────

    def _coop_log(self, action, note=False, partner=None, date=None):
        Log = self.env['coop.document.log'].sudo()
        for doc in self:
            vals = {'document_id': doc.id, 'action': action, 'note': note or False,
                    'partner_id': (partner or self.env.user.partner_id).id}
            if date:
                vals['date'] = date
            Log.create(vals)

    def _coop_snapshot(self, note=False):
        """Текущий файл — новой редакцией, если он не совпадает с последней."""
        Version = self.env['coop.document.version'].sudo()
        for doc in self.sudo():
            if not doc.file:
                continue
            last = Version.search([('document_id', '=', doc.id)], order='number desc', limit=1)
            print_ = doc.fingerprint or _sha256_b64(doc.file)
            if last and last.fingerprint == print_:
                continue
            Version.create({
                'document_id': doc.id,
                'number': (last.number or 0) + 1,
                'file': doc.file,
                'file_name': doc.file_name,
                'fingerprint': print_,
                'note': note or False,
            })
            doc.with_env(self.env)._coop_log('uploaded' if not last else 'version',
                                             note=_('редакция %s', (last.number or 0) + 1))

    @api.model_create_multi
    def create(self, vals_list):
        docs = super().create(vals_list)
        if not self.env.context.get('coop_no_snapshot'):
            docs._coop_snapshot()
        return docs

    def write(self, vals):
        result = super().write(vals)
        if 'file' in vals and not self.env.context.get('coop_no_snapshot'):
            self._coop_snapshot()
        return result

    def action_sign(self):
        result = super().action_sign()
        for doc in self:
            last = doc.version_ids.sorted('number', reverse=True)[:1]
            last.sudo().pinned = True
            doc._coop_log('signed', note=_('редакция %s закреплена', last.number or 1))
        return result

    # ── Действия ────────────────────────────────────────────────────

    def action_download(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': '/coop/document/%d/download' % self.id,
                'target': 'self'}

    def action_trash(self):
        for doc in self:
            if doc.state == 'signed':
                raise UserError(_('Подписанный документ хранится и в корзину не '
                                  'кладётся. Отмените его, если он больше не действует.'))
        self.write({'active': False, 'trashed_on': fields.Date.context_today(self)})
        self._coop_log('trashed')
        return True

    def action_restore(self):
        self.write({'active': True, 'trashed_on': False})
        self._coop_log('restored')
        return True

    def action_share(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ссылка для внешней стороны'),
            'res_model': 'coop.document.share.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_document_id': self.id},
        }

    @api.model
    def _cron_purge_trash(self):
        """Корзина хранит 30 дней, потом документ удаляется насовсем."""
        limit = fields.Date.context_today(self) - timedelta(days=TRASH_DAYS)
        old = self.sudo().with_context(active_test=False, coop_purge=True).search([
            ('active', '=', False), ('trashed_on', '<=', limit), ('state', '!=', 'signed')])
        old.version_ids.with_context(coop_purge=True).unlink()
        old.unlink()
        return len(old)

    # ── Загрузка многих файлов и скан ───────────────────────────────

    @api.model
    def action_open_upload(self):
        """Кнопка «Загрузить» на месте «Нового» (Н10, владелец 25.09):
        открывает экран загрузки — файлы и папки перетаскиванием, скан
        камерой, — а не пустую карточку документа."""
        return self.env['ir.actions.actions']._for_xml_id(
            'coop_documents.action_coop_documents_upload')

    @api.model
    def coop_upload(self, files, folder_id=False):
        """Загрузить файлы разом; `path` у файла — путь внутри выбранной
        папки («Стройка/Акты/акт-3.pdf»): недостающие папки заводятся.

        Каждый файл — документ-черновик от имени действующего участника.
        """
        Folder = self.env['coop.document.folder']
        owner = self.env.user._coop_acting_partner()
        cache = {}

        def folder_for(path):
            parts = [p for p in (path or '').split('/')[:-1] if p]
            parent = Folder.browse(folder_id) if folder_id else Folder
            key = ()
            for part in parts:
                key += (part,)
                if key not in cache:
                    found = Folder.search([('name', '=', part), ('partner_id', '=', owner.id),
                                           ('parent_id', '=', parent.id or False)], limit=1)
                    cache[key] = found or Folder.create({
                        'name': part, 'partner_id': owner.id, 'parent_id': parent.id or False})
                parent = cache[key]
            return parent

        created = self.browse()
        for item in files or []:
            name = (item.get('name') or 'Файл').strip()
            title = name.rsplit('.', 1)[0] if '.' in name else name
            folder = folder_for(item.get('path') or name)
            created |= self.create({
                'name': title[:200],
                'kind': 'other',
                'file': item.get('data'),
                'file_name': name,
                'folder_id': folder.id or False,
            })
        return created.ids

    @api.model
    def coop_scan(self, images, name=False, folder_id=False):
        """Снимки с камеры — одним PDF, страница на снимок."""
        from PIL import Image
        pages = []
        for data in images or []:
            img = Image.open(io.BytesIO(base64.b64decode(data)))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            # Не больше 1600 точек по длинной стороне: скан акта, а не
            # фотоархив — и файл остаётся лёгким.
            img.thumbnail((1600, 1600))
            pages.append(img)
        if not pages:
            raise UserError(_('Нет снимков.'))
        out = io.BytesIO()
        pages[0].save(out, format='PDF', save_all=True, append_images=pages[1:],
                      resolution=150.0)
        title = name or _('Скан от %s', fields.Date.context_today(self).strftime('%d.%m.%Y'))
        doc = self.create({
            'name': title,
            'kind': 'act',
            'file': base64.b64encode(out.getvalue()),
            'file_name': '%s.pdf' % title,
            'folder_id': folder_id or False,
        })
        return doc.id


class CoopDocumentShareWizard(models.TransientModel):
    _name = 'coop.document.share.wizard'
    _description = 'Выдать ссылку на документ'

    document_id = fields.Many2one('coop.document', required=True)
    expires_on = fields.Date(string='Действует до',
                             default=lambda self: fields.Date.context_today(self) + timedelta(days=14))
    password = fields.Char(string='Пароль (по желанию)')
    allow_download = fields.Boolean(string='Можно скачать', default=True)
    url = fields.Char(string='Ссылка', readonly=True)

    def action_create(self):
        self.ensure_one()
        share = self.env['coop.document.share'].sudo().create({
            'document_id': self.document_id.id,
            'expires_on': self.expires_on,
            'password': self.password or False,
            'allow_download': self.allow_download,
        })
        self.url = share.url
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'coop_share_done': True},
        }


class CoopDocumentMoveWizard(models.TransientModel):
    _name = 'coop.document.move.wizard'
    _description = 'Переложить документы в папку'

    document_ids = fields.Many2many('coop.document')
    folder_id = fields.Many2one('coop.document.folder', string='В папку')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        ids = self.env.context.get('active_ids') or []
        values['document_ids'] = [(6, 0, ids)]
        return values

    def action_move(self):
        self.document_ids.write({'folder_id': self.folder_id.id or False})
        self.document_ids._coop_log('moved', note=self.folder_id.complete_name or _('без папки'))
        return {'type': 'ir.actions.act_window_close'}
