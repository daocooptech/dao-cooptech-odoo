# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Формы, которые человек сам не заводит: рабочая группа оператора узла.
CLOSED_FORMS = ('platform',)


def inn_is_valid(inn):
    """Контрольные цифры ИНН: 10 знаков у организации, 12 у ИП."""
    if not inn.isdigit() or len(inn) not in (10, 12):
        return False
    digits = [int(c) for c in inn]

    def control(weights):
        return sum(w * d for w, d in zip(weights, digits)) % 11 % 10

    if len(inn) == 10:
        return control((2, 4, 10, 3, 5, 9, 4, 6, 8)) == digits[9]
    return (control((7, 2, 4, 10, 3, 5, 9, 4, 6, 8)) == digits[10]
            and control((3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)) == digits[11])


class CoopOrgAdd(models.TransientModel):
    """Страница «Добавить организацию» (`OrgAddPage`, решение 625).

    Отдельная временная запись, а не черновик контакта: у организации нет
    состояния «черновик», и недописанная встала бы в каталог, в выбор
    сторон сделки и в поиск. Организация появляется одним действием —
    «Создать организацию», — сразу с реквизитами и с уполномоченным.
    """
    _name = 'coop.org.add'
    _description = 'Страница добавления организации'
    # Заполняют не за минуту: за час запись убрал бы сборщик.
    _transient_max_hours = 24

    name = fields.Char(string='Название')
    group_code = fields.Selection([
        ('cooperative', 'Кооперативная'),
        ('commercial', 'Коммерческая'),
        ('nonprofit', 'Некоммерческая'),
        ('decentralized', 'Децентрализованная'),
    ], string='Какая организация', default='cooperative')
    form_id = fields.Many2one('coop.legal.form', string='Правовая форма')
    card_label = fields.Char(
        string='Вид на карточке', related='form_id.group_id.card_label')
    inn = fields.Char(
        string='ИНН', help='10 цифр у организации, 12 у предпринимателя.')
    inn_lookup = fields.Boolean(
        string='Можно заполнить по ИНН', compute='_compute_inn_lookup')
    kpp = fields.Char(string='КПП', size=9)
    ogrn = fields.Char(string='ОГРН', size=15)
    registered_on = fields.Date(string='Зарегистрирована')
    okved_id = fields.Many2one(
        'coop.okved', string='Вид деятельности (ОКВЭД)',
        domain=[('parent_id', '!=', False)])
    # Решение 704: устав — файлом, он ляжет в «Документы» организации.
    charter_file = fields.Binary(string='Устав', attachment=False)
    charter_file_name = fields.Char(string='Имя файла устава')
    image_1920 = fields.Image(string='Знак', max_width=1920, max_height=1920)
    city = fields.Char(string='Город')
    street = fields.Char(string='Адрес')
    phone = fields.Char(string='Телефон')
    email = fields.Char(string='Почта')
    website = fields.Char(string='Сайт')
    specialization_id = fields.Many2one(
        'coop.specialization', string='Специализация')
    category_id = fields.Many2one(
        string='Сфера', related='specialization_id.category_id')
    about = fields.Text(string='Описание')

    @api.depends('name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.name or _('Новая организация')

    def _compute_inn_lookup(self):
        """Кнопка есть там, где подключён справочник и задан его ключ."""
        ready = hasattr(self.env['res.partner'], 'get_legal_entity_data') and bool(
            self.env['ir.config_parameter'].sudo().get_str(
                'dadata_connector.dadata_token'))
        for record in self:
            record.inn_lookup = ready

    @api.onchange('group_code')
    def _onchange_group_code(self):
        if self.form_id.group_id.code != self.group_code:
            self.form_id = False

    @api.model
    def action_new_org(self):
        """«Добавить организацию»: страница ввода."""
        record = self.create({
            'city': self.env.user.partner_id.city or False})
        action = self.env['ir.actions.act_window']._for_xml_id(
            'coop_orgs.action_coop_org_add')
        action['res_id'] = record.id
        return action

    # ── ИНН ──────────────────────────────────────────────────────────────

    def _coop_check_inn(self):
        """ИНН верный и ещё не занят."""
        self.ensure_one()
        inn = (self.inn or '').strip()
        if not inn:
            return ''
        if not inn_is_valid(inn):
            raise UserError(_(
                'ИНН «%s» записан с ошибкой: проверьте цифры.') % inn)
        # Под sudo: занятость ИНН не зависит от того, что видит человек.
        twin = self.env['res.partner'].sudo().with_context(
            active_test=False).search([
                ('coop_inn', '=', inn), ('is_company', '=', True),
                ('coop_is_participant', '=', True)], limit=1)
        if twin:
            raise UserError(_(
                'Организация с ИНН %(inn)s уже есть: «%(name)s». Откройте её '
                'в каталоге и подайте заявление на вступление.',
                inn=inn, name=twin.name))
        return inn

    def action_fill_by_inn(self):
        """«Заполнить по ИНН»: реквизиты из ЕГРЮЛ.

        Найденное подставляется в поля — человек видит его и правит до
        создания организации.
        """
        self.ensure_one()
        inn = self._coop_check_inn()
        if not inn:
            raise UserError(_('Сначала впишите ИНН.'))
        if not self.inn_lookup:
            raise UserError(_('Справочник ЕГРЮЛ на узле не подключён.'))
        try:
            found = self.env['res.partner'].sudo().get_legal_entity_data(
                inn, widget=False)
        except (UserError, ValidationError):
            raise
        except Exception as error:
            _logger.warning('Заполнение по ИНН не удалось: %s', error)
            raise UserError(_(
                'Справочник ЕГРЮЛ сейчас не отвечает. Впишите реквизиты '
                'вручную или попробуйте позже.')) from error
        self._coop_apply_found(found)
        return False

    def _coop_apply_found(self, found):
        values = {
            key: found[source] for key, source in (
                ('name', 'name'), ('kpp', 'kpp'), ('ogrn', 'ogrn'),
                ('city', 'city'), ('street', 'street'))
            if found.get(source)}
        code = (found.get('arceat') or '')[:2]
        if code:
            okved = self.env['coop.okved'].search([
                ('code', '=', code), ('parent_id', '!=', False)], limit=1)
            if okved:
                values['okved_id'] = okved.id
        # Форма — по первому слову краткого названия: «ПК "Родник"».
        head = (found.get('name') or '').replace('"', ' ').replace('«', ' ').split()
        if head:
            form = self.env['coop.legal.form'].search([
                ('short_name', '=ilike', head[0]),
                ('code', 'not in', CLOSED_FORMS)], limit=1)
            if form:
                values.update(form_id=form.id, group_code=form.group_id.code)
        self.write(values)

    # ── Создание ─────────────────────────────────────────────────────────

    def action_create_org(self):
        """«Создать организацию»: контакт, участие и уполномоченный."""
        self.ensure_one()
        me = self.env.user.partner_id
        me.coop_require_level('contact', _('создать организацию'))
        if not (self.name or '').strip():
            raise UserError(_('Напишите название организации.'))
        if not self.form_id or self.form_id.code in CLOSED_FORMS:
            raise UserError(_('Выберите правовую форму.'))
        if self.form_id.group_id.code != self.group_code:
            raise UserError(_('Правовая форма — не из выбранной группы.'))
        inn = self._coop_check_inn()
        Partner = self.env['res.partner']
        values = {
            'name': self.name.strip(),
            'is_company': True,
            'coop_is_participant': True,
            'coop_legal_form_id': self.form_id.id,
            'coop_inn': inn or False,
            'coop_kpp': self.kpp,
            'coop_ogrn': self.ogrn,
            'coop_registered_on': self.registered_on,
            'coop_okved_id': self.okved_id.id,
            'image_1920': self.image_1920,
            'city': self.city,
            'street': self.street,
            'phone': self.phone,
            'email': self.email,
            'website': self.website,
            'coop_specialization_id': self.specialization_id.id,
        }
        if 'coop_about' in Partner._fields:
            values['coop_about'] = self.about
        # Под sudo: заводить контакты участнику не положено, а организацию
        # он заводит этой страницей — с проверками выше.
        org = Partner.sudo().create(values)
        if self.charter_file:
            org._coop_put_public_doc(
                'charter', _('Устав'), self.charter_file,
                self.charter_file_name or 'charter.pdf')
        self.env['coop.membership'].sudo().create({
            'partner_id': me.id,
            'organization_id': org.id,
            'role': 'founder',
            'state': 'active',
            'joined_on': fields.Date.context_today(self),
            'admission_basis': _('Создал организацию на платформе'),
            'job_title': _('Уполномоченный'),
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'res_id': org.id,
            'view_mode': 'form',
            'views': [(self.env.ref('coop_orgs.view_coop_orgs_form').id, 'form')],
            'target': 'main',
        }
