# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Ступени по возрастанию. Порядок здесь — единственное место, где он
# задан: сравнивать ступени строками нельзя, а раскладывать их по числам
# в каждом модуле значит получить два расходящихся представления о том,
# что выше чего.
LEVELS = ('none', 'account', 'contact', 'identity')
LEVEL_LABELS = {
    'none': 'Не подтверждён',
    'account': 'Учётная запись',
    'contact': 'Контакт подтверждён',
    'identity': 'Личность подтверждена',
}

# Какая проверка какую ступень даёт. Организация подтверждается иначе,
# чем человек: у неё нет паспорта, зато есть ЕГРЮЛ и устав.
KIND_LEVEL = {
    'email': 'account',
    'phone': 'contact',
    'identity': 'identity',   # человек: очно, ЕСИА, Госключ
    'registry': 'identity',   # организация: ИНН и ОГРН сверены с ЕГРЮЛ
}


class CoopVerification(models.Model):
    """Факт проверки участника, а не сама проверка.

    Хранится то, что проверку подтверждает: кто проверил, когда, каким
    способом и до какого числа это действует. Сканов документов и
    паспортных данных здесь нет и не должно быть.

    Причина не в осторожности вообще, а в устройстве сети. Узлов много, и
    каждый принадлежит своему кооперативу; скан паспорта в базе узла
    делает каждый кооператив оператором персональных данных с полным
    набором обязанностей, а протокол федеративного обмена прямо запрещает
    персональные данные в рассылаемых событиях. Факт проверки передать
    можно, документ — нет.

    Своего распознавания по селфи здесь нет и не будет: частные операторы
    не вправе вести собственные биометрические системы вне государственной
    ЕБС (ФЗ от 29.12.2022 № 572-ФЗ). Законные пути — очное подтверждение в
    кооперативе, Госуслуги и Госключ.
    """
    _name = 'coop.verification'
    _description = 'Подтверждение участника'
    _inherit = ['mail.thread']
    _order = 'confirmed_on desc, id desc'

    partner_id = fields.Many2one(
        'res.partner', string='Участник', required=True, index=True,
        ondelete='cascade', tracking=True)
    kind = fields.Selection([
        ('email', 'Электронная почта'),
        ('phone', 'Телефон'),
        ('identity', 'Личность'),
        ('registry', 'Сведения в реестре'),
    ], string='Что подтверждается', required=True, index=True, tracking=True)

    method = fields.Selection([
        ('self', 'Самостоятельно, по коду'),
        ('inperson', 'Очно в кооперативе'),
        ('esia', 'Госуслуги (ЕСИА)'),
        ('goskey', 'Госключ'),
        ('registry', 'Сверка с ЕГРЮЛ'),
    ], string='Способ', required=True, tracking=True,
        help='Способы подтверждения личности выбраны владельцем: очно, '
             'Госуслуги, Госключ. Своего распознавания по фотографии нет '
             'и быть не может — частные биометрические системы вне '
             'государственной ЕБС вести запрещено.')

    state = fields.Selection([
        ('pending', 'Ожидает проверки'),
        ('confirmed', 'Подтверждено'),
        ('rejected', 'Отклонено'),
        ('expired', 'Истекло'),
    ], string='Состояние', required=True, default='pending', index=True,
        tracking=True)

    confirmed_by_id = fields.Many2one(
        'res.users', string='Кто подтвердил', readonly=True, tracking=True,
        help='При очном подтверждении — участник кооператива, который '
             'сверил документ. При машинном — пусто.')
    confirmed_on = fields.Datetime(string='Когда подтверждено', readonly=True)
    expires_on = fields.Date(
        string='Действует до',
        help='Пусто — бессрочно. Сверка с реестром устаревает: сведения '
             'в ЕГРЮЛ меняются, и годичной давности выписка ничего не '
             'подтверждает.')

    # Ссылка у того, кто проверял, — номер обращения в ЕСИА, ссылка на
    # выписку. Не документ, а способ найти его у источника.
    evidence_ref = fields.Char(
        string='Ссылка на подтверждение',
        help='Идентификатор у стороны, которая проверяла: номер обращения, '
             'ссылка на выписку. Сам документ здесь не хранится.')
    note = fields.Char(string='Пояснение')

    _one_per_kind = models.Constraint(
        'unique(partner_id, kind)',
        'Такое подтверждение у участника уже есть — правьте его, а не заводите второе.',
    )

    def action_confirm(self):
        for record in self:
            record.write({
                'state': 'confirmed',
                'confirmed_by_id': self.env.user.id,
                'confirmed_on': fields.Datetime.now(),
            })
        return True

    def action_reject(self):
        self.write({'state': 'rejected'})
        return True

    @api.model
    def _cron_expire(self):
        """Истёкшие подтверждения перестают действовать сами.

        Без этого сверка трёхлетней давности продолжает считаться
        действующей, а сведения в реестре к тому времени другие.
        """
        stale = self.search([
            ('state', '=', 'confirmed'),
            ('expires_on', '!=', False),
            ('expires_on', '<', fields.Date.context_today(self)),
        ])
        if stale:
            stale.write({'state': 'expired'})
        return True

    # Пересчёт ступени у партнёра — при любом изменении фактов.
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.partner_id._compute_coop_verification_level()
        return records

    def write(self, vals):
        partners = self.partner_id
        result = super().write(vals)
        (partners | self.partner_id)._compute_coop_verification_level()
        return result

    def unlink(self):
        partners = self.partner_id
        result = super().unlink()
        partners._compute_coop_verification_level()
        return result


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_verification_ids = fields.One2many(
        'coop.verification', 'partner_id', string='Подтверждения')
    coop_verification_level = fields.Selection(
        [(code, LEVEL_LABELS[code]) for code in LEVELS],
        string='Ступень верификации', default='none', required=True,
        compute='_compute_coop_verification_level', store=True, index=True,
        help='Что участник вправе делать. Не подтверждён — только смотрит. '
             'Подтверждён контакт — пишет, публикует навыки и ресурсы, '
             'откликается. Подтверждена личность — вакансии, организации, '
             'проекты, сделки, деньги, паи.')

    @api.depends('coop_verification_ids.state', 'coop_verification_ids.kind')
    def _compute_coop_verification_level(self):
        """Ступень — следствие фактов, а не отдельно выставляемое значение.

        Ступени идут подряд: подтверждённая личность без подтверждённого
        телефона всё равно даёт «личность». Обратное неверно — пропустить
        ступень вверх нельзя.
        """
        for partner in self:
            reached = {
                KIND_LEVEL.get(verification.kind)
                for verification in partner.coop_verification_ids
                if verification.state == 'confirmed'
            }
            # Высшая достигнутая, а не первая пропущенная: подтверждённая
            # личность без подтверждённой почты — обычное дело при очном
            # приёме в кооперативе, и понижать его до «не подтверждён» из-за
            # незаполненной почты было бы нелепо.
            level = 'none'
            for candidate in reversed(LEVELS):
                if candidate in reached:
                    level = candidate
                    break
            partner.coop_verification_level = level

    def coop_level_at_least(self, level):
        """Дотягивает ли участник до нужной ступени."""
        self.ensure_one()
        return LEVELS.index(self.coop_verification_level) >= LEVELS.index(level)

    def coop_require_level(self, level, action):
        """Проверка перед действием, с объяснением вместо отказа.

        Отказ должен говорить, чего не хватает и что с этим делать. «Нет
        доступа» без объяснения человек читает как поломку и идёт писать в
        поддержку.
        """
        self.ensure_one()
        if self.coop_level_at_least(level):
            return True
        raise UserError(_(
            'Чтобы %(action)s, нужна ступень «%(need)s». Сейчас у вас — '
            '«%(have)s».\n\n'
            'Личность подтверждают очно в кооперативе, через Госуслуги или '
            'Госключ. Телефон — кодом из сообщения.'
        ) % {
            'action': action,
            'need': LEVEL_LABELS[level],
            'have': LEVEL_LABELS[self.coop_verification_level],
        })
