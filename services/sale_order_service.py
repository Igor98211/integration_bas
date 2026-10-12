from odoo import Command, _
from odoo.exceptions import ValidationError


class SaleOrderService:

    def __init__(self, env):
        self.env = env

    def import_sale_orders(self, data):
        """Import sale orders. On missing partner/product (or any item
        error) stop the whole batch, log the error and return it.
        """
        results = []

        for item in data.get("sale_orders", []):
            try:
                external_id = item.get("guid")

                if not external_id:
                    raise ValidationError(_("Sale order guid is required."))

                order = self._find_order(item)

                if item.get("deleted") or item.get("deletion_mark"):
                    if order:
                        # No active flag on SO — cancel whatever state it is in.
                        if order.state != "cancel":
                            if order.locked:
                                order.action_unlock()
                            order.action_cancel()
                        status = "cancelled"
                    else:
                        status = "skipped_deleted"
                else:
                    partner = self._find_partner(item)
                    line_commands = self._prepare_lines(item)

                    values = self._prepare_values(item, partner)
                    values["order_line"] = (
                        [Command.clear()] + line_commands
                        if order
                        else line_commands
                    )

                    if order:
                        # Line replace needs draft: cancel/unlock then reopen.
                        order = self._ensure_draft_for_update(order)
                        order.write(values)
                        status = "updated"
                    else:
                        order = (
                            self.env["sale.order"]
                            .sudo()
                            .create(values)
                        )
                        status = "created"

                    # BAS posted=True -> Odoo confirmed (state=sale).
                    # posted=False stays / returns to draft.
                    status = self._apply_posted_state(order, item, status)

                self._log_success(item, order, status)

                results.append({
                    "external_id": external_id,
                    "odoo_id": order.id if order else None,
                    "status": status,
                })

            except Exception as error:
                self._log_error(item, error)
                return {
                    "success": False,
                    "error": str(error),
                    "results": results,
                }

        return {
            "success": True,
            "results": results,
        }

    def _find_order(self, item):
        return (
            self.env["sale.order"]
            .sudo()
            .search(
                [("x_bas_id", "=", item.get("guid"))],
                limit=1,
            )
        )

    def _find_partner(self, item):
        partner_guid = item.get("partner_guid")
        if not partner_guid:
            raise ValidationError(_(
                "Sale order %(number)s: partner_guid is required."
            ) % {"number": item.get("number") or item.get("guid")})

        partner = (
            self.env["res.partner"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [("x_bas_id", "=", partner_guid)],
                limit=1,
            )
        )
        if not partner:
            raise ValidationError(_(
                "Partner not found for partner_guid=%(guid)s "
                "(sale order %(number)s). Import partners first."
            ) % {
                "guid": partner_guid,
                "number": item.get("number") or item.get("guid"),
            })
        return partner

    def _find_product_variant(self, product_guid, order_number, line_number):
        if not product_guid:
            raise ValidationError(_(
                "Sale order %(number)s line %(line)s: product guid "
                "is required."
            ) % {
                "number": order_number,
                "line": line_number,
            })

        # BAS guid is stored on product.template; SO lines need variant.
        product = (
            self.env["product.product"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [("product_tmpl_id.x_bas_id", "=", product_guid)],
                limit=1,
            )
        )
        if not product:
            raise ValidationError(_(
                "Product not found for guid=%(guid)s "
                "(sale order %(number)s line %(line)s). "
                "Import products first."
            ) % {
                "guid": product_guid,
                "number": order_number,
                "line": line_number,
            })
        return product

    def _ensure_draft_for_update(self, order):
        """Bring an existing SO back to draft so lines can be replaced."""
        if order.state == "draft":
            return order
        if order.locked:
            order.action_unlock()
        if order.state == "sale":
            order.action_cancel()
        if order.state == "cancel":
            order.action_draft()
        if order.state == "sent":
            # sent is editable enough for write + optional confirm
            return order
        if order.state not in ("draft", "sent"):
            raise ValidationError(_(
                "Sale order %(name)s is in state '%(state)s' and cannot "
                "be updated from BAS."
            ) % {"name": order.name, "state": order.state})
        return order

    def _bas_date_order(self, item):
        if not item.get("date"):
            return False
        # ISO datetime from BAS, e.g. 2024-08-29T16:58:45
        return item["date"].replace("T", " ")

    def _apply_posted_state(self, order, item, status):
        """Map BAS posted flag to Odoo sale.order state.

        posted=True  -> action_confirm() (state=sale)
        posted=False -> leave / return to draft
        """
        posted = bool(item.get("posted"))
        bas_date = self._bas_date_order(item)

        if posted:
            if order.state in ("draft", "sent"):
                order.action_confirm()
                # action_confirm() sets date_order=now; restore BAS date.
                if bas_date:
                    order.write({"date_order": bas_date})
                return f"{status}_confirmed"
            return status

        # Unposted in BAS: if we had confirmed earlier, reopen as draft.
        if order.state == "sale":
            if order.locked:
                order.action_unlock()
            order.action_cancel()
            order.action_draft()
            if bas_date:
                order.write({"date_order": bas_date})
            return f"{status}_draft"
        return status

    def _prepare_values(self, item, partner):
        values = {
            "partner_id": partner.id,
            "x_bas_id": item.get("guid"),
        }

        # BAS document number -> customer reference (not Odoo sequence name).
        if item.get("number"):
            values["client_order_ref"] = item["number"]

        bas_date = self._bas_date_order(item)
        if bas_date:
            values["date_order"] = bas_date

        if item.get("comment") and str(item["comment"]).strip():
            values["note"] = str(item["comment"]).strip()

        # --- Not loaded yet (left for later mapping) ---
        # organization_guid / organization_name -> res.company (company_id)
        #   For a single-company DB, env.company is enough.
        # currency_guid / currency_code / currency_name -> res.currency
        #   via pricelist_id (currency_id on SO is computed).
        #   ISO 980 = UAH (base.UAH).
        # contract_guid / contract_name -> no standard Odoo model
        # order_state_guid / order_state_name -> finer state than posted
        #   (Завершений / Повернення etc. — need explicit mapping)
        # responsible_guid / responsible_name -> res.users (user_id)
        # structural_unit_guid / structural_unit_name
        #   -> stock.warehouse / analytic account (unclear)
        # shipment_date -> commitment_date
        # vat_included -> tax mapping / fiscal position
        # amount -> informational; Odoo computes amounts
        # additional_attributes -> custom fields later
        # lines[].characteristic_* -> product variant attributes
        # lines[].reserve -> stock reservation (sale_stock)
        # lines[].unit_* -> product_uom_id
        # lines[].vat_* -> tax_ids
        # lines[].discount_amount -> only discount % is mapped
        # lines[].content -> line name override
        # lines[].shipment_date -> line commitment / delivery

        return values

    def _prepare_lines(self, item):
        order_number = item.get("number") or item.get("guid")
        commands = []

        for line in item.get("lines") or []:
            line_number = line.get("line_number")
            product = self._find_product_variant(
                line.get("product"),
                order_number,
                line_number,
            )

            line_vals = {
                "product_id": product.id,
                "product_uom_qty": line.get("quantity") or 0.0,
                "price_unit": line.get("price") or 0.0,
            }

            discount = line.get("discount_percent")
            if discount:
                line_vals["discount"] = discount

            # if line.get("content") and str(line["content"]).strip():
            #     line_vals["name"] = str(line["content"]).strip()

            commands.append(Command.create(line_vals))

        return commands

    def _log_success(self, item, order, status):
        self.env["integration.log"].sudo().create({
            "external_id": item.get("guid"),
            "object_type": "sale_order",
            "status": "success",
            "odoo_id": order.id if order else False,
            "description": (
                (order.client_order_ref or order.name)
                if order
                else item.get("number")
            ),
            "message": status,
        })

    def _log_error(self, item, error):
        self.env["integration.log"].sudo().create({
            "external_id": item.get("guid"),
            "object_type": "sale_order",
            "status": "error",
            "description": item.get("number"),
            "message": str(error),
        })
