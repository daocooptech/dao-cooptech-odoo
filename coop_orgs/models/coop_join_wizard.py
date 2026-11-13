# -*- coding: utf-8 -*-
"""Заявление о вступлении в организацию — три шага (задача 445).

Модель членства описана до мелочей — основание участия, полномочия,
голос, дата приёма, основание приёма, — а подать заявление участник не
мог: на карточке организации были «Написать» и «Подписаться», и всё.

Владелец 13.11.2026: «пайщики и наемные работники это разные
экономические единицы, при обычной подаче заявки на вступление можно дать
описание процессу, какие плюсы и подводные камни от вступления, документы
кооператива». Отсюда три шага: что вас ждёт → документы с отметкой
«ознакомился» → заявление. Наёмного работника здесь больше нет: найм —
отдельный путь «Работать» (решение 678). Ассоциированный член — только у
сельхозкооперативов, остальным его не показываем (решение 679 п. 2). Без
устава на платформе заявления нет (решение 679 п. 4).
"""

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Форма организации → набор текстов «что получаете / чем рискуете».
FORM_PROFILE = {
    'po': 'po',
    'pk': 'pk', 'artel': 'pk',
    'spk': 'agri', 'sppk': 'agri', 'skpk': 'agri',
    'kpk': 'credit',
    'zhsk': 'housing', 'gsk': 'housing',
}

# Ассоциированный член — институт закона о сельхозкооперации (решение 679).
ASSOCIATE_FORMS = ('spk', 'sppk', 'skpk')

# Тексты — по разбору legal-counsel 14.11.2026 (Матчасть, задача 445).
PROFILES = {
    'po': {
        'gain': ['Преимущество при покупке и сдаче продукции общества',
                 'Выплаты из доходов общества — до 20 % доходов, по решению собрания',
                 'Один член — один голос на собрании, независимо от размера пая'],
        'risk': ['Ответственность по долгам общества — в пределах, записанных в уставе',
                 'Вступительный взнос не возвращается',
                 'Пай при выходе возвращают на условиях устава, действовавшего на день вступления'],
    },
    'pk': {
        'gain': ['Доля прибыли кооператива по личному трудовому и иному участию',
                 'Оплата труда деньгами и продукцией кооператива',
                 'Один член — один голос на собрании'],
        'risk': ['Нужен личный трудовой вклад — или дополнительный взнос, если устав это допускает',
                 'Субсидиарная ответственность по долгам кооператива — в размере из устава',
                 'Пай при выходе выплачивают после окончания года, по балансу'],
    },
    'agri': {
        'gain': ['Дивиденды на пай; с кооперативными выплатами — до 30 % прибыли на паи',
                 'Сбыт, переработка и снабжение для своего хозяйства через кооператив',
                 'Можно вступить ассоциированным членом: пай и дивиденды есть, '
                 'голос — только в пределах 20 % голосов членов'],
        'risk': ['Производственный кооператив: ответственность по долгам — не меньше 5 % пая',
                 'Потребительский: в пределах дополнительного взноса; по уставу — '
                 'и по долгам, возникшим до вашего вступления',
                 'Большая часть работ кооператива — для членов: участвовать надо делом'],
    },
    'credit': {
        'gain': ['Займы кооператива — только членам',
                 'Сбережения и проценты на пай по положению кооператива',
                 'Один член — один голос на собрании'],
        'risk': ['Дополнительный взнос на покрытие убытков — в течение 3 месяцев после баланса',
                 'Субсидиарная ответственность по долгам — в пределах невнесённой части '
                 'дополнительного взноса',
                 'Пай возвращают не раньше 90 дней после годовой отчётности; '
                 'вышедший отвечает за убытки года выхода'],
    },
    'housing': {
        'gain': ['Право пользоваться помещением или местом, пока выплачивается пай',
                 'Полностью внёсший паевой взнос получает помещение в собственность',
                 'Один член — один голос на собрании'],
        'risk': ['Убытки кооператива члены покрывают дополнительными взносами '
                 'в течение 3 месяцев после утверждения баланса',
                 'Субсидиарная ответственность по долгам — в пределах невнесённой '
                 'части дополнительного взноса',
                 'Вступительный взнос не возвращается; пай при выходе — по уставу'],
    },
}

GENERIC = {
    'gain': ['Пай и голос на собрании: один член — один голос',
             'Право на долю того, что кооператив распределяет между членами'],
    'risk': ['Ответственность по долгам кооператива — в пределах, записанных в уставе',
             'Вступительный взнос не возвращается; пай при выходе — по уставу'],
}


# Некоммерческие и ДАО: членство без пая (роль «Участник»).
NONPROFIT = {
    'gain': ['Голос на собрании и участие в делах организации',
             'Доступ к программам и проектам организации для участников'],
    'risk': ['Членские взносы по уставу; они не возвращаются',
             'Пая нет: при выходе имущество организации не делится'],
}


def _ul(items):
    return Markup('<ul class="mb-2">%s</ul>') % Markup('').join(
        Markup('<li>%s</li>') % item for item in items)


class CoopJoinWizard(models.TransientModel):
    _name = 'coop.org.join'
    _description = 'Заявление о вступлении в организацию'

    organization_id = fields.Many2one(
        'res.partner', string='Организация', required=True, readonly=True)
    is_cooperative = fields.Boolean(
        related='organization_id.coop_is_cooperative', readonly=True)
    step = fields.Selection([
        ('about', 'Что вас ждёт'),
        ('docs', 'Документы'),
        ('apply', 'Заявление'),
    ], string='Шаг', default='about', required=True)
    # Пришли из окна «Участвовать» проекта — «Назад» вернёт туда.
    project_id = fields.Many2one('coop.project', string='Проект')
    role_id = fields.Many2one(
        'coop.membership.role', string='Кем вступаете', required=True,
        ondelete='restrict', domain="[('id', 'in', allowed_role_ids)]",
        default=lambda self: self._default_join_role())
    allowed_role_ids = fields.Many2many(
        'coop.membership.role', string='Из чего выбирать',
        compute='_compute_allowed_role_ids')
    role_code = fields.Char(related='role_id.code', readonly=True)
    note = fields.Text(string='Пара слов о себе')
    acknowledged = fields.Boolean(
        string='Я ознакомился(лась) с документами кооператива')
    about_html = fields.Html(compute='_compute_texts', sanitize=False)
    docs_html = fields.Html(compute='_compute_texts', sanitize=False)
    # Почему заявление не подать (решения 677, 679 п. 4). Пусто — можно.
    block = fields.Selection([
        ('member', 'Уже член'),
        ('applied', 'Заявление подано'),
        ('closed', 'Не принимает'),
        ('no_charter', 'Нет устава'),
    ], compute='_compute_block')
    block_note = fields.Char(compute='_compute_block')
    # Гражданину КНР — предупреждение об одобрении SAFE (решение 503).
    safe_notice = fields.Boolean(compute='_compute_safe_notice')

    # По заявлению возникает только членство с паем. Наёмный сотрудник —
    # путь «Работать» (решение 678), не основание вступления.
    BY_APPLICATION = ('member', 'associate', 'participant')

    @api.model
    def _default_join_role(self):
        org = self.env['res.partner'].browse(
            self.env.context.get('default_organization_id'))
        code = 'member' if (not org or org.coop_is_cooperative) else 'participant'
        return self.env['coop.membership.role'].search(
            [('code', '=', code)], limit=1)

    def _form_code(self):
        return self.organization_id.coop_legal_form_id.code or ''

    @api.depends('role_id')
    def _compute_safe_notice(self):
        citizenship = self.env.user.partner_id._coop_citizenship()
        for record in self:
            record.safe_notice = (record.role_id.code in ('member', 'associate')
                                  and citizenship.code == 'CN')

    @api.depends('organization_id')
    def _compute_allowed_role_ids(self):
        """Только основания своей формы (решение 679 п. 2)."""
        roles = self.env['coop.membership.role'].search(
            [('code', 'in', self.BY_APPLICATION)])
        for record in self:
            group = record.organization_id.coop_legal_form_group_id
            allowed = roles.filtered(lambda r: r.fits_group(group))
            if record._form_code() not in ASSOCIATE_FORMS:
                allowed = allowed.filtered(lambda r: r.code != 'associate')
            record.allowed_role_ids = allowed

    @api.depends('organization_id')
    def _compute_block(self):
        for record in self:
            org = record.organization_id
            record.block, record.block_note = (
                org._coop_join_block() if org else (False, False))

    @api.depends('organization_id')
    def _compute_texts(self):
        for record in self:
            org = record.organization_id
            profile = (PROFILES.get(FORM_PROFILE.get(record._form_code()),
                                    GENERIC)
                       if org.coop_is_cooperative else NONPROFIT)

            def fee(value):
                return (_('%s ₽') % '{:,.0f}'.format(value).replace(',', ' ')
                        if value else _('размер задан уставом'))
            record.about_html = (
                Markup('<h5>Как это устроено</h5><p>Заявление → решение '
                       'правления → вступительный и паевой взнос → вклад в '
                       'проекты организации.</p><h5>Что получаете</h5>')
                + _ul(profile['gain'])
                + Markup('<h5>Чем рискуете</h5>') + _ul(profile['risk'])
                + Markup('<h5>Взносы</h5>')
                + _ul([_('Вступительный: %s') % fee(org.coop_entrance_fee),
                       _('Обязательный паевой: %s') % fee(org.coop_min_share_fee)]))
            rows = [
                (_('Устав'), org.coop_charter_url),
                (_('Положение о взносах и возврате пая'), org.coop_fees_rules_url),
                (_('Положение о распределении прибыли'), org.coop_profit_rules_url),
                (_('Последняя отчётность'), org.coop_report_url),
            ]
            items = []
            for title, url in rows:
                if url:
                    href = url if '://' in url else 'https://' + url
                    items.append(Markup(
                        '<li class="d-flex justify-content-between gap-2 py-2 border-bottom">'
                        '<span>%s</span><a href="%s" target="_blank" '
                        'rel="noopener">Открыть</a></li>') % (title, href))
                else:
                    items.append(Markup(
                        '<li class="d-flex justify-content-between gap-2 py-2 border-bottom">'
                        '<span>%s</span><span class="text-muted">не выложено</span>'
                        '</li>') % title)
            record.docs_html = Markup(
                '<ul class="list-unstyled mb-2">%s</ul>') % Markup('').join(items)

    # ── Шаги ──────────────────────────────────────────────────────────────

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Вступить в %s') % self.organization_id.name,
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_next(self):
        self.ensure_one()
        if self.block:
            raise UserError(self.block_note)
        if self.step == 'about':
            self.step = 'docs'
        elif self.step == 'docs':
            if not self.acknowledged:
                raise UserError(_('Отметьте, что ознакомились с документами.'))
            self.step = 'apply'
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        if self.step == 'apply':
            self.step = 'docs'
        elif self.step == 'docs':
            self.step = 'about'
        elif self.project_id:
            return self.project_id.action_contribute()
        else:
            return {'type': 'ir.actions.act_window_close'}
        return self._reopen()

    def action_follow(self):
        """«Сообщить, когда откроется» — подписка на организацию."""
        self.ensure_one()
        self.organization_id.sudo().message_subscribe(
            partner_ids=self.env.user.partner_id.ids)
        return {'type': 'ir.actions.act_window_close'}

    def action_withdraw(self):
        self.ensure_one()
        mine = self.organization_id._coop_my_membership()
        if mine and mine.state == 'applied':
            mine.action_withdraw()
        return {'type': 'ir.actions.act_window_close'}

    def action_apply(self):
        self.ensure_one()
        organization = self.organization_id
        me = self.env.user.partner_id
        if not organization.is_company:
            raise UserError(_('Вступают в организацию, а не к человеку.'))
        if organization == me:
            raise UserError(_('Это ваша собственная карточка.'))
        if self.block:
            raise UserError(self.block_note)
        if not self.acknowledged:
            raise UserError(_('Сначала ознакомьтесь с документами '
                              'кооператива и отметьте это.'))
        if self.role_id not in self.allowed_role_ids:
            raise UserError(_('«%(role)s» в «%(org)s» не вступают.',
                              role=self.role_id.name, org=organization.name))

        membership = self.env['coop.membership'].sudo().create({
            'partner_id': me.id,
            'organization_id': organization.id,
            'role_id': self.role_id.id,
            'state': 'applied',
            # Голос — у пайщика; ассоциированный член голосует только
            # в пределах устава, это решает приём, а не заявление.
            'has_vote': self.role_id.code in ('member', 'participant'),
            'coop_acknowledged_on': fields.Datetime.now(),
        })

        body = _('Заявление о вступлении в «%(org)s»: %(who)s, %(by_whom)s. '
                 'С документами кооператива ознакомлен.',
                 org=organization.display_name, who=me.display_name,
                 by_whom=self.role_id.name)
        if self.note:
            body = "%s %s" % (body, self.note)
        self.env['coop.notification']._notify(
            membership._roster_deciders(), body,
            record=organization, kind='org')
        organization.sudo().message_post(body=body)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'type': 'success', 'sticky': False,
                'message': _('Заявление подано, ответ придёт в уведомления.'),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class CoopMembershipAcknowledged(models.Model):
    _inherit = 'coop.membership'

    coop_acknowledged_on = fields.Datetime(
        string='Ознакомлен с документами',
        help='Когда заявитель отметил, что прочитал устав и положения '
             'кооператива (задача 445).')
