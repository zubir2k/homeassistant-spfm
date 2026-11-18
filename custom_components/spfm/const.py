"""Constants for the SPFM integration."""

from datetime import timedelta

DOMAIN = "spfm"
VERSION = "0.9.4"  # keep in sync with manifest.json (cache-busts the card)
PLATFORMS = ["calendar", "sensor"]

CONF_UNITS = "units"
CONF_ACCOUNT_ID = "account_id"

# Hourly: announcements should surface reasonably quickly; each cycle is only
# three small GETs per unit.
DEFAULT_POLL_INTERVAL = timedelta(hours=1)

EVENT_NEW_ANNOUNCEMENT = "spfm_new_announcement"
EVENT_NOTIFICATION = "spfm_notification"
EVENT_NEW_BILL = "spfm_new_bill"

# The portal page with the Pay button (payment is a signed iPay88 POST, so no deep link).
PAY_URL = "https://spfm.com.my/prod/selfcare/bill-and-receipt/outstanding"
EVENT_VISITOR_PENDING = "spfm_visitor_pending"
EVENT_VISITOR_ARRIVED = "spfm_visitor_arrived"
EVENT_VISITOR_DEPARTED = "spfm_visitor_departed"

# Notifications and visitors: what the app pushes. Three tiny GETs per unit.
ACTIVITY_POLL_INTERVAL = timedelta(minutes=2)

DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_BASE_DELAY = 1.0
DEFAULT_RETRY_BACKOFF_FACTOR = 2

MANUFACTURER = "Sunway Property Facility Management"
MODEL = "SPFM Selfcare unit"
CURRENCY_RM = "MYR"
