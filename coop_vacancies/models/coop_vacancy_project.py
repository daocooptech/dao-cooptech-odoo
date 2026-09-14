# -*- coding: utf-8 -*-
"""Трудовая потребность проекта — это вакансия, а не объявление спроса.

Владелец 14 сентября 2026: «вакансии из проектов размещаются в вакансиях
а не в ресурсах». Каталог ресурсов — про вещи: технику, материалы,
помещения. Работа живёт в своём каталоге, где есть специализация,
навыки, опыт и отклики, — и искать её там же, где ищут доски, человеку
незачем.

Связь у вакансии с проектом уже была, но с управляемым — а он
появляется только при запуске. Работу же ищут раньше всего: люди и есть
главный вклад в кооперативную затею. Поэтому добавлена связь со сбором
вкладов, а управляемый проект подставляется сам, когда появляется.

Отклик на вакансию проекта — то же, что предложение на потребность:
утверждённый становится вкладом, труд идёт в долю, остальные отклики
отклоняются (решение владельца от 2026-09-14).
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CoopVacancy(models.Model):
    _inherit = 'coop.vacancy'

    coop_project_id = fields.Many2one(
        'coop.project', string='Сбор вкладов', index=True,
        ondelete='cascade',
        help='Проект, которому нужна эта работа. Заполнено у вакансий, '
             'размещённых проектом; у вакансий организаций пусто.')
    need_manager_id = fields.Many2one(
        'res.partner', string='Ответственный за потребность',
        help='Кто смотрит отклики и утверждает один. Не указан — значит '
             'инициатор проекта.')
    need_accepted_id = fields.Many2one(
        'coop.project.contribution', string='Утверждённый отклик',
        readonly=True, copy=False)

    @api.onchange('coop_project_id')
    def _onchange_coop_project(self):
        """Управляемый проект и город берутся у сбора.

        Вводить их заново — верный способ получить вакансию в одном
        городе, а проект в другом.
        """
        for record in self:
            if not record.coop_project_id:
                continue
            record.project_id = record.coop_project_id.project_id
            record.city = record.coop_project_id.city or record.city

    def _need_deciders(self):
        """Кто вправе утвердить отклик на эту вакансию."""
        self.ensure_one()
        partners = self.coop_project_id.partner_id
        if self.need_manager_id:
            partners |= self.need_manager_id
        return partners

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Управляемый проект подставляется и при создании: onchange
        # срабатывает только в форме, а вакансии заводятся ещё и
        # загрузчиком, и переносом.
        for record in records.filtered(
                lambda v: v.coop_project_id and not v.project_id):
            record.project_id = record.coop_project_id.project_id
        return records


class CoopVacancyApplication(models.Model):
    """Отклик на вакансию проекта, утверждённый — это вклад.

    Решение владельца от 2026-09-14: отклик на вакансию проекта — то же
    самое, что предложение на потребность. Утвердили — человек стал
    участником проекта, его труд учтён вкладом и пошёл в долю, остальные
    отклики отклонены.

    У вакансии организации ничего этого не происходит: там наём, а не
    складчина, и доли не возникает.
    """
    _inherit = 'coop.vacancy.application'

    contribution_id = fields.Many2one(
        'coop.project.contribution', string='Вклад по отклику',
        readonly=True, copy=False,
        help='Заводится, когда отклик на вакансию проекта утверждён.')

    def action_invite(self):
        result = super().action_invite()
        for record in self:
            record._accept_into_project()
        return result

    def _accept_into_project(self):
        """Превратить утверждённый отклик во вклад и закрыть вакансию."""
        self.ensure_one()
        project = self.vacancy_id.coop_project_id
        if not project or self.contribution_id:
            return
        deciders = self.vacancy_id._need_deciders()
        allowed = (self.env.user.partner_id in deciders
                   or any(self.env.user.coop_has_power('deal', partner)
                          for partner in deciders))
        if not allowed:
            raise UserError(_(
                'Утверждать отклики по проекту «%s» может его инициатор, '
                'ответственный за потребность или тот, кому организация '
                'поручила сделки.') % project.name)

        # Оценка труда — то, что вакансия обещает за работу. Ноль тоже
        # бывает: волонтёрская вакансия доли не даёт, и это правда, а не
        # недосмотр.
        value = self.vacancy_id.contribution_value or 0
        contribution = self.env['coop.project.contribution'].sudo().create({
            'project_id': project.id,
            'partner_id': self.partner_id.id,
            'kind': 'labour',
            'name': self.vacancy_id.name,
            'value': value,
            'state': 'accepted',
            'accepted_on': fields.Date.context_today(self),
        })
        self.contribution_id = contribution.id

        # Дальше — последствия уже принятого решения: право утверждать
        # проверено выше по существу, а прав на саму вакансию и чужие
        # отклики у ответственного за потребность нет и быть не должно.
        others = self.vacancy_id.application_ids.filtered(
            lambda app: app.id != self.id and app.state == 'applied')
        if others:
            others.sudo().write({'state': 'declined'})
        self.vacancy_id.sudo().write({
            'state': 'closed',
            'need_accepted_id': contribution.id,
        })
        self.vacancy_id.sudo().message_post(body=_(
            'Вакансия закрыта: утверждён отклик от %(who)s, труд учтён '
            'вкладом на %(value)s ₽. Прочих откликов отклонено: %(count)s.',
            who=self.partner_id.display_name, value=value, count=len(others)))
