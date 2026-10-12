from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    x_bas_id = fields.Char(
        string="BAS ID",
        index=True,
    )
