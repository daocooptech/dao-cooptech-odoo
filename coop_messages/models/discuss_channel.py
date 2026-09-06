# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.addons.mail.tools.discuss import Store


class DiscussChannel(models.Model):
    """Переписка платформы.

    Канал Discuss — это уже готовая переписка: доставка, вложения,
    прочтения, уведомления. Не хватает ему одного — понимания, о чём
    разговор. Личная беседа, торг по сделке, обсуждение проекта и рассылка
    сервиса в списке выглядят одинаково, и найти нужную можно только по
    названию, которое человек должен помнить.

    Поэтому здесь три вещи: вид переписки, подпись под названием и запись,
    из которой переписка выросла. По виду в макете собраны фильтры-чипы, по
    подписи узнают собеседника без открытия, по записи в шапке появляется
    ссылка «Открыть организацию» — обратный путь из разговора к делу.
    """

    _inherit = 'discuss.channel'

    KINDS = [
        ('person', 'Личная'),
        ('deal', 'Сделка'),
        ('org', 'Организация'),
        ('project', 'Проект'),
        ('community', 'Сообщество'),
        ('service', 'Сервис'),
    ]

    # Соответствие «модель записи → вид переписки». Списком, а не цепочкой
    # условий: новый раздел платформы добавляется одной строкой, и по ней
    # же видно, что вид переписки берётся из записи, а не назначается
    # руками.
    KIND_BY_MODEL = {
        'coop.deal': 'deal',
        'coop.project': 'project',
        'coop.community': 'community',
    }

    coop_kind = fields.Selection(
        KINDS, string='Вид переписки', index=True,
        compute='_compute_coop_kind', store=True, readonly=False,
        help='По виду собраны фильтры в списке переписок.')

    coop_res_model = fields.Char(
        string='Модель записи',
        help='О чём разговор: сделка, проект, организация, сообщество.')
    coop_res_id = fields.Many2oneReference(
        string='Запись', model_field='coop_res_model', index=True)
    coop_link_label = fields.Char(
        string='Подпись ссылки',
        compute='_compute_coop_link_label', store=True, readonly=False,
        help='Что написано на кнопке перехода к записи.')

    coop_subtitle = fields.Char(
        string='Подпись',
        help='Строка под названием переписки: город и число пайщиков, '
             'сумма сделки, роль собеседника.')

    coop_pinned = fields.Boolean(
        string='Закреплена',
        help='Закреплённые переписки идут первыми в списке.')

    @api.depends('channel_type', 'coop_res_model')
    def _compute_coop_kind(self):
        """Вид берётся из записи, а личной считается беседа один на один.

        Пересчитывается только у тех, у кого вида ещё нет: вид можно
        поправить руками (например, отметить служебную рассылку сервисной),
        и затирать эту правку при каждой записи в канал нельзя.
        """
        for channel in self:
            if channel.coop_kind:
                continue
            if channel.coop_res_model:
                channel.coop_kind = self.KIND_BY_MODEL.get(
                    channel.coop_res_model, 'org')
            elif channel.channel_type == 'chat':
                channel.coop_kind = 'person'
            else:
                channel.coop_kind = False

    LINK_LABELS = {
        'deal': 'Открыть сделку',
        'org': 'Открыть организацию',
        'project': 'Открыть проект',
        'community': 'Открыть сообщество',
        'person': 'Открыть профиль',
    }

    @api.depends('coop_kind', 'coop_res_model', 'coop_res_id')
    def _compute_coop_link_label(self):
        for channel in self:
            if not channel.coop_res_model or not channel.coop_res_id:
                channel.coop_link_label = False
            elif not channel.coop_link_label:
                channel.coop_link_label = self.LINK_LABELS.get(
                    channel.coop_kind, 'Открыть запись')

    @api.model_create_multi
    def create(self, vals_list):
        """Личная переписка, заведённая на лету, — сразу с подписью и
        ссылкой на профиль, а не только с видом.

        `_compute_coop_kind` расставляет вид «личная» и без этого — он
        смотрит только на тип канала. Запись же, город и специализация
        собеседника требуют дойти до партнёра, а к этому моменту участники
        канала ещё не сохранены (они появляются в той же транзакции), так
        что делать это приходится после создания, а не в compute.
        """
        channels = super().create(vals_list)
        chats = channels.filtered(
            lambda c: c.channel_type == 'chat' and not c.coop_res_model)
        for channel in chats:
            correspondent = channel.channel_partner_ids - self.env.user.partner_id
            if len(correspondent) != 1 or correspondent.is_company:
                continue
            parts = [p for p in (correspondent.city,
                                  correspondent.coop_specialization_id.name)
                     if p]
            channel.write({
                'coop_res_model': 'res.partner',
                'coop_res_id': correspondent.id,
                'coop_subtitle': ' · '.join(parts) or False,
            })
        return channels

    def _to_store_defaults(self, target: Store.Target):
        """Наши поля уезжают на клиент вместе с каналом.

        Отдельным запросом их было бы не собрать: список переписок рисуется
        из того, что движок уже прислал, и дозагрузка вида и подписи дала
        бы кадр со списком без фильтров.
        """
        return super()._to_store_defaults(target) + [
            'coop_kind',
            'coop_subtitle',
            'coop_res_model',
            'coop_res_id',
            'coop_link_label',
            'coop_pinned',
        ]
