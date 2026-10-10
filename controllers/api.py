   
    
import hmac
import json

from odoo import http
from odoo.http import request, Response

from ..services.partner_service import PartnerService


class IntegrationController(http.Controller):

    @http.route("/api/1c/partners", type="http", auth="public", methods=["POST"], csrf=False,)
    def partners(self):
        expected_token = (request.env["ir.config_parameter"].sudo().get_param("bas_api_token")
        )

        auth_header = request.httprequest.headers.get("Authorization", "")
        provided_token = (
            auth_header.removeprefix("Bearer ").strip()
            if auth_header.startswith("Bearer ")
            else ""
        )

        if (
            not expected_token
            or not provided_token
            or not hmac.compare_digest(
                provided_token, expected_token
            )
        ):
            return Response(
                json.dumps({"error": "Unauthorized"}),
                status=401,
                content_type="application/json",
            )

        try:
            data = json.loads(request.httprequest.data)
        except (ValueError, TypeError):
            return Response(
                json.dumps({"error": "Invalid JSON"}),
                status=400,
                content_type="application/json",
            )

        result = PartnerService(request.env).import_partners(data)

        return Response(json.dumps(result), content_type="application/json",)
