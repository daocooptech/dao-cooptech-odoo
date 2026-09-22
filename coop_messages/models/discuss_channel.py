# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.addons.mail.tools.discuss import Store

_logger = logging.getLogger(__name__)


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
        ('shareholders', 'Пайщики'),
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

    coop_managed = fields.Boolean(
        string='Состав ведёт платформа', index=True,
        help='У переписки, заведённой платформой, состав следует за '
             'составом записи: стороны сделки, участники проекта, '
             'пайщики кооператива. '
             'У остальных переписок состав ведёт тот, кто их завёл: '
             'решение владельца 328 — у одной организации чатов может '
             'быть сколько угодно, и платформа в них не вмешивается.')

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

    def message_post(self, **kwargs):
        """Заблокировавшему не пишут.

        Проверка стоит на отправке, а не только на заведении переписки:
        закрыть дорогу можно и после того, как разговор уже начался, и
        тогда старый канал остался бы лазейкой.

        Только личные переписки: в переписке сделки, проекта или
        организации стороны связаны делом, и личная неприязнь одного не
        должна обрывать общий разговор.
        """
        self._coop_check_not_blocked()
        return super().message_post(**kwargs)

    def _coop_check_not_blocked(self):
        Block = self.env['coop.block']
        me = self.env.user.partner_id
        for channel in self:
            if channel.channel_type != 'chat':
                continue
            interlocutors = channel.channel_partner_ids - me
            closers = [p for p in interlocutors if Block._blocks(p, me)]
            if closers:
                raise UserError(_(
                    'Участник %s не принимает от вас сообщений.'
                ) % closers[0].display_name)

    # Модели, чьи переписки ведёт платформа. Списком, а не цепочкой
    # условий: новый раздел добавляется одной строкой.
    coop_owner_partner_ids = fields.Many2many(
        'res.partner', 'coop_channel_owner_rel', 'channel_id', 'partner_id',
        string='Хозяева переписки', compute='_compute_coop_owner',
        store=True, readonly=True,
        help='Кто может переименовать переписку. У сделки — обе стороны, '
             'у проекта — инициатор, у организации — те, кто ведёт состав '
             'или подписывает от её имени.')

    @api.depends('coop_res_model', 'coop_res_id', 'coop_kind')
    def _compute_coop_owner(self):
        """Хозяева переписки — хранимым полем, а не вычислением на лету.

        Правило доступа сравнивает поле с тем, кем человек является, а
        ссылка-справочник (`coop_res_model` плюс номер) в условии правила
        не соединяется с таблицей — по ней отбирать нельзя.
        """
        for channel in self:
            owners = self.env['res.partner']
            record = channel._coop_record()
            # Не у всякой записи с перепиской есть примесь: чат сообщества
            # заводит организатор, и модель сообщества про хозяев ничего
            # не знает. Без этой проверки вычисление падало на первом же
            # таком канале, и с ним не поднималась вся база — ошибка в
            # вычисляемом поле останавливает загрузку целиком.
            if record is not None and hasattr(record, '_coop_channel_owners'):
                owners = record._coop_channel_owners(channel.coop_kind)
            channel.coop_owner_partner_ids = [(6, 0, owners.ids)]

    def _coop_record(self):
        """Запись, из которой выросла переписка."""
        self.ensure_one()
        if not self.coop_res_model or not self.coop_res_id:
            return None
        if self.coop_res_model not in self.env:
            return None
        record = self.env[self.coop_res_model].sudo().browse(self.coop_res_id)
        return record if record.exists() else None

    MANAGED_MODELS = ('coop.deal', 'coop.project', 'res.partner')

    # Виды переписок, которые ведёт платформа. Личная переписка тоже
    # ссылается на человека, и по одной лишь модели записи её от рабочего
    # чата организации не отличить: пометив по модели, я записал в
    # «ведёт платформа» все сорок шесть личных.
    MANAGED_KINDS = ('deal', 'project', 'org', 'shareholders')

    def _action_unfollow(self, partner=None, guest=None, post_leave_message=True):
        """Из переписки платформы не выходят.

        Решение владельца 16 сентября 2026: запретить явно. Состав такой
        переписки следует за записью, и вышедшего вернул бы обратно
        первый же пересчёт — кнопка обещала бы то, что отменяется само.

        Пока человек сторона сделки или член кооператива, разговор его.
        Перестал быть — платформа уберёт его сама, и просить об этом не
        придётся.
        """
        for channel in self:
            if channel.coop_managed:
                raise UserError(_(
                    'Из этой переписки нельзя выйти: её состав следует за '
                    'записью. «%(что)s» — разговор тех, кто в деле; выйти '
                    'из него можно, только перестав в нём участвовать.',
                    what=channel.display_name))
        return super()._action_unfollow(
            partner=partner, guest=guest, post_leave_message=post_leave_message)

    @api.model
    def coop_resync_managed(self):
        """Привести состав переписок платформы к составу записей.

        Зовётся при обновлении модуля, как пересборка бокового меню:
        правило состава живёт в коде, а записи участников — в базе, и
        разойтись они могут от любой правки мимо платформы. Разовый
        прогон дешевле расследования «почему человек не видит свою
        сделку».

        Заодно проставляется признак «состав ведёт платформа»: до 16
        сентября 2026 его не было, и переписки, заведённые платформой, от
        заведённых руками ничем не отличались.
        """
        Channels = self.sudo()
        merged = {'каналов': 0, 'добавлено': 0, 'убрано': 0}
        # Снять пометку с того, что платформа не ведёт: личные переписки
        # пометились по ошибке, когда признак ставился по модели записи.
        foreign = Channels.search([('coop_managed', '=', True),
                               ('coop_kind', 'not in', list(self.MANAGED_KINDS))])
        if foreign:
            foreign.write({'coop_managed': False})
        for model in self.MANAGED_MODELS:
            if model not in self.env:
                continue
            Model = self.env[model].sudo()
            # Сначала помечаем уже заведённые: до 16 сентября 2026
            # признака не было, и переписки платформы от заведённых
            # руками ничем не отличались.
            own_list = Channels.search([('coop_res_model', '=', model),
                                  ('coop_kind', 'in', self.MANAGED_KINDS),
                                  ('coop_managed', '=', False)])
            if own_list:
                own_list.write({'coop_managed': True})
            # Потом заводим недостающие и сводим составы. Порядок важен:
            # заведение ищет переписку по признаку, и без пометки выше
            # оно завело бы вторую рядом с существующей.
            records = Model.search([])
            records._coop_ensure_channel()
            for channel in Channels.search([('coop_res_model', '=', model),
                                        ('coop_kind', 'in', self.MANAGED_KINDS)]):
                record = Model.browse(channel.coop_res_id)
                if not record.exists():
                    continue
                specs = {ch['kind']: ch for ch in record._coop_channel_specs()}
                spec = specs.get(channel.coop_kind)
                if not spec:
                    continue
                added, removed = record._coop_apply_members(
                    channel, spec['partners'])
                merged['каналов'] += 1
                merged['добавлено'] += added
                merged['убрано'] += removed
        _logger.info(
            'Состав переписок сведён с записями: каналов %(каналов)s, '
            'добавлено %(добавлено)s, убрано %(убрано)s', merged)
        return True

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
            'coop_managed',
        ]
