import hmac
import json

from odoo import http
from odoo.http import request, Response

from ..services.partner_service import PartnerService
from ..services.product_service import ProductService
from ..services.sale_order_service import SaleOrderService


class IntegrationController(http.Controller):

    def _unauthorized(self):
        return Response(
            json.dumps({"error": "Unauthorized"}),
            status=401,
            content_type="application/json",
        )

    def _invalid_json(self):
        return Response(
            json.dumps({"error": "Invalid JSON"}),
            status=400,
            content_type="application/json",
        )

    def _check_token(self):
        expected_token = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("bas_api_token")
        )

        auth_header = request.httprequest.headers.get("Authorization", "")
        provided_token = (
            auth_header.removeprefix("Bearer ").strip()
            if auth_header.startswith("Bearer ")
            else ""
        )

        return bool(
            expected_token
            and provided_token
            and hmac.compare_digest(provided_token, expected_token)
        )

    def _parse_json_body(self):
        try:
            return json.loads(request.httprequest.data), None
        except (ValueError, TypeError):
            return None, self._invalid_json()

    @http.route(
        "/api/1c/partners",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def partners(self):
        if not self._check_token():
            return self._unauthorized()

        data, error_response = self._parse_json_body()
        if error_response:
            return error_response

        result = PartnerService(request.env).import_partners(data)
        return Response(json.dumps(result), content_type="application/json")

    @http.route(
        "/api/1c/products",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def products(self):
        if not self._check_token():
            return self._unauthorized()

        data, error_response = self._parse_json_body()
        if error_response:
            return error_response

        result = ProductService(request.env).import_products(data)
        return Response(json.dumps(result), content_type="application/json")

    @http.route(
        "/api/1c/sale_orders",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def sale_orders(self):
        if not self._check_token():
            return self._unauthorized()

        data, error_response = self._parse_json_body()
        if error_response:
            return error_response

        result = SaleOrderService(request.env).import_sale_orders(data)
        return Response(json.dumps(result), content_type="application/json")
