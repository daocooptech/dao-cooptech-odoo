from odoo import http
from odoo.http import request
from datetime import datetime, date


class ActRevise(http.Controller):

    @http.route(['/my/act_revise/<string:act>'], type='http', auth="public", website=True)
    def print_report(self):
        partner = request.env.user.partner_id.parent_id.id
        partner_name = request.env.user.partner_id.parent_id.name
        if not partner:
            partner = request.env.user.partner_id.id
            partner_name = request.env.user.partner_id.name
        company = request.env.user.company_id.id
        company_name = request.env.user.company_id.name
        today = date.today()
        d1 = today.strftime("%d.%m.%y")

        wizard_data = {
            "target_move": "posted",
            "hide_account_at_0": True,
            "foreign_currency": True,
            "company_id": company,
            "partner_ids": [partner],
            "show_cost_center": True,
            "centralize": True
        }
        wizard_record = request.env['general.ledger.act_revise.wizard'].sudo().create(wizard_data)

        action = request.env.ref('l10n_ru_act_rev.action_general_ledger_wizard').read()[0]
        action['res_id'] = wizard_record.id
        action['context'] = dict(request.env.context)
        return request.redirect('/web#action=' + str(action['id']) + '&id=' + str(wizard_record.id) + '&view_type=form')

    # @http.route(['/my/act_revise/<string:act>'], type='http', auth="public", website=True)
    # def print_report(self):
        # partner = request.env.user.partner_id.parent_id.id
        # partner_name = request.env.user.partner_id.parent_id.name
        # if not partner:
        #     partner = request.env.user.partner_id.id
        #     partner_name = request.env.user.partner_id.name
        # company = request.env.user.company_id.id
        # company_name = request.env.user.company_id.name
        # today = date.today()
        # d1 = today.strftime("%d.%m.%y")
        # # new_url = str('Акт Сверки ' + d1 + ' ' + company_name + '_' + partner_name)
        # # new_url=str('AC ' + company +' - ' + partner + ' ' + d1)
        # # if request.httprequest.full_path == '/my/act_revise/a?':
        # #     return werkzeug.utils.redirect('/my/act_revise/%s' % new_url)
        # wizard_data = {"target_move": "posted",
        #                "hide_account_at_0": True,
        #                "foreign_currency": True,
        #                #"show_analytic_tags": True,
        #                "company_id": company,
        #                "partner_ids": [partner],
        #                #"show_partner_details": True,
        #                "show_cost_center": True,
        #                "centralize": True}
        # t = request.env['general.ledger.act_revise.wizard'].sudo().create(wizard_data)
        # data = t._prepare_report_general_ledger()
        # name = t.get_report_filename()
        # report_name = name.encode('cp1251')
        # pdf, _ = request.env['ir.actions.report']._render_qweb_pdf(
        #     'act_revise.action_print_report_general_ledger_qweb', res_ids=t.id, data=data)
        # pdfhttpheaders = [('Content-Type', 'application/pdf'), ('Content-Length', len(pdf)), ]
        # return request.make_response(pdf, headers=pdfhttpheaders)

    @http.route(['/my/act_revise_contact/<string:act>'], type='http', auth="public", website=True)
    def print_report_contact(self, date_to, date_from, target_move, company, partner):
        partner_id = int(partner) or 'default_partner_value'
        company_id = int(company)
        wizard_data = {"date_to": date_to,
                       "date_from": date_from,
                       "target_move": target_move,
                       "hide_account_at_0": True,
                       "foreign_currency": True,
                       #"show_analytic_tags": True,
                       "company_id": company_id,
                       "partner_ids": [partner_id],
                       #"show_partner_details": True,
                       "show_cost_center": True,
                       "centralize": True}
        t = request.env['general.ledger.act_revise.wizard'].sudo().create(wizard_data)
        data = t._prepare_report_general_ledger()
        pdf, _ = request.env['ir.actions.report']._render_qweb_pdf(
            'l10n_ru_act_rev.action_print_report_general_ledger_qweb', res_ids=t.id, data=data)
        pdfhttpheaders = [('Content-Type', 'application/pdf'), ('Content-Length', len(pdf)), ]
        return request.make_response(pdf, headers=pdfhttpheaders)