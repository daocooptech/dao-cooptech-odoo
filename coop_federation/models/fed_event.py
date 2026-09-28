# -*- coding: utf-8 -*-
"""Журнал узла: только дописываемый, связанный хэшами, подписанный.

Событие попадает в журнал в два шага (transactional outbox):

1. деловая транзакция кладёт строку `pending` — тип, предмет, тело. Та же
   транзакция, тот же курсор: откатилось действие — откатилось и событие.
   Ни подписи, ни сети внутри действия пользователя;
2. запечатывание (задание раз в минуту и сразу после постановки) берёт
   блокировку записи узла, раздаёт `seq` и `prev` по порядку и подписывает.
   Номер выдаётся при печати, а не при вставке — параллельные транзакции не
   спорят за номер.

Подписанное событие хранится целиком в `raw` — ровно те байты, что уйдут
соседям: восстанавливать конверт из полей значило бы рисковать другой
сериализацией. Запечатанную строку нельзя ни изменить, ни удалить — это
держит триггер в самой базе, а не метод `write`: загрузчики и ручные
запросы ходят мимо ORM.
"""
import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..lib.fedproto import canonical, log as fed_log
from .fed_identity import utc_now

_logger = logging.getLogger(__name__)


class CoopFedEvent(models.Model):
    _name = 'coop.fed.event'
    _description = 'Событие журнала узла'
    _order = 'node, seq, id'

    origin = fields.Selection([('local', 'Наше'), ('peer', 'Соседа')],
                              default='local', required=True, readonly=True)
    node = fields.Char('Узел-автор', required=True, readonly=True, index=True)
    seq = fields.Integer('Номер', readonly=True)
    prev = fields.Char(readonly=True)
    event_id = fields.Char('Идентификатор', readonly=True, index=True)
    kid = fields.Char(readonly=True)
    ts = fields.Char('Время (UTC)', readonly=True)
    type = fields.Char('Тип', required=True, readonly=True, index=True)
    subject = fields.Char('Предмет', required=True, readonly=True, index=True)
    to_json = fields.Char('Адресаты', readonly=True)
    body_json = fields.Text('Тело', readonly=True)
    body_hash = fields.Char(readonly=True)
    sig = fields.Char(readonly=True)
    raw = fields.Text('Событие целиком', readonly=True)
    status = fields.Selection([
        ('pending', 'Ждёт печати'),
        ('ok', 'Подписано'),
        ('suspect', 'Сомнительно'),
        ('deferred', 'Отложено — пропуск в номерах'),
        ('rejected', 'Отвергнуто'),
        ('unknown_type', 'Незнакомый тип — сохранено'),
    ], string='Состояние', default='pending', required=True, readonly=True, index=True)
    reason = fields.Char('Причина', readonly=True)

    _node_seq_uniq = models.UniqueIndex('(node, seq) WHERE seq IS NOT NULL',
                                        'Номер в журнале узла не повторяется.')
    _event_id_uniq = models.UniqueIndex('(event_id) WHERE event_id IS NOT NULL',
                                        'Событие с таким идентификатором уже есть.')

    def init(self):
        # Запечатанное — неизменяемо. Меняться может только служебное
        # состояние чужих событий (переподтверждение сомнительного), но не
        # конверт, тело или подпись.
        self.env.cr.execute("""
            CREATE OR REPLACE FUNCTION coop_fed_event_sealed() RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    IF OLD.seq IS NOT NULL THEN
                        RAISE EXCEPTION 'coop.fed.event: запечатанное событие удалять нельзя';
                    END IF;
                    RETURN OLD;
                END IF;
                IF OLD.seq IS NOT NULL AND (
                       NEW.node IS DISTINCT FROM OLD.node
                    OR NEW.seq IS DISTINCT FROM OLD.seq
                    OR NEW.prev IS DISTINCT FROM OLD.prev
                    OR NEW.event_id IS DISTINCT FROM OLD.event_id
                    OR NEW.kid IS DISTINCT FROM OLD.kid
                    OR NEW.ts IS DISTINCT FROM OLD.ts
                    OR NEW.type IS DISTINCT FROM OLD.type
                    OR NEW.subject IS DISTINCT FROM OLD.subject
                    OR NEW.to_json IS DISTINCT FROM OLD.to_json
                    OR NEW.body_json IS DISTINCT FROM OLD.body_json
                    OR NEW.body_hash IS DISTINCT FROM OLD.body_hash
                    OR NEW.sig IS DISTINCT FROM OLD.sig
                    OR NEW.raw IS DISTINCT FROM OLD.raw) THEN
                    RAISE EXCEPTION 'coop.fed.event: запечатанное событие менять нельзя';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            DROP TRIGGER IF EXISTS coop_fed_event_sealed ON coop_fed_event;
            CREATE TRIGGER coop_fed_event_sealed BEFORE UPDATE OR DELETE ON coop_fed_event
                FOR EACH ROW EXECUTE FUNCTION coop_fed_event_sealed();
        """)

    # -- постановка -------------------------------------------------------

    @api.model
    def _enqueue(self, type_, subject, body, to=None):
        """Положить событие в очередь на печать. Тело канонизируется сразу:
        дробное число или иной непредставимый тип — ошибка здесь, в
        транзакции автора, а не молчаливый пропуск при печати."""
        identity = self.env['coop.fed.identity'].sudo().search([], limit=1)
        if not identity:
            raise UserError('Узел сети ещё не заведён.')
        record = self.sudo().create({
            'origin': 'local',
            'node': identity.did,
            'type': type_,
            'subject': subject,
            'body_json': canonical.dumps(body),
            'to_json': json.dumps(list(to)) if to is not None else False,
            'status': 'pending',
        })
        cron = self.env.ref('coop_federation.cron_coop_fed_seal', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()
        return record

    # -- печать -----------------------------------------------------------

    @api.model
    def _seal(self):
        """Раздать номера и подписать очередь. Возвращает число запечатанных."""
        identity = self.env['coop.fed.identity'].sudo().search([], limit=1)
        if not identity:
            return 0
        # Номера раздаёт один процесс за раз: остальные ждут блокировку.
        self.env.cr.execute('SELECT id FROM coop_fed_identity WHERE id = %s FOR UPDATE',
                            [identity.id])
        identity.invalidate_recordset()
        pending = self.sudo().search([('origin', '=', 'local'), ('status', '=', 'pending'),
                                      ('node', '=', identity.did)], order='id')
        if not pending:
            return 0
        try:
            key, secret = identity._secret()
        except UserError as error:
            identity.last_error = str(error)
            _logger.error('Федерация: печать остановлена — %s', error)
            return 0
        for event in pending:
            seq = identity.head_seq + 1
            to = json.loads(event.to_json) if event.to_json else None
            draft = fed_log.make(
                node=identity.did, kid=key.kid, seq=seq,
                prev=identity.head_event or None, ts=utc_now(),
                type_=event.type, subject=event.subject,
                body=json.loads(event.body_json), to=to)
            signed = fed_log.sign(draft, secret)
            event.write({
                'seq': seq,
                'prev': signed['prev'],
                'event_id': signed['id'],
                'kid': key.kid,
                'ts': signed['ts'],
                'body_hash': signed['body_hash'],
                'sig': signed['sig'],
                'raw': canonical.dumps(signed),
                'status': 'ok',
            })
            identity.write({'head_seq': seq, 'head_event': signed['id']})
        identity._sign_head(key, secret)
        identity.last_error = False
        return len(pending)

    @api.model
    def _cron_seal(self):
        self._seal()

    # -- выдача -----------------------------------------------------------

    def as_signed(self):
        """Событие ровно в том виде, в каком оно подписано."""
        self.ensure_one()
        return json.loads(self.raw)

    @api.model
    def journal(self, identity, since=0, limit=100, reader=None):
        """Порция журнала для GET /federation/log.

        `reader` — уже подтверждённый подписью запроса читатель. Адресное
        событие не ему отдаётся вымаранным: конверт целиком, тело отцеплено.
        """
        # Без условия `seq != False`: для целого поля Odoo понимает его как
        # «не ноль» и молча выбрасывает первое событие журнала — цепочка
        # у соседа начиналась бы с единицы. Запечатанность и так видна по
        # состоянию: у `ok` и `suspect` номер есть всегда.
        events = self.sudo().search([
            ('node', '=', identity.did), ('seq', '>=', since),
            ('status', 'in', ('ok', 'suspect'))], order='seq', limit=limit)
        out = []
        for event in events:
            signed = event.as_signed()
            audience = signed.get('to')
            if audience is not None and reader not in audience and reader != identity.did:
                signed = fed_log.redact(signed)
            out.append(signed)
        return out
