from odoo import models
from datetime import datetime
import re
import pymorphy3
from markupsafe import Markup

FRACTIONS = (
    (u"десятая", u"десятых", u"десятых"),
    (u"сотая", u"сотых", u"сотых"),
    (u"тысячная", u"тысячных", u"тысячных"),
    (u"десятитысячная", u"десятитысячных", u"десятитысячных"),
    (u"стотысячная", u"стотысячных", u"стотысячных"),
    (u"миллионная", u"милллионных", u"милллионных"),
    (u"десятимиллионная", u"десятимилллионных", u"десятимиллионных"),
    (u"стомиллионная", u"стомилллионных", u"стомиллионных"),
    (u"миллиардная", u"миллиардных", u"миллиардных"),
)

ONES = {
    0: (u"", u"", u""),
    1: (u"один", u"одна", u"одно"),
    2: (u"два", u"две", u"два"),
    3: (u"три", u"три", u"три"),
    4: (u"четыре", u"четыре", u"четыре"),
    5: (u"пять", u"пять", u"пять"),
    6: (u"шесть", u"шесть", u"шесть"),
    7: (u"семь", u"семь", u"семь"),
    8: (u"восемь", u"восемь", u"восемь"),
    9: (u"девять", u"девять", u"девять"),
}

TENS = {
    0: u"",
    10: u"десять",
    11: u"одиннадцать",
    12: u"двенадцать",
    13: u"тринадцать",
    14: u"четырнадцать",
    15: u"пятнадцать",
    16: u"шестнадцать",
    17: u"семнадцать",
    18: u"восемнадцать",
    19: u"девятнадцать",
    2: u"двадцать",
    3: u"тридцать",
    4: u"сорок",
    5: u"пятьдесят",
    6: u"шестьдесят",
    7: u"семьдесят",
    8: u"восемьдесят",
    9: u"девяносто",
}

HUNDREDS = {
    0: u"",
    1: u"сто",
    2: u"двести",
    3: u"триста",
    4: u"четыреста",
    5: u"пятьсот",
    6: u"шестьсот",
    7: u"семьсот",
    8: u"восемьсот",
    9: u"девятьсот",
}

MALE = 1
FEMALE = 2

import sys
import types

PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3

if PY3:
    string_types = str,
    integer_types = int,
    class_types = type,
    text_type = str
    binary_type = bytes

    MAXSIZE = sys.maxsize
else:
    string_types = basestring,
    integer_types = (int, long)
    class_types = (type, types.ClassType)
    text_type = unicode
    binary_type = str


class Report_contract_customer(models.Model):
    _inherit = 'partner.contract.customer'

    def img(self, img, type='png', width=0, height=0):
        # Odoo 20: Binary-поле отдаёт BinaryValue, а не base64-текст; вывод через t-out
        # экранируется, поэтому готовый <img> возвращаем как Markup.
        if not img:
            return Markup('')
        if hasattr(img, 'to_base64'):
            img = img.to_base64()
        elif isinstance(img, bytes):
            img = img.decode()
        width = "width='%spx'" % width if width else ' '
        height = "height='%spx'" % height if height else ' '
        return Markup("<img %s %s src='data:image/%s;base64,%s' />") % (
            Markup(width), Markup(height), type, img)

    def numer(self, name):
        if name:
            numeration = re.findall('\d+$', name)
            if numeration: return numeration[0]
        return ''

    def ru_date(self, date):
        if date and date != 'False':
            return dt.ru_strftime(u'"%d" %B %Y года', date=datetime.strptime(str(date), "%Y-%m-%d"), inflected=True)
        return ''

    def ru_date2(self, date):
        if date and date != 'False':
            return dt.ru_strftime(u'%d %B %Y г.', date=datetime.strptime(str(date), "%Y-%m-%d %H:%M:%S"),
                                  inflected=True)
        return ''

    def in_words(self, number):
        return numeral.in_words(number)

    def rubles(self, sum):
        "Transform sum number in rubles to text"
        text_rubles = self.numeral_rubles(int(sum))
        copeck = round((sum - int(sum)) * 100)
        text_copeck = self.numeral_choose_plural(int(copeck), (u"копейка", u"копейки", u"копеек"))
        return ("%s %02d %s") % (text_rubles, copeck, text_copeck)

    def numeral_rubles(self, amount, zero_for_kopeck=False):
        self.check_positive(amount)
        pts = []
        amount = round(amount, 2)
        pts.append(self.sum_string(int(amount), 1, (u"рубль", u"рубля", u"рублей")))
        remainder = self._get_float_remainder(amount, 2)
        iremainder = int(remainder)

        if iremainder != 0 or zero_for_kopeck:
            if iremainder < 10 and len(remainder) == 1:
                iremainder *= 10
            pts.append(self.sum_string(iremainder, 2,
                                       (u"копейка", u"копейки", u"копеек")))
        return u" ".join(pts)

    def _get_float_remainder(self, fvalue, signs=9):
        self.check_positive(fvalue)
        if isinstance(fvalue, integer_types):
            return "0"
        if isinstance(fvalue, Decimal) and fvalue.as_tuple()[2] == 0:
            return "0"

    def sum_string(self, amount, gender, items=None):
        if isinstance(items, text_type):
            items = split_values(items)
        if items is None:
            items = (u"", u"", u"")
        try:
            one_item, two_items, five_items = items
        except ValueError:
            raise ValueError("Items must be 3-element sequence")
        self.check_positive(amount)
        if amount == 0:
            return u"ноль %s" % five_items
        into = u''
        tmp_val = amount
        into, tmp_val = self._sum_string_fn(into, tmp_val, gender, items)
        into, tmp_val = self._sum_string_fn(into, tmp_val, FEMALE,
                                            (u"тысяча", u"тысячи", u"тысяч"))
        into, tmp_val = self._sum_string_fn(into, tmp_val, MALE,
                                            (u"миллион", u"миллиона", u"миллионов"))
        into, tmp_val = self._sum_string_fn(into, tmp_val, MALE,
                                            (u"миллиард", u"миллиарда", u"миллиардов"))
        if tmp_val == 0:
            return into
        else:
            raise ValueError("Cannot operand with numbers bigger than 10**11")

    def _sum_string_fn(self, into, tmp_val, gender, items=None):
        if items is None:
            items = (u"", u"", u"")
        one_item, two_items, five_items = items
        self.check_positive(tmp_val)
        if tmp_val == 0:
            return into, tmp_val
        words = []
        rest = tmp_val % 1000
        tmp_val = tmp_val // 1000
        if rest == 0:
            if into == u"":
                into = u"%s " % five_items
            return into, tmp_val
        end_word = five_items
        words.append(HUNDREDS[rest // 100])
        rest = rest % 100
        rest1 = rest // 10
        tens = rest1 == 1 and TENS[rest] or TENS[rest1]
        words.append(tens)
        if rest1 < 1 or rest1 > 1:
            amount = rest % 10
            end_word = self.numeral_choose_plural(amount, items)
            words.append(ONES[amount][gender - 1])
        words.append(end_word)
        words.append(into)
        words = filter(lambda x: len(x) > 0, words)
        return u" ".join(words).strip(), tmp_val

    def check_positive(self, value, strict=False):
        if not strict and value < 0:
            raise ValueError("Value must be positive or zero, not %s" % str(value))
        if strict and value <= 0:
            raise ValueError("Value must be positive, not %s" % str(value))

    def numeral_choose_plural(self, amount, variants):
        if isinstance(variants, text_type):
            variants = split_values(variants)
        self.check_length(variants, 3)
        amount = abs(amount)
        if amount % 10 == 1 and amount % 100 != 11:
            variant = 0
        elif amount % 10 >= 2 and amount % 10 <= 4 and \
                (amount % 100 < 10 or amount % 100 >= 20):
            variant = 1
        else:
            variant = 2
        return variants[variant]

    def check_length(self, value, length):
        _length = len(value)
        if _length != length:
            raise ValueError("length must be %d, not %d" % \
                             (length, _length))

    def initials(self, fio):
        if fio:
            return (fio.split()[0] + ' ' + ''.join([fio[0:1] + '.' for fio in fio.split()[1:]])).strip()
        return ''

    def address(self, partner):
        repr = []
        if partner.zip: repr.append(partner.zip)
        if partner.city: repr.append(partner.city)
        if partner.street: repr.append(partner.street)
        if partner.street2: repr.append(partner.street2)
        return ', '.join(repr)

    def address_delivery(self, partner):
        if partner:
            addr = self.env['res.partner'].search([('parent_id', '=', partner), ('type', '=', 'delivery')], limit=1)
            repr = []
            if addr:
                if addr.zip: repr.append(addr.zip)
                if addr.city: repr.append(addr.city)
                if addr.street: repr.append(addr.street)
                if addr.street2: repr.append(addr.street2)
                return ', '.join(repr)

    def get_function_print(self, function):
        morph = pymorphy3.MorphAnalyzer()
        if function:
            f = morph.parse(function)[0]
            f = f.inflect({'gent'}).word
            return f.title()

    def get_function_partnerip(self, partner):
        director = self.env['res.partner'].search([('parent_id', '=', partner), ('type', '=', 'director')], limit=1)
        if director:
            if director.function:
                return director.function

    def get_function_partner(self, partner):
        res = []
        morph = pymorphy3.MorphAnalyzer()
        if partner:
            director = self.env['res.partner'].search([('parent_id', '=', partner), ('type', '=', 'director')], limit=1)
            if director:
                if director.function:
                    list_f = str(director.function).split(' ')
                    for func in list_f:
                        f = morph.parse(func)[0]
                        f = f.inflect({'gent'}).word
                        res.append(f)
                    return ' '.join(res)



    def get_date_text(self, date):
        month_list = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября',
                      'ноября', 'декабря']
        if date:
            date_list = str(date).split('-')
            if date_list[0] and date_list[1] and date_list[2]:
                return ('"' + date_list[2] + '" ' + month_list[int(date_list[1]) - 1] + ' ' + date_list[0] + ' г.')

    def get_bank(self, partner):
        repr = []
        bank = None
        if partner.bank_ids:
            bank = partner.bank_ids[0]
        elif partner.parent_id.bank_ids:
            bank = partner.parent_id.bank_ids[0]
        if bank and bank.bank_name: repr.append(bank.bank_name)
        if bank and bank.acc_number: repr.append(u"Р/счет " + bank.acc_number)
        if bank and bank.bank_bic: repr.append(u"БИК " + bank.bank_bic)
        if bank and bank.bank_corr_acc: repr.append(u"к/с " + bank.bank_corr_acc)
        return '<br/>'.join(repr)
