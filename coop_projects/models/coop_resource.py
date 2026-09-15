# -*- coding: utf-8 -*-
"""Потребность проекта — это объявление спроса в каталоге ресурсов.

Своей сущности «потребность» на платформе нет и заводить её не нужно.
Владелец 14 сентября 2026: «потребности проектов попадают в базу
ресурсов в раздел спрос». Каталог ресурсов уже различает предложение и
спрос, у объявления есть рубрика, город, цена и срок — всё, чем
описывается «нужен сварщик на три недели» или «нужно двадцать кубов
доски».

Не хватало одного: связи с проектом. Без неё потребности проектов и
частные объявления «ищу» лежали в одной куче, а откликнувшийся не видел,
во что он входит.

Порядок работы — фрилансовый, как и сказал владелец: на потребность
приходят предложения, ответственный смотрит все и утверждает одно.
Утверждённое становится вкладом в проект, остальные отклоняются в тот же
момент: потребность закрыта, и держать людей в ожидании незачем.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CoopResource(models.Model):
    _inherit = 'coop.resource'

    project_id = fields.Many2one(
        'coop.project', string='Потребность проекта', index=True,
        ondelete='cascade',
        help='Заполнено у объявлений, которые проект разместил как свою '
             'потребность. У частных объявлений пусто.')
    is_project_need = fields.Boolean(
        string='Потребность проекта', compute='_compute_is_project_need',
        store=True)

    # Утверждать может инициатор проекта, а на проекте в три десятка
    # потребностей он становится узким местом. Поэтому у потребности
    # может быть свой ответственный — решение владельца от 2026-09-14.
    need_manager_id = fields.Many2one(
        'res.partner', string='Ответственный за потребность',
        help='Кто смотрит предложения и утверждает одно. Не указан — '
             'значит инициатор проекта.')
    need_offer_ids = fields.One2many(
        'coop.project.contribution', 'need_id', string='Предложения')
    need_offer_count = fields.Integer(
        string='Предложений', compute='_compute_need_offers')
    need_accepted_id = fields.Many2one(
        'coop.project.contribution', string='Утверждённое предложение',
        readonly=True, copy=False)

    # Пай — доля, которая полагается за закрытие этой потребности.
    #
    # Вкладчику важнее стоимости: 150 000 ₽ значат разное в проекте на
    # полтора миллиона и в проекте на пятнадцать. Считается от того же
    # знаменателя, что и готовность проекта, — `required_total`, иначе
    # сумма паёв по всем потребностям не сошлась бы со ста процентами.
    need_share_percent = fields.Float(
        string='Пай, %', compute='_compute_need_share', digits=(5, 2),
        help='Стоимость потребности к общей потребности проекта.')
    # То же число под другой подписью. Владелец 15 сентября 2026: «пай
    # только в кооперативных проектах, доля в коммерческих, а в
    # некоммерческих вообще нет долей и паёв».
    #
    # Подпись колонки в списке движка задаётся разметкой и от записи не
    # зависит, а одно и то же поле дважды в списке движок не берёт.
    # Поэтому полей два, значение у них общее, и в разметке показывается
    # то, чьё слово подходит виду проекта. Слово тут не украшение: пай —
    # имущественное участие в кооперативе с правом возврата по уставу,
    # доля в коммерческом — часть в капитале, и путать их нельзя.
    need_share_ratio = fields.Float(
        string='Доля, %', compute='_compute_need_share', digits=(5, 2),
        help='Стоимость потребности к общей потребности проекта.')
    need_can_join = fields.Boolean(
        string='Можно участвовать', compute='_compute_need_can_join')

    @api.depends('price', 'project_id.required_total')
    def _compute_need_share(self):
        for record in self:
            всего = record.project_id.required_total
            доля = (record.price * 100.0 / всего
                    if всего and record.price else 0.0)
            record.need_share_percent = доля
            record.need_share_ratio = доля

    @api.depends_context('uid')
    @api.depends('state', 'project_id.state', 'need_accepted_id',
                 'project_id.partner_id')
    def _compute_need_can_join(self):
        """Те же условия, что и у окна вклада, одним признаком.

        Разойдись они — и человек увидел бы кнопку, отвечающую ошибкой.
        """
        мои = self.env.user.coop_actor_partner_ids
        for record in self:
            record.need_can_join = bool(
                record.project_id
                and record.project_id.state == 'gathering'
                and record.state == 'published'
                and not record.need_accepted_id
                and record.project_id.partner_id not in мои)

    # Чем закрывается потребность того или иного вида. Окно вклада
    # спрашивает то же самое; подставляем ответ заранее, чтобы человек,
    # пришедший из строки «Двигатель асинхронный», не выбирал вид вклада
    # руками.
    ВИД_ВКЛАДА = {
        'material': 'material',
        'equipment': 'resource',
        'labour': 'labour',
        'financial': 'money',
    }

    def action_join_need(self):
        """«Участвовать» из строки потребности."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Участие: %s') % self.name,
            'res_model': 'coop.project.contribute',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_project_id': self.project_id.id,
                'default_need_id': self.id,
                'default_name': self.name,
                'default_value': self.price,
                'default_kind': self.ВИД_ВКЛАДА.get(
                    self.resource_type, 'resource'),
            },
        }

    @api.depends('project_id')
    def _compute_is_project_need(self):
        for record in self:
            record.is_project_need = bool(record.project_id)

    @api.depends('need_offer_ids.state')
    def _compute_need_offers(self):
        for record in self:
            record.need_offer_count = len(record.need_offer_ids.filtered(
                lambda offer: offer.state == 'offered'))

    def _need_deciders(self):
        """Кто вправе утвердить предложение на эту потребность."""
        self.ensure_one()
        partners = self.project_id.partner_id
        if self.need_manager_id:
            partners |= self.need_manager_id
        return partners

    @api.constrains('project_id', 'listing_type')
    def _check_project_need(self):
        for record in self:
            if record.project_id and record.listing_type != 'request':
                raise ValidationError(_(
                    'Потребность проекта — это спрос. Объявление '
                    '«%(name)s» стоит предложением, а привязано к проекту '
                    '«%(project)s».',
                    name=record.name, project=record.project_id.name))

    def action_view_offers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Предложения на потребность'),
            'res_model': 'coop.project.contribution',
            'view_mode': 'list,form',
            'domain': [('need_id', '=', self.id)],
            'context': {
                'default_need_id': self.id,
                'default_project_id': self.project_id.id,
            },
        }
