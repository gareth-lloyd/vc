"""User + Contact loaders.

UserMaster: legacy password hashes are SQL Server bcrypt-with-salt; we do
NOT migrate them. New users get unusable passwords and will need a reset.
Per `01-accounts.md`: IsSystemAdmin=1 -> ADMIN, else RESERVATIONS.

VillaContact -> Contact (one-to-one). Then VillaContactEmail/VillaContactTele
fan out into ContactEmail/ContactPhone children. The new schema enforces
"at most one primary per contact" via a partial unique constraint, so we
demote any duplicate primaries on the second-and-later child rows.
"""

from __future__ import annotations

from typing import Any

from accounts.enums import ContactPreferredMethod, ContactStatus, EmailLabel, PhoneLabel
from accounts.models import Contact, ContactEmail, ContactPhone, User
from core.enums import StaffRole
from data_migration.base import BaseLoader


class UserLoader(BaseLoader):
    name = "user"
    target_model = User
    legacy_query = (
        "SELECT Id, Email, FirstName, LastName, IsSystemAdmin, IsActive, "
        "MobileNo, LoginAt, LoginIP "
        "FROM UserMaster WHERE DeletedAt IS NULL"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        email = (row.get("Email") or "").strip().lower()
        if not email or "@" not in email:
            return None
        return {
            "email": email,
            "first_name": (row.get("FirstName") or "").strip()[:150],
            "last_name": (row.get("LastName") or "").strip()[:150],
            "phone": (row.get("MobileNo") or "").strip()[:32],
            "role": StaffRole.ADMIN if row.get("IsSystemAdmin") else StaffRole.RESERVATIONS,
            "is_active": bool(row.get("IsActive")),
            "is_staff": True,
            "last_login": row.get("LoginAt"),
            "last_login_ip": row.get("LoginIP") or None,
        }


class ContactLoader(BaseLoader):
    name = "contact"
    target_model = Contact
    legacy_query = (
        "SELECT Id, Title, FirstName, LastName, Company, WebsiteUrl, Notes, "
        "PrefferedMethod, AddressLine1, AddressLine2, DeletedAt "
        "FROM VillaContact"
    )

    _method_map = {
        1: ContactPreferredMethod.EMAIL,
        2: ContactPreferredMethod.PHONE,
        3: ContactPreferredMethod.SMS,
    }

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        first = (row.get("FirstName") or "").strip()[:128]
        last = (row.get("LastName") or "").strip()[:128]
        if not (first or last):
            return None
        return {
            "title": (row.get("Title") or "").strip()[:16],
            "first_name": first or "(unknown)",
            "last_name": last or "(unknown)",
            "company": (row.get("Company") or "").strip()[:128],
            "website_url": (row.get("WebsiteUrl") or "").strip()[:200],
            "notes": (row.get("Notes") or "").strip(),
            "preferred_method": self._method_map.get(
                row.get("PrefferedMethod") or 0,
                ContactPreferredMethod.EMAIL,
            ),
            "address_line_1": (row.get("AddressLine1") or "").strip()[:255],
            "address_line_2": (row.get("AddressLine2") or "").strip()[:255],
            "status": (ContactStatus.INACTIVE if row.get("DeletedAt") else ContactStatus.ACTIVE),
        }


class ContactEmailLoader(BaseLoader):
    """VillaContactEmail -> ContactEmail. Demotes duplicate primaries."""

    name = "contact_email"
    target_model = ContactEmail
    legacy_query = "SELECT Id, ContactId, Email, IsPrimary FROM VillaContactEmail"

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        email = (row.get("Email") or "").strip().lower()
        if not email or "@" not in email:
            return None
        contact = Contact.objects.filter(legacy_id=str(row["ContactId"])).first()
        if contact is None:
            return None
        is_primary = bool(row.get("IsPrimary"))
        if is_primary and ContactEmail.objects.filter(contact=contact, is_primary=True).exists():
            is_primary = False
        # ContactEmail has unique(contact, email); if dup exists, treat as upsert
        # via legacy_id (BaseLoader handles that for us).
        return {
            "contact": contact,
            "email": email[:254],
            "is_primary": is_primary,
            "label": EmailLabel.PRIMARY if is_primary else EmailLabel.OTHER,
        }


class ContactPhoneLoader(BaseLoader):
    name = "contact_phone"
    target_model = ContactPhone
    legacy_query = "SELECT Id, ContactId, CountryCode, MobileNo, IsPrimary FROM VillaContactTele"

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        number = (row.get("MobileNo") or "").strip()
        if not number:
            return None
        contact = Contact.objects.filter(legacy_id=str(row["ContactId"])).first()
        if contact is None:
            return None
        cc = (row.get("CountryCode") or "").strip()
        full = (f"+{cc.lstrip('+')} {number}" if cc else number)[:32]
        is_primary = bool(row.get("IsPrimary"))
        if is_primary and ContactPhone.objects.filter(contact=contact, is_primary=True).exists():
            is_primary = False
        return {
            "contact": contact,
            "number": full,
            "is_primary": is_primary,
            "label": PhoneLabel.MOBILE,
        }
