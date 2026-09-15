"""Pipeline-parking constants shared by the sheet importer and the legacy
EnquiryLoader, so no loader imports a management command (BUG-030 §21)."""

from __future__ import annotations

from reservations.enums import EnquiryLostReason, EnquiryStatus, LeadStatus

#: Historic rows have no outcome column; park them out of the live pipeline.
HISTORIC_STATUS = EnquiryStatus.DEAD
HISTORIC_LOST_REASON = EnquiryLostReason.UNKNOWN
HISTORIC_LEAD_STATUS = LeadStatus.COLD

#: A legacy enquiry older than this many days before the dump's newest
#: enquiry, with no quotation, is a stale lead and is parked like a historic
#: sheet row. Relative to the dump, not the wall clock, so a load is
#: deterministic per dump.
STALE_ENQUIRY_DAYS = 90
