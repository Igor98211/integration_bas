from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    x_bas_id = fields.Char(
        string="BAS ID",
        index=True,
    )

    x_bas_full_name = fields.Text(string="Full name")
