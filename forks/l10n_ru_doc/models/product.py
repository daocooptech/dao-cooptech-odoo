from odoo import fields, models


class ProductTnved(models.Model):
    _inherit = 'product.product'
    kod_tnved = fields.Char('Код ТНВЭД')

    def _ru_print_name(self, description=None):
        """Item name for print forms: the product name without the [code] prefix.

        In Odoo 20 the line label is the product display name with the code,
        then the line description. The print forms have a separate column for
        the product code, so the name column must not repeat it.
        """
        self.ensure_one()
        name = self.with_context(display_default_code=False).display_name
        if not description:
            return name
        lines = description.splitlines()
        # a description that already starts with the product name (with or
        # without the code), e.g. a line imported from an older version
        if lines and lines[0] in (name, self.with_context(display_default_code=True).display_name):
            return '\n'.join([name] + lines[1:])
        return '%s\n%s' % (name, description)
