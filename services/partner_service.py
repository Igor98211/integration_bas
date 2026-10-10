from odoo import _
from odoo.exceptions import ValidationError

""" 
TODO решить с auth="public" и убрать sudo()"""


class PartnerService:

    def __init__(self, env):
        self.env = env

    def import_partners(self, data):
        results = []
        success = True

        for item in data.get("partners", []):
            try:
                external_id = item.get("guid")

                if not external_id:
                    raise ValidationError(
                        _("Partner guid is required.")
                    )

                partner = self._find_partner(item)

                # Do not create a partner marked for deletion.
                if item.get("deleted") or item.get("deletion_mark"):
                    if partner:
                        partner.write({"active": False})
                        status = "archived"
                    else:
                        status = "skipped_deleted"

                else:
                    values = self._prepare_values(item)

                    if partner:
                        partner.write(values)
                        status = "updated"
                    else:
                        partner = (
                            self.env["res.partner"]
                            .sudo()
                            .create(values)
                        )
                        status = "created"

                self._log_success(item, partner, status)

                results.append({
                    "external_id": external_id,
                    "odoo_id": partner.id if partner else None,
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

    def _find_partner(self, item):
        external_id = item.get("guid")

        return (
            self.env["res.partner"]
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
                or _("Unnamed partner")
            ),
            "x_bas_id": item.get("guid"),
            "active": True,
        }

        # BAS partner code -> Odoo reference.
        if item.get("code"):
            values["ref"] = item["code"]

        # Map individual/company type when BAS provides
        # a recognized value.
        partner_kind = (item.get("partner_kind") or "").strip().lower()

        if partner_kind in ("company", "organization", "legal_entity"):
            values["company_type"] = "company"
        elif partner_kind in ("person", "individual", "individual entrepreneur"):
            values["company_type"] = "person"

        # Tax identifier.
        # Prefer EDРPOU when present; otherwise use tax_id.
        tax_id = item.get("edrpou") or item.get("tax_id")

        if tax_id and tax_id.strip():
            values["vat"] = tax_id.strip()

        # Optional comment.
        if item.get("comment") and item["comment"].strip():
            values["comment"] = item["comment"].strip()

        # Extract the first available phone and email.
        contacts = item.get("contact_information") or []

        phone = self._get_contact_value(contacts, "phone")
        email = self._get_contact_value(contacts, "email")

        # Do not overwrite existing values with empty data.
        if phone:
            values["phone"] = phone

        if email:
            values["email"] = email
            
        values["x_bas_full_name"] = item.get("full_name")

        return values

    def _get_contact_value(self, contacts, contact_type):
        for contact in contacts:
            if contact.get("type") != contact_type:
                continue

            value = (
                contact.get(contact_type)
                or contact.get("presentation")
            )

            if value and value.strip():
                return value.strip()

        return False

    def _log_success(self, item, partner, status):
        self.env["integration.log"].sudo().create({
            "external_id": item.get("guid"),
            "object_type": "partner",
            "status": "success",
            "odoo_id": partner.id if partner else False,
            "description": (
                partner.name if partner else item.get("name")
            ),
            "message": status,
        })

    def _log_error(self, item, error):
        self.env["integration.log"].sudo().create({
            "external_id": item.get("guid"),
            "object_type": "partner",
            "status": "error",
            "description": item.get("name"),
            "message": str(error),
        })


