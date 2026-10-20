from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RsbuPostingMixin(models.AbstractModel):
    """Абстрактный миксин связи документа-источника с журналом РСБУ.

    Инкапсулирует механику: идемпотентную генерацию РСБУ-операции,
    зеркалирование отмены, транзакционную блокировку и навигацию.
    Расчёт строк Дт/Кт делегируется методу _rsbu_build_lines (Этап 4);
    на Этапе 3 это заглушка, возвращающая пустой список.
    """
    _name = 'rsbu.posting.mixin'
    _description = 'РСБУ — Миксин проведения'

    rsbu_move_id = fields.Many2one(
        'rsbu.move', string='РСБУ-проводка', copy=False, readonly=True)
    rsbu_move_count = fields.Integer(
        string='РСБУ-проводки', compute='_compute_rsbu_move_count')

    def _rsbu_source_domain(self):
        self.ensure_one()
        return [('source_model', '=', self._name),
                ('source_res_id', '=', self.id)]

    @api.depends('rsbu_move_id')
    def _compute_rsbu_move_count(self):
        # Вместе со сторно и прежними проводками перепроведённого документа.
        Move = self.env['rsbu.move'].sudo()
        for rec in self:
            rec.rsbu_move_count = Move.search_count(
                rec._rsbu_source_domain()) if rec.id else 0

    # ------------------------------------------------------------------
    # Точки расширения (реализуются Этапом 4)
    # ------------------------------------------------------------------
    def _rsbu_is_applicable(self):
        """Входит ли документ в РСБУ-периметр (нужна ли РСБУ-проводка).

        На Этапе 3 маппинга ещё нет, поэтому по умолчанию False —
        штатное проведение документов Odoo не затрагивается. На Этапе 4
        применимость определяется матрицей связности (наличием шаблона).
        """
        self.ensure_one()
        return False

    def _rsbu_get_move_values(self):
        """Значения шапки rsbu.move для документа-источника."""
        self.ensure_one()
        return {
            'date': self._rsbu_move_date(),
            'company_id': self.company_id.id,
            'ref': self.display_name,
            'source_model': self._name,
            'source_res_id': self.id,
        }

    def _rsbu_move_date(self):
        """Дата РСБУ-операции. По умолчанию — поле date документа/сегодня."""
        self.ensure_one()
        return getattr(self, 'date', False) or fields.Date.context_today(self)

    def _rsbu_build_lines(self):
        """Список значений строк rsbu.move.line (Дт/Кт + субконто).

        ЗАГЛУШКА Этапа 3: возвращает пустой список -> трактуется как
        «нет маппинга». Реализуется маппингом на Этапе 4.
        """
        self.ensure_one()
        return []

    # ------------------------------------------------------------------
    # Механика
    # ------------------------------------------------------------------
    def _rsbu_generate(self):
        """Идемпотентно создать и провести РСБУ-операцию по документу.

        Управляемый обход: при context ``rsbu_skip=True`` генерация
        пропускается (по аналогии с with_user/with_context Odoo) —
        для служебных/внешних вызовов, где РСБУ-слой не нужен.
        """
        self.ensure_one()
        if self.env.context.get('rsbu_skip'):
            return
        # Слой включается по организации и с даты (решение владельца
        # 20.10.2026: флажком по организации, учёт с 01.01.2027).
        company = self.company_id
        if not company.rsbu_enabled:
            return
        if company.rsbu_start_date                 and self._rsbu_move_date() < company.rsbu_start_date:
            return
        if not self._rsbu_is_applicable() or self.rsbu_move_id:
            return
        lines = self._rsbu_build_lines()
        if not lines:
            raise UserError(_(
                'Не удалось сформировать РСБУ-проводку для «%s»: '
                'не определён маппинг типовой операции.')
                % self.display_name)
        vals = self._rsbu_get_move_values()
        # Служебный маркер резолвера: строки с origin_self=True ссылаются на
        # саму создаваемую проводку как на документ-основание (аванс).
        # Убираем маркер из vals строк (ORM его не знает) и запоминаем позиции.
        origin_self_idx = []
        clean_lines = []
        for i, line in enumerate(lines):
            line = dict(line)
            if line.pop('origin_self', False):
                origin_self_idx.append(i)
            clean_lines.append(line)
        vals['line_ids'] = [(0, 0, line) for line in clean_lines]
        # sudo: РСБУ-проводка — внутренняя механика, создаётся при проведении
        # документа независимо от прав пользователя на РСБУ-модели.
        move = self.env['rsbu.move'].sudo().create(vals)
        # Проставить origin_move_id = сама проводка для помеченных строк.
        if origin_self_idx:
            move_lines = move.line_ids
            for i in origin_self_idx:
                if i < len(move_lines):
                    move_lines[i].origin_move_id = move.id
        move.action_post()  # проверки баланса/субконто Этапа 2
        self.sudo().rsbu_move_id = move.id

    def _rsbu_remove(self):
        """Зеркалирование отмены: сторнировать связанную РСБУ-операцию.

        У выпуска операция удалялась — проведённый учёт пропадал без следа,
        в том числе в закрытом периоде. Черновик (не проведён) удаляется.
        """
        for rec in self:
            move = rec.rsbu_move_id.sudo()
            if move:
                rec.sudo().rsbu_move_id = False
                if move.state == 'posted':
                    move._reverse()
                else:
                    move.unlink()

    # ------------------------------------------------------------------
    # Навигация
    # ------------------------------------------------------------------
    def action_view_rsbu_move(self):
        self.ensure_one()
        moves = self.env['rsbu.move'].search(self._rsbu_source_domain())
        if len(moves) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('РСБУ-проводка'),
                'res_model': 'rsbu.move',
                'view_mode': 'form',
                'res_id': moves.id,
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('РСБУ-проводки'),
            'res_model': 'rsbu.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }
