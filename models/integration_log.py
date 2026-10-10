
from odoo import fields, models


class IntegrationLog(models.Model):
    _name = "integration.log"
    _description = "Integration Log"
    _order = "create_date desc"

    external_id = fields.Char(string="External ID", index=True,)

    object_type = fields.Selection(
        selection=[("partner", "Partner"),("product", "Product"),],
        string="Object Type",
        required=True,
        index=True,
    )

    status = fields.Selection(
        selection=[("success", "Success"), ("error", "Error"),],
        string="Status",
        required=True,
        index=True,
    )

    odoo_id = fields.Integer(string="Odoo ID",)

    message = fields.Text(string="Message",)
    
    description = fields.Text(string="Description",)

