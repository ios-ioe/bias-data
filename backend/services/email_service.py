"""Sends team access-code emails via Resend (https://resend.com).

Uses Resend's plain HTTPS REST API rather than SMTP. This matters because the
backend is hosted on a Hugging Face Space, and HF Spaces containers commonly
block outbound SMTP ports (25/465/587) at the network level -- Gmail SMTP can
hang or silently fail there with no clear error. A plain HTTPS POST is not
affected by that restriction.

Configuration (env vars):
  RESEND_API_KEY   - required to actually send. If unset, emails are skipped
                      and logged, but team creation still succeeds -- the
                      organizer can always copy the access code manually from
                      the admin Teams tab as a fallback.
  RESEND_FROM      - "from" address, e.g. "Bias Data Event <onboarding@yourdomain.com>".
                      Defaults to Resend's shared sandbox sender, which only
                      delivers to the Resend account owner's own verified
                      email -- fine for local testing, NOT for the real event.
                      Verify your own sending domain in Resend before the
                      event and set this to an address on that domain.
"""

import logging
from typing import Iterable

import httpx

from config import RESEND_API_KEY, RESEND_FROM

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def _build_email(team_name: str, access_code: str) -> tuple[str, str]:
    subject = f"Your access code for {team_name} -- Bias Data Collection Event"
    body = (
        f"Hi {team_name},\n\n"
        f"Your team's access code for the bias data collection tool is:\n\n"
        f"    {access_code}\n\n"
        f"Every member of the team can use this same code to log in on the "
        f"submission page. Keep it private to your team -- do not share it "
        f"with other teams.\n\n"
        f"Good luck!\n"
    )
    return subject, body


def send_team_access_code(
    team_name: str, access_code: str, member_emails: Iterable[str]
) -> bool:
    """Send the access code to every member email. Returns True only if the
    email was actually dispatched (i.e. RESEND_API_KEY is configured and the
    API call succeeded). Never raises -- a failed or skipped send should not
    block team creation, since the organizer can always copy the code
    manually from the admin Teams tab.
    """
    recipients = list(member_emails)
    if not recipients:
        return False

    if not RESEND_API_KEY:
        logger.warning(
            "RESEND_API_KEY not set -- skipping email for team '%s'. "
            "Copy the access code from the admin Teams tab and send it manually.",
            team_name,
        )
        return False

    subject, body = _build_email(team_name, access_code)

    try:
        response = httpx.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": RESEND_FROM,
                "to": recipients,
                "subject": subject,
                "text": body,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        logger.info("Sent access code email for team '%s' to %d recipient(s)", team_name, len(recipients))
        return True
    except httpx.HTTPError as exc:
        logger.error("Failed to send access code email for team '%s': %s", team_name, exc)
        return False
