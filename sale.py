# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (c) 2010-2013 Elico Corp. All Rights Reserved.
#    Author: Yannick Gouin <yannick.gouin@elico-corp.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import copy
from datetime import datetime, timedelta
import time
from openerp import netsvc
import openerp.addons.decimal_precision as dp
from openerp.tools.translate import _
import itertools

from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT

from openerp.osv import fields, osv, expression

from openerp import models, api, _
from openerp.exceptions import except_orm, Warning, RedirectWarning

class sale_order(osv.osv):
    _inherit = "sale.order"
    _name = "sale.order"
    
    def _amount_all(self, cr, uid, ids, field_name, arg, context=None):
        #print "Amount ALL IN the sale....."
        cur_obj = self.pool.get('res.currency')
        res = {}
        for order in self.browse(cr, uid, ids, context=context):
            res[order.id] = {
                'amount_untaxed': 0.0,
                'amount_tax': 0.0,
                'amount_total': 0.0,
                #'global_discount':0.00
            }
            val = val1 = 0.0
            cur = order.pricelist_id.currency_id
            global_discount = order.global_discount
            for line in order.order_line:
                val1 += line.price_subtotal
                val += self._amount_line_tax(cr, uid, line, context=context)
            res[order.id]['amount_tax'] = cur_obj.round(cr, uid, cur, val)
            res[order.id]['amount_untaxed'] = cur_obj.round(cr, uid, cur, val1)
            disc_amount = global_discount or 0.00
            res[order.id]['amount_total'] = res[order.id]['amount_untaxed'] + res[order.id]['amount_tax'] - disc_amount
        return res
    
    _columns = {
        'global_discount': fields.float('Discount', digits_compute=dp.get_precision('Discount'), readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}),
        'amount_total': fields.function(_amount_all, method=True, digits_compute= dp.get_precision('Sale Price'), string='Total',
                                            store = True,multi='sums', help="The total amount."),
    }
    _defaults={
               'global_discount': 0.0,
               }
    
    def _make_invoice(self, cr, uid, order, lines, context=None):
        inv_obj = self.pool.get('account.invoice')
        obj_invoice_line = self.pool.get('account.invoice.line')
        if context is None:
            context = {}
        invoiced_sale_line_ids = self.pool.get('sale.order.line').search(cr, uid, [('order_id', '=', order.id), ('invoiced', '=', True)], context=context)
        from_line_invoice_ids = []
        for invoiced_sale_line_id in self.pool.get('sale.order.line').browse(cr, uid, invoiced_sale_line_ids, context=context):
            for invoice_line_id in invoiced_sale_line_id.invoice_lines:
                if invoice_line_id.invoice_id.id not in from_line_invoice_ids:
                    from_line_invoice_ids.append(invoice_line_id.invoice_id.id)
        for preinv in order.invoice_ids:
            if preinv.state not in ('cancel',) and preinv.id not in from_line_invoice_ids:
                for preline in preinv.invoice_line:
                    inv_line_id = obj_invoice_line.copy(cr, uid, preline.id, {'invoice_id': False, 'price_unit': -preline.price_unit})
                    lines.append(inv_line_id)
        inv = self._prepare_invoice(cr, uid, order, lines, context=context)
        inv_id = inv_obj.create(cr, uid, inv, context=context)
        data = inv_obj.onchange_payment_term_date_invoice(cr, uid, [inv_id], inv['payment_term'], time.strftime(DEFAULT_SERVER_DATE_FORMAT))
        if data.get('value', False):
            inv_obj.write(cr, uid, [inv_id], data['value'], context=context)
        inv_obj.button_compute(cr, uid, [inv_id])
        inv_obj.write(cr, uid, [inv_id],{
                                         'global_discount_invoice':order.global_discount or 0.00
                                         }, context=context)
        
        return inv_id

    def onchange_global_discount(self, cr, uid, ids, global_discount,amount_net,amount_total, context):
        
        res = super(sale_order, self)._amount_all(cr, uid, ids, global_discount, context)
        value ={}
        global_discount = global_discount or 0.00
        for order in self.browse(cr, uid, ids, context=context):
            o_res = res[order.id]
            #total_amount = 0
            value['global_discount'] = global_discount
            value['amount_net'] = order.amount_untaxed - global_discount

            # we apply a discount on the tax as well.
            # We might have rounding issue
            #o_res['amount_tax'] = cur_round(o_res['amount_tax'] ) #* (100.0 - (add_disc or 0.0))/100.0)
            #o_res['amount_total'] = o_res['amount_net'] + o_res['amount_tax'] original with tax
            value['amount_total'] = value['amount_net']
        return {'value': value}
sale_order()



class account_invoice(osv.osv):
    _inherit = "account.invoice"
    _name = "account.invoice"
    
    def _amount_all(self, cr, uid, ids, field_name, arg, context=None):
        cur_obj = self.pool.get('res.currency')
        res = {}
        for inv in self.browse(cr, uid, ids, context=context):
            res[inv.id] = {
                'amount_untaxed': 0.0,
                'amount_tax': 0.0,
                'amount_total': 0.0,
                #'amount_residual': 0.0,
                #'global_discount':0.00
            }
            val = val1 = 0.0
            cur = inv.currency_id
            global_discount_invoice = inv.global_discount_invoice
            for line in inv.invoice_line:
                val1 += line.price_subtotal
                #removing Tax Amount
                #val += self.compute(cr, uid, line, context=context)
            #removing Tax Amount
            #res[inv.id]['amount_tax'] = cur_obj.round(cr, uid, cur, val)
            res[inv.id]['amount_untaxed'] = cur_obj.round(cr, uid, cur, val1)
            disc_amount = global_discount_invoice or 0.00
            res[inv.id]['amount_total'] = res[inv.id]['amount_untaxed'] + res[inv.id]['amount_tax'] - global_discount_invoice
            #res[inv.id]['amount_residual'] = res[inv.id]['amount_total']
            
        return res
    
    @api.one
    @api.depends('invoice_line.price_subtotal', 'tax_line.amount','global_discount_invoice')
    def _compute_amount(self):
        self.amount_untaxed = sum(line.price_subtotal for line in self.invoice_line)
        self.amount_tax = sum(line.amount for line in self.tax_line)
        #self.global_discount_invoice = self.global_discount_invoice
        self.amount_total = self.amount_untaxed + self.amount_tax - self.global_discount_invoice

    @api.one
    @api.depends(
        'state', 'currency_id', 'invoice_line.price_subtotal',
        'move_id.line_id.account_id.type',
        'move_id.line_id.amount_residual',
        # Fixes the fact that move_id.line_id.amount_residual, being not stored and old API, doesn't trigger recomputation
        'move_id.line_id.reconcile_id',
        'move_id.line_id.amount_residual_currency',
        'move_id.line_id.currency_id',
        'move_id.line_id.reconcile_partial_id.line_partial_ids.invoice.type',
    )
    # An invoice's residual amount is the sum of its unreconciled move lines and,
    # for partially reconciled move lines, their residual amount divided by the
    # number of times this reconciliation is used in an invoice (so we split
    # the residual amount between all invoice)
    def _compute_residual(self):
        self.residual = 0.0
        # Each partial reconciliation is considered only once for each invoice it appears into,
        # and its residual amount is divided by this number of invoices
        partial_reconciliations_done = []
        for line in self.sudo().move_id.line_id:
            if line.account_id.type not in ('receivable', 'payable'):
                continue
            if line.reconcile_partial_id and line.reconcile_partial_id.id in partial_reconciliations_done:
                continue
            # Get the correct line residual amount
            if line.currency_id == self.currency_id:
                line_amount = line.amount_residual_currency if line.currency_id else line.amount_residual
            else:
                from_currency = line.company_id.currency_id.with_context(date=line.date)
                line_amount = from_currency.compute(line.amount_residual, self.currency_id)
            # For partially reconciled lines, split the residual amount
            if line.reconcile_partial_id:
                partial_reconciliation_invoices = set()
                for pline in line.reconcile_partial_id.line_partial_ids:
                    if pline.invoice and self.type == pline.invoice.type:
                        partial_reconciliation_invoices.update([pline.invoice.id])
                line_amount = self.currency_id.round(line_amount / len(partial_reconciliation_invoices))
                partial_reconciliations_done.append(line.reconcile_partial_id.id)
            self.residual += line_amount
        global_discount_invoice = self.global_discount_invoice
        self.residual = max(self.residual, 0.0)

    
    _columns = {
        'global_discount_invoice': fields.float('Discount', digits_compute=dp.get_precision('Discount'), readonly=True, states={'draft': [('readonly', False)]}),
        }
    
    _defaults={
               'global_discount_invoice': 0.0,
               }
        
      
    def onchange_global_discount_invoice(self, cr, uid, ids, global_discount_invoice, context):
        
        res = self.pool.get("account.invoice")._amount_all(cr, uid, ids, global_discount_invoice, context)
        value ={}
        global_discount_invoice = global_discount_invoice or 0.00
        for order in self.browse(cr, uid, ids, context=context):
            
            value['global_discount_invoice'] = global_discount_invoice
            value['amount_net'] = order.amount_untaxed - global_discount_invoice

            # we apply a discount on the tax as well.
            # We might have rounding issue
            #o_res['amount_tax'] = cur_round(o_res['amount_tax'] ) #* (100.0 - (add_disc or 0.0))/100.0)
            #o_res['amount_total'] = o_res['amount_net'] + o_res['amount_tax'] original with tax
            value['amount_total'] = value['amount_net']
            #value['residual'] = value['amount_total']
        return {'value': value}
    @api.multi
    def action_move_create(self):
        """ Creates invoice related analytics and financial move lines """
        account_invoice_tax = self.env['account.invoice.tax']
        account_move = self.env['account.move']
        
        for inv in self:
            if not inv.journal_id.sequence_id:
                raise except_orm(_('Error!'), _('Please define sequence on the journal related to this invoice.'))
            if not inv.invoice_line:
                raise except_orm(_('No Invoice Lines!'), _('Please create some invoice lines.'))
            if inv.move_id:
                continue

            ctx = dict(self._context, lang=inv.partner_id.lang)

            if not inv.date_invoice:
                inv.with_context(ctx).write({'date_invoice': datetime.today().strftime(DEFAULT_SERVER_DATE_FORMAT)})
            date_invoice = inv.date_invoice

            company_currency = inv.company_id.currency_id
            # create the analytical lines, one move line per invoice line
            iml = inv._get_analytic_lines()
            # check if taxes are all computed
            compute_taxes = account_invoice_tax.compute(inv.with_context(lang=inv.partner_id.lang))
            inv.check_tax_lines(compute_taxes)

            # I disabled the check_total feature
            if self.env['res.users'].has_group('account.group_supplier_inv_check_total'):
                if inv.type in ('in_invoice', 'in_refund') and abs(inv.check_total - inv.amount_total) >= (inv.currency_id.rounding / 2.0):
                    raise except_orm(_('Bad Total!'), _('Please verify the price of the invoice!\nThe encoded total does not match the computed total.'))

            if inv.payment_term:
                total_fixed = total_percent = 0
                for line in inv.payment_term.line_ids:
                    if line.value == 'fixed':
                        total_fixed += line.value_amount
                    if line.value == 'procent':
                        total_percent += line.value_amount
                total_fixed = (total_fixed * 100) / (inv.amount_total or 1.0)
                if (total_fixed + total_percent) > 100:
                    raise except_orm(_('Error!'), _("Cannot create the invoice.\nThe related payment term is probably misconfigured as it gives a computed amount greater than the total invoiced amount. In order to avoid rounding issues, the latest line of your payment term must be of type 'balance'."))

            # one move line per tax line
            iml += account_invoice_tax.move_line_get(inv.id)

            #iml += self.move_line_get(inv.id)


            if inv.type in ('in_invoice', 'in_refund'):
                ref = inv.reference
            else:
                ref = inv.number

            diff_currency = inv.currency_id != company_currency
            # create one move line for the total and possibly adjust the other lines amount
            total, total_currency, iml = inv.with_context(ctx).compute_invoice_totals(company_currency, ref, iml)

            name = inv.supplier_invoice_number or inv.name or '/'
            discount = 0.00
            totlines = []
            
            if inv.global_discount_invoice:
                discount  = inv.global_discount_invoice
            if inv.type=='out_invoice':            
                total = total - discount
            if inv.type=='in_invoice':            
                total = total + discount
            if inv.payment_term:
                totlines = inv.with_context(ctx).payment_term.compute(total, date_invoice)[0]
            
            if totlines:
                res_amount_currency = total_currency
                ctx['date'] = date_invoice
                for i, t in enumerate(totlines):
                    if inv.currency_id != company_currency:
                        amount_currency = company_currency.with_context(ctx).compute(t[1], inv.currency_id)
                    else:
                        amount_currency = False

                    # last line: add the diff
                    res_amount_currency -= amount_currency or 0
                    if i + 1 == len(totlines):
                        amount_currency += res_amount_currency

                    iml.append({
                        'type': 'dest',
                        'name': name,
                        'price': t[1],
                        'account_id': inv.account_id.id,
                        'date_maturity': t[0],
                        'amount_currency': diff_currency and amount_currency,
                        'currency_id': diff_currency and inv.currency_id.id,
                        'ref': ref,
                    })

            else:
                iml.append({
                    'type': 'dest',
                    'name': name,
                    'price': total,
                    'account_id': inv.account_id.id,
                    'date_maturity': inv.date_due,
                    'amount_currency': diff_currency and total_currency,
                    'currency_id': diff_currency and inv.currency_id.id,
                    'ref': ref
                })

            date = date_invoice

            part = self.env['res.partner']._find_accounting_partner(inv.partner_id)

            line = [(0, 0, self.line_get_convert(l, part.id, date)) for l in iml]

            line = inv.group_lines(iml, line)
            system_parameter_obj = self.env['ir.config_parameter']
            discount_account_id = False
            if discount >0.00:
                discount_account_id = False
                parameter = system_parameter_obj.search([('key','=','discount_account_id')])
                if parameter:
                    discount_account_id = parameter.value
                else:
                    raise except_orm(_('Warning!'), _("Please Configure Discount Account in System Parameters.\n (key='discount_account_id' & value=<account_id>)"))
                if discount_account_id == False:
                    raise except_orm(_('Warning!'), _("Please assign Discount Account in System Parameters"))
                
                if inv.type=='in_invoice':
                    discount_line = (0, 0, 
                                {'analytic_account_id': False, 
                                'tax_code_id': False, 
                                'analytic_lines': [], 
                                'tax_amount': False, 
                                'name': 'Discount Amount Credit', 
                                'ref': False, 
                                'currency_id': False,
                                'credit': discount,
                                'product_id': False,
                                'date_maturity': inv.date_invoice,
                                'debit': False,
                                'date': inv.date_invoice,
                                'amount_currency': 0,
                                'product_uom_id': False,
                                'quantity': 1.0,
                                'partner_id': inv.partner_id.id,
                                'account_id': int(discount_account_id)})
                if inv.type=='out_invoice':
                    discount_line = (0, 0, 
                                {'analytic_account_id': False, 
                                'tax_code_id': False, 
                                'analytic_lines': [], 
                                'tax_amount': False, 
                                'name': 'Discount Amount Debit', 
                                'ref': False, 
                                'currency_id': False,
                                'credit': False,
                                'product_id': False,
                                'date_maturity': inv.date_invoice,
                                'debit': discount,
                                'date': inv.date_invoice,
                                'amount_currency': 0,
                                'product_uom_id': False,
                                'quantity': 1.0,
                                'partner_id': inv.partner_id.id,
                                'account_id': int(discount_account_id)})
            journal = inv.journal_id.with_context(ctx)
            if journal.centralisation:
                raise except_orm(_('User Error!'),
                        _('You cannot create an invoice on a centralized journal. Uncheck the centralized counterpart box in the related journal from the configuration menu.'))

            line = inv.finalize_invoice_move_lines(line)
            if discount:
                line.append(discount_line)

            move_vals = {
                'ref': inv.reference or inv.name,
                'line_id': line,
                'journal_id': journal.id,
                'date': inv.date_invoice,
                'narration': inv.comment,
                'company_id': inv.company_id.id,
            }
            ctx['company_id'] = inv.company_id.id
            period = inv.period_id
            if not period:
                period = period.with_context(ctx).find(date_invoice)[:1]
            if period:
                move_vals['period_id'] = period.id
                for i in line:
                    i[2]['period_id'] = period.id

            ctx['invoice'] = inv
            ctx_nolang = ctx.copy()
            ctx_nolang.pop('lang', None)
            move = account_move.with_context(ctx_nolang).create(move_vals)

            # make the invoice point to that move
            vals = {
                'move_id': move.id,
                'period_id': period.id,
                'move_name': move.name,
            }
            inv.with_context(ctx).write(vals)
            # Pass invoice in context in method post: used if you want to get the same
            # account move reference when creating the same invoice after a cancelled one:
            move.post()
        self._log_event()
        return True
account_invoice()


class account_move(osv.osv):
    _inherit = "account.move"

    def post(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        invoice = context.get('invoice', False)
        valid_moves = self.validate(cr, uid, ids, context)

        if not valid_moves:
            raise osv.except_osv(_('Error!'), _('You cannot validate a non-balanced entry.\nMake sure you have configured payment terms properly.\nThe latest payment term line should be of the "Balance" type.'))
        obj_sequence = self.pool.get('ir.sequence')
        for move in self.browse(cr, uid, valid_moves, context=context):
            if move.name =='/':
                new_name = False
                journal = move.journal_id

                if invoice and invoice.internal_number:
                    new_name = invoice.internal_number
                if new_name=='/' or new_name is False:
                    if journal.sequence_id:
                        c = {'fiscalyear_id': move.period_id.fiscalyear_id.id}
                        new_name = obj_sequence.next_by_id(cr, uid, journal.sequence_id.id, c)
                    else:
                        raise osv.except_osv(_('Error!'), _('Please define a sequence on the journal.'))

                if new_name:
                    self.write(cr, uid, [move.id], {'name':new_name})

        cr.execute('UPDATE account_move '\
                   'SET state=%s '\
                   'WHERE id IN %s',
                   ('posted', tuple(valid_moves),))
        self.invalidate_cache(cr, uid, context=context)
        return True
account_move()
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
