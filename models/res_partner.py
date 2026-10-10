from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    x_bas_id = fields.Char(
        string="BAS ID",
        index=True,
    )
    
    x_bas_full_name = fields.Text(string="Full name",)
    