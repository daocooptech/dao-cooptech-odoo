# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Виды кооперативов, у которых по закону бывают кооперативные участки:
# потребительское общество (3085-1, ст. 1, 17) и прочие потребительские.
SECTION_KINDS = ('consumer_society', 'consumer')

SECTION_NOTE = (
    'Часть потребительского общества: объединяет пайщиков для участия в '
    'собраниях (ст. 1 и 17 Закона РФ № 3085-1). Не юридическое лицо и не '
    'филиал: своих органов, имущества и сделок у участка нет.')
SECTION_NOTE_ABROAD = (
    ' В стране пребывания не зарегистрирован и деятельности там не ведёт — '
    'только членство и голосование.')


class CoopOrgSection(models.Model):
    """Кооперативный участок потребительского общества.

    Решение 428 (владелец 28.09.2026): «участок для членства и
    голосования». По 3085-1 участок — часть общества, в которой объединено
    определённое число пайщиков, как правило по территориальному признаку
    (ст. 1); собрание пайщиков участка обсуждает дела общества и избирает
    уполномоченных на общее собрание (ст. 17). Своих органов, имущества и
    права сделок у участка нет — поэтому здесь только состав, уполномоченные
    и собрания. Участок может объединять пайщиков, живущих за рубежом
    (заключение юриста 28.09, «Кооперативный участок за рубежом (Шанхай)»):
    пока он голосует и участвует в делах общества дистанционно, это законно.
    """
    _name = 'coop.org.section'
    _description = 'Кооперативный участок'
    _order = 'organization_id, sequence, name'

    name = fields.Char(string='Участок', required=True)
    sequence = fields.Integer(default=10)
    organization_id = fields.Many2one(
        'res.partner', string='Потребительское общество', required=True,
        index=True, ondelete='cascade', domain=[('is_company', '=', True)])
    city = fields.Char(string='Где живут пайщики участка')
    country_id = fields.Many2one('res.country', string='Страна')
    abroad = fields.Boolean(string='За рубежом', compute='_compute_abroad', store=True)
    note = fields.Text(string='Что это такое', compute='_compute_note')
    membership_ids = fields.One2many('coop.membership', 'section_id', string='Пайщики участка')
    member_count = fields.Integer(string='Пайщиков', compute='_compute_member_count')
    delegate_ids = fields.Many2many(
        'res.partner', 'coop_org_section_delegate_rel', 'section_id', 'partner_id',
        string='Уполномоченные',
        help='Избраны собранием участка на общее собрание уполномоченных '
             'потребительского общества (ст. 17 Закона № 3085-1).')
    meeting_ids = fields.One2many('coop.org.section.meeting', 'section_id', string='Собрания участка')
    image_512 = fields.Image(related='organization_id.image_512')

    @api.depends('country_id')
    def _compute_abroad(self):
        for section in self:
            section.abroad = bool(section.country_id) and section.country_id.code != 'RU'

    @api.depends('abroad')
    def _compute_note(self):
        for section in self:
            section.note = SECTION_NOTE + (SECTION_NOTE_ABROAD if section.abroad else '')

    @api.depends('membership_ids.state')
    def _compute_member_count(self):
        for section in self:
            section.member_count = len(section.membership_ids.filtered(
                lambda m: m.state == 'active'))

    @api.constrains('organization_id')
    def _check_organization(self):
        for section in self:
            if section.organization_id.coop_cooperative_kind not in SECTION_KINDS:
                raise UserError(_(
                    'Кооперативные участки бывают у потребительских обществ и '
                    'потребительских кооперативов (ст. 1 Закона № 3085-1), а '
                    '«%s» — не такой.', section.organization_id.display_name))


class CoopOrgSectionMeeting(models.Model):
    """Собрание пайщиков кооперативного участка (ст. 17 Закона № 3085-1)."""
    _name = 'coop.org.section.meeting'
    _description = 'Собрание кооперативного участка'
    _order = 'date desc, id desc'

    section_id = fields.Many2one('coop.org.section', string='Участок', required=True,
                                 index=True, ondelete='cascade')
    date = fields.Date(string='Дата', required=True, default=fields.Date.context_today)
    mode = fields.Selection([
        ('online', 'Онлайн'),
        ('absentee', 'Заочно'),
        ('inperson', 'Очно'),
    ], string='Форма', required=True, default='online')
    agenda = fields.Char(string='Повестка', required=True)
    decision = fields.Char(string='Решение')
    state = fields.Selection([
        ('planned', 'Назначено'),
        ('held', 'Проведено'),
    ], string='Состояние', required=True, default='planned')
    votes_for = fields.Integer(string='За')
    votes_against = fields.Integer(string='Против')
    votes_abstain = fields.Integer(string='Воздержались')


class CoopMembership(models.Model):
    _inherit = 'coop.membership'

    section_id = fields.Many2one(
        'coop.org.section', string='Кооперативный участок', index=True,
        ondelete='set null', domain="[('organization_id', '=', organization_id)]",
        help='Участок общества, в собраниях которого пайщик участвует.')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_section_ids = fields.One2many(
        'coop.org.section', 'organization_id', string='Кооперативные участки')
