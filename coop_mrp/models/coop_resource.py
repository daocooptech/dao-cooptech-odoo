# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError


def _duration(minutes):
    """«40 мин», «1 ч», «1 ч 30 мин» — как в эталоне `ProcessSteps`."""
    minutes = int(round(minutes or 0))
    hours, rest = divmod(minutes, 60)
    if not hours:
        return '%d мин' % rest
    return '%d ч %d мин' % (hours, rest) if rest else '%d ч' % hours


class CoopResource(models.Model):
    _inherit = 'coop.resource'

    # Решение 630: техпроцесс приходит из производственного учёта
    # организации-владельца. Поле — только у тех, кому открыт модуль
    # производства: чужим техкарта не читается, и без `groups` форма
    # ресурса падала бы у каждого смотрящего.
    bom_id = fields.Many2one(
        'mrp.bom', string='Техкарта', groups='mrp.group_mrp_user',
        domain="[('company_id', '=', coop_owner_company_id)]",
        help='Техкарта из «Производства» организации. Её операции — '
             'технологический процесс на карточке, если организация '
             'показывает техпроцесс.')
    coop_owner_company_id = fields.Many2one(
        'res.company', related='owner_id.coop_company_id')
    process_steps = fields.Json(compute='_compute_process', string='Технологический процесс')
    process_caption = fields.Char(compute='_compute_process')

    @api.depends('owner_id.coop_show_process')
    def _compute_process(self):
        for resource in self:
            steps, caption = resource._coop_process()
            resource.process_steps = steps or False
            resource.process_caption = caption

    def _coop_process_bom(self):
        """Техкарта, которую владелец согласился показать, иначе пусто."""
        resource = self.sudo()
        if not resource.owner_id.coop_show_process:
            return resource.env['mrp.bom']
        return resource.bom_id

    def _coop_process_batch(self, bom):
        """Партия — последний выпуск по техкарте."""
        return self.env['mrp.production'].sudo().search(
            [('bom_id', '=', bom.id), ('state', '=', 'done')],
            order='date_finished desc, id desc', limit=1)

    def _coop_process(self):
        """Этапы — участки подряд, операции — операции техкарты.

        В движке операции плоские, а эталон показывает этапы с
        операциями внутри: этапом считается участок (рабочий центр),
        на котором идут подряд несколько операций.
        """
        self.ensure_one()
        bom = self._coop_process_bom()
        if not bom or not bom.operation_ids:
            return [], False
        batch = self._coop_process_batch(bom)
        done = {wo.operation_id.id for wo in batch.workorder_ids if wo.state == 'done'}
        steps = []
        for op in bom.operation_ids.sorted(lambda o: (o.sequence, o.id)):
            if not steps or steps[-1]['workcenter'] != op.workcenter_id.id:
                steps.append({'workcenter': op.workcenter_id.id, 'title': op.workcenter_id.name,
                              'minutes': 0, 'children': []})
            stage = steps[-1]
            stage['minutes'] += op.time_cycle
            links = []
            if op.coop_instruction:
                links.append({'kind': 'instruction', 'label': 'Инструкция', 'op': op.id})
            if op.id in done:
                links.append({'kind': 'result', 'label': 'Результат', 'op': op.id})
            stage['children'].append({'title': op.name, 'duration': _duration(op.time_cycle),
                                      'links': links})
        total = sum(s['minutes'] for s in steps)
        for stage in steps:
            stage['duration'] = _duration(stage['minutes'])
            del stage['workcenter']
        count = len(steps)
        word = 'этап' if count % 10 == 1 and count % 100 != 11 else (
            'этапа' if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14 else 'этапов')
        caption = '%d %s · %s' % (count, word, _duration(total))
        if batch:
            caption = 'Партия № %s от %s · %s на %s %s' % (
                batch.name, batch.date_finished.strftime('%d.%m.%Y'), caption,
                ('%g' % batch.qty_produced).replace('.', ','), batch.uom_id.name)
        return steps, caption

    def coop_process_doc(self, operation_id, kind):
        """Инструкция или результат операции — для окна на витрине.

        Читается от имени системы: смотрящему техкарта чужой организации
        не открыта. Поэтому только та операция, что видна в блоке.
        """
        self.ensure_one()
        self.check_access('read')
        bom = self._coop_process_bom()
        op = bom.operation_ids.filtered(lambda o: o.id == operation_id)
        if not op:
            raise UserError('Эта операция на карточке не показывается.')
        if kind == 'instruction':
            return {'title': '%s — инструкция' % op.name, 'body': op.coop_instruction or ''}
        batch = self._coop_process_batch(bom)
        wo = batch.workorder_ids.filtered(lambda w: w.operation_id == op and w.state == 'done')[:1]
        if not wo:
            raise UserError('В последней партии эта операция не выполнялась.')
        rows = [
            ('Партия', batch.name),
            ('Участок', wo.workcenter_id.name),
            ('Закончена', fields.Datetime.context_timestamp(self, wo.date_finished).strftime('%d.%m.%Y %H:%M')
             if wo.date_finished else '—'),
            ('Заняло', _duration(wo.duration)),
            ('По плану', _duration(wo.duration_expected)),
            ('Выпущено', '%s %s' % (('%g' % wo.qty_produced).replace('.', ','), batch.uom_id.name)),
        ]
        body = Markup('<dl class="coop-process_doc">%s</dl>') % Markup('').join(
            Markup('<dt>%s</dt><dd>%s</dd>') % (escape(k), escape(v)) for k, v in rows)
        return {'title': '%s — результат' % op.name, 'body': body}
