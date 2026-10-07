# -*- coding: utf-8 -*-
"""Этот узел сети: его идентификатор, ключ и голова журнала.

Узел — организация (решение 108), один `did:web` на всю платформу
(решение 430, п. 2): платформа подписывает события своих организаций и
людей, сторона внутри события названа в теле. Организация, ушедшая на свой
сервер, получит свой адрес — переход заложен, но не сделан.

Секрет ключа в базе не хранится — только путь к файлу вне базы и вне
репозитория (`<data_dir>/federation/<база>/`). Копия базы на другой машине
ключа не получает и подписать ничего не может: иначе два экземпляра под
одним DID дали бы два разных журнала — для соседей это доказанное
раздвоение, улика подделки.
"""
import datetime
import logging
import os
import urllib.parse

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import config

from odoo.addons.coop_theme.node_path import NODE_PATH

from ..lib import crypto
from ..lib.fedproto import canonical, did as fed_did, log as fed_log

_logger = logging.getLogger(__name__)

TS_FORMAT = '%Y-%m-%dT%H:%M:%SZ'


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(TS_FORMAT)


def did_for_url(url):
    """did:web по адресу платформы: порт — через %3A, как велит спецификация."""
    parsed = urllib.parse.urlparse(url if '//' in (url or '') else '//' + (url or ''))
    host = (parsed.hostname or '').lower()
    if not host:
        raise UserError('Не задан адрес узла — не из чего сделать did:web.')
    if parsed.port:
        host += '%3A' + str(parsed.port)
    return 'did:web:' + host


def configured_host():
    """Адрес узла в сети — только явной строкой `coop_node_host` в odoo.conf.

    Не из `web.base.url`: на боевой он заморожен на http://localhost:8069
    (28.09.2026), и узел получил бы чужой идентификатор. Идентификатор —
    навсегда: сменить его значит переехать всей сетью. Поэтому без явной
    настройки узел не заводится вовсе.
    """
    host = (config.get('coop_node_host') or '').strip().strip('/')
    if not host:
        raise UserError('В odoo.conf нет строки coop_node_host (например, '
                        'coop_node_host = 217.15.207.46) — адрес узла в сети не задан.')
    return host


def base_url_for_host(host):
    """Адрес платформы для узла: у доменного имени — https (так did:web
    ищет документ, и сертификат есть только у имени — daocoop.tech,
    решение 433), у голого IP и localhost — http."""
    name = urllib.parse.urlparse('//' + host).hostname or ''
    bare = name == 'localhost' or name.replace('.', '').isdigit() or ':' in name
    return ('http://' if bare else 'https://') + host


class CoopFedIdentity(models.Model):
    _name = 'coop.fed.identity'
    _description = 'Узел сети'

    name = fields.Char('Название', required=True)
    did = fields.Char('Идентификатор (did:web)', required=True, readonly=True)
    node_path = fields.Char('Имя в адресной строке', readonly=True,
                            help='nn1, nn2… — задаётся строкой coop_node_path в odoo.conf.')
    base_url = fields.Char('Адрес', readonly=True)
    country_id = fields.Many2one('res.country', string='Страна (юрисдикция)')
    state = fields.Selection([
        ('active', 'Подписывает'),
        ('detached', 'Отцеплен — копия базы, не подписывает'),
    ], string='Состояние', default='active', required=True, readonly=True)
    head_seq = fields.Integer('Последний номер', default=-1, readonly=True)
    head_event = fields.Char('Последнее событие', readonly=True)
    head_ts = fields.Char('Голова журнала подписана (UTC)', readonly=True)
    head_sig = fields.Char(readonly=True)
    last_error = fields.Char('Последняя ошибка', readonly=True)
    key_ids = fields.One2many('coop.fed.key', 'identity_id', string='Ключи')

    _did_uniq = models.Constraint('unique(did)', 'Идентификатор узла уникален.')

    # -- ключ -------------------------------------------------------------

    @api.model
    def _key_dir(self):
        path = os.path.join(config['data_dir'], 'federation', self.env.cr.dbname)
        os.makedirs(path, mode=0o700, exist_ok=True)
        return path

    def _working_key(self, when=None):
        self.ensure_one()
        keys = self.key_ids.filtered(
            lambda k: k.purpose == 'working' and k.secret_path and not k.revoked_at)
        if not keys:
            raise UserError('У узла нет действующего рабочего ключа.')
        return keys.sorted('not_before')[-1]

    def _secret(self):
        """Секрет рабочего ключа из файла. Отказ, если файла нет или он не
        от того ключа, что объявлен: подписать чужим ключом нельзя никогда."""
        self.ensure_one()
        if self.state != 'active':
            raise UserError('Узел отцеплен (копия базы): подписывать нечем и нельзя.')
        key = self._working_key()
        try:
            with open(key.secret_path, 'rb') as handle:
                secret = handle.read()
        except OSError:
            raise UserError('Нет файла ключа %s — копия базы или потерянный ключ.' % key.secret_path)
        if len(secret) != 32 or fed_log.b64(crypto.public_key(secret)) != key.public_key:
            raise UserError('Файл ключа %s не соответствует объявленному ключу.' % key.secret_path)
        return key, secret

    # -- установка --------------------------------------------------------

    @api.model
    def _ensure(self):
        """Узел, ключ и первое событие журнала. Идемпотентно."""
        identity = self.search([], limit=1)
        if identity:
            return identity
        host = configured_host()
        company = self.env.company
        identity = self.create({
            'name': company.name or 'Платформа',
            'did': did_for_url(host),
            'node_path': NODE_PATH,
            'base_url': base_url_for_host(host),
            'country_id': company.country_id.id,
        })
        secret = crypto.generate()
        kid = identity.did + '#key-1'
        path = os.path.join(self._key_dir(), 'key-1.key')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(secret)
        self.env['coop.fed.key'].create({
            'identity_id': identity.id,
            'kid': kid,
            'owner_did': identity.did,
            'public_key': fed_log.b64(crypto.public_key(secret)),
            'purpose': 'working',
            'not_before': utc_now(),
            'secret_path': path,
        })
        identity._announce()
        return identity

    def _announce(self):
        """node.announced — кто мы. Реквизиты организации, не людей: можно всем."""
        self.ensure_one()
        company = self.env.company
        self.env['coop.fed.event']._enqueue('node.announced', self.did, {
            'name': self.name,
            'regions': [company.city] if company.city else [],
            'software': 'odoo/rudoo-20',
            'protocols': ['https-pull'],
            'jurisdiction': {
                'country': (self.country_id.code or '').upper(),
                # Правовая форма — на карточке партнёра компании (`coop_orgs`),
                # у `res.company` такого поля нет: на боевой 19 поле в
                # объявлении поэтому всегда уходило пустым (находка 432 п. 2).
                'legal_form': company.partner_id.coop_legal_form_id.name or ''
                if 'coop_legal_form_id' in company.partner_id._fields else '',
                'registry': 'ЕГРЮЛ' if self.country_id.code == 'RU' else '',
                # В 20 поля `res.company.company_registry` нет: берём ОГРН из
                # карточки компании (`coop_orgs`), если модуль стоит.
                'reg_number': company.partner_id.coop_ogrn
                if 'coop_ogrn' in company.partner_id._fields else '',
            },
        })

    # -- документ и голова ------------------------------------------------

    def did_document(self):
        self.ensure_one()
        keys = []
        for key in self.key_ids.filtered(lambda k: k.owner_did == self.did):
            keys.append({
                'kid': key.kid,
                'public_key': fed_log.unb64(key.public_key),
                'not_before': key.not_before,
                'revoked': key.revoked_at,
                'compromised': key.compromised_at,
            })
        return fed_did.document(self.did, keys)

    def keyring(self):
        """Ключи этого узла — для самопроверки журнала."""
        self.ensure_one()
        return fed_did.keyring(self.did_document(), self.did)

    def head(self):
        self.ensure_one()
        if not self.head_sig:
            return None
        key = self._working_key()
        return {'node': self.did, 'kid': key.kid, 'ts': self.head_ts,
                'seq': self.head_seq, 'id': self.head_event or None, 'sig': self.head_sig}

    def _sign_head(self, key, secret):
        self.ensure_one()
        ts = utc_now()
        body = {'node': self.did, 'kid': key.kid, 'ts': ts,
                'seq': self.head_seq, 'id': self.head_event or None}
        self.head_ts = ts
        self.head_sig = fed_log.b64(crypto.sign(secret, canonical.encode(body)))

    def action_seal_now(self):
        self.env['coop.fed.event']._seal()
        return True
