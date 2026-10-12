from odoo import _
from odoo.exceptions import ValidationError


class ProductService:

    def __init__(self, env):
        self.env = env

    def import_products(self, data):
        results = []
        success = True

        for item in data.get("products", []):
            try:
                external_id = item.get("guid")

                if not external_id:
                    raise ValidationError(_("Product guid is required."))

                product = self._find_product(item)

                # Do not create a product marked for deletion / inactive.
                if (
                    item.get("deleted")
                    or item.get("deletion_mark")
                    or item.get("inactive")
                ):
                    if product:
                        product.write({"active": False})
                        status = "archived"
                    else:
                        status = "skipped_deleted"

                else:
                    values = self._prepare_values(item)

                    if product:
                        product.write(values)
                        status = "updated"
                    else:
                        product = (
                            self.env["product.template"]
                            .sudo()
                            .create(values)
                        )
                        status = "created"

                self._log_success(item, product, status)

                results.append({
                    "external_id": external_id,
                    "odoo_id": product.id if product else None,
                    "status": status,
                })

            except Exception as error:
                success = False
                self._log_error(item, error)

                results.append({
                    "external_id": item.get("guid"),
                    "status": "error",
                    "message": str(error),
                })

        return {
            "success": success,
            "results": results,
        }

    def _find_product(self, item):
        external_id = item.get("guid")

        return (
            self.env["product.template"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [("x_bas_id", "=", external_id)],
                limit=1,
            )
        )

    def _prepare_values(self, item):
        values = {
            "name": (
                item.get("name")
                or item.get("full_name")
                or _("Unnamed product")
            ),
            "x_bas_id": item.get("guid"),
            "x_bas_full_name": item.get("full_name"),
            "active": True,
        }

        # Prefer article (SKU); fall back to BAS code.
        article = (item.get("article") or "").strip()
        code = (item.get("code") or "").strip()
        if article:
            values["default_code"] = article
        elif code:
            values["default_code"] = code

        # BAS product_type -> Odoo 19 type / is_storable.
        # stock -> Goods tracked in inventory
        # service -> Service (commented until needed)
        # other -> keep Odoo defaults
        product_type = (item.get("product_type") or "").strip().lower()
        if product_type == "stock":
            values["type"] = "consu"
            values["is_storable"] = True
        # elif product_type == "service":
        #     values["type"] = "service"
        #     values["is_storable"] = False

        if item.get("comment") and str(item["comment"]).strip():
            values["description_sale"] = str(item["comment"]).strip()

        # --- Not loaded yet (left for later mapping) ---
        # unit_guid / unit_name / unit_code -> uom.uom (uom_id)
        #   Default remains uom.product_uom_unit ("Units" / "шт").
        # category_guid / category_name -> product.category (categ_id)
        # manufacturer_guid / manufacturer_name -> no standard field
        # country_guid / country_name -> res.country (optional)
        # vat_rate_kind -> account.tax / taxes_id
        # warehouse_guid / warehouse_name -> stock.warehouse (not on product)
        # price_group_* -> product.pricelist / pricelist item
        # replenishment_method -> route_ids / buy vs manufacture
        # parent_guid / parent_name -> product hierarchy (not standard)
        # additional_attributes -> product.attribute / product.template.attribute.line
        # changed_at -> write_date is system-managed; do not overwrite

        return values

    def _log_success(self, item, product, status):
        self.env["integration.log"].sudo().create({
            "external_id": item.get("guid"),
            "object_type": "product",
            "status": "success",
            "odoo_id": product.id if product else False,
            "description": (
                product.name if product else item.get("name")
            ),
            "message": status,
        })

    def _log_error(self, item, error):
        self.env["integration.log"].sudo().create({
            "external_id": item.get("guid"),
            "object_type": "product",
            "status": "error",
            "description": item.get("name"),
            "message": str(error),
        })
