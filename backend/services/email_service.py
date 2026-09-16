import logging
import os
from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "no-reply@auroratio.com")
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "AuroRatio")
CONTACT_TO_EMAIL = os.getenv("CONTACT_TO_EMAIL", "support@auroratio.com")

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
PARIS_TIMEZONE = ZoneInfo("Europe/Paris")


def _brevo_enabled() -> bool:
    return bool(BREVO_API_KEY)


def _normalize_datetime(value: object) -> datetime | None:
    """Normalize supported datetime inputs to an aware UTC datetime."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            logger.warning("Could not parse invitation expiry value")
            return None
    else:
        return None

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _format_invite_expiry(value: object, *, locale: str) -> str:
    """Return a customer-facing invite expiry in Europe/Paris."""
    expiry = _normalize_datetime(value)
    if expiry is None:
        return ""

    paris_expiry = expiry.astimezone(PARIS_TIMEZONE)
    timezone_name = paris_expiry.tzname() or "Europe/Paris"

    if locale == "fr":
        return f"{paris_expiry.strftime('%d/%m/%Y à %H:%M')} ({timezone_name})"

    return f"{paris_expiry.strftime('%B %d, %Y at %H:%M')} ({timezone_name})"


async def send_email(
    *,
    to_email: str,
    subject: str,
    html_content: str,
    to_name: str | None = None,
) -> bool:
    if not _brevo_enabled():
        logger.warning("BREVO_API_KEY is not configured. Transactional email not sent")
        return False

    payload = {
        "sender": {
            "name": BREVO_SENDER_NAME,
            "email": BREVO_SENDER_EMAIL,
        },
        "to": [
            {
                "email": to_email,
                "name": to_name or to_email,
            }
        ],
        "subject": subject,
        "htmlContent": html_content,
    }

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                BREVO_API_URL,
                json=payload,
                headers=headers,
            )
    except httpx.HTTPError:
        logger.exception("Brevo transactional email request failed")
        return False

    if not 200 <= response.status_code < 300:
        logger.error(
            "Brevo transactional email failed with status %s",
            response.status_code,
        )
        return False

    return True


async def send_billing_management_link(
    *,
    to_email: str,
    portal_link: str,
    locale: str,
) -> bool:
    label = "Abonnement AuroRatio" if locale == "fr" else "AuroRatio subscription"
    return await send_billing_management_links(
        to_email=to_email,
        links=[{"label": label, "url": portal_link}],
        locale=locale,
    )


async def send_billing_management_links(
    *,
    to_email: str,
    links: list[dict[str, str]],
    locale: str,
) -> bool:
    if not links:
        return False

    safe_links = [
        {
            "label": escape(link["label"]),
            "url": escape(link["url"], quote=True),
        }
        for link in links
    ]

    link_rows = "".join(
        f"""
        <li style="margin:0 0 18px">
          <div style="margin-bottom:8px">{link["label"]}</div>
          <a href="{link["url"]}" style="display:inline-block;background:#C9A84C;color:#0A0A08;padding:12px 18px;text-decoration:none;border-radius:6px;font-weight:bold">
            {"Ouvrir la gestion de facturation" if locale == "fr" else "Open billing management"}
          </a>
        </li>
        """
        for link in safe_links
    )

    if locale == "fr":
        subject = "Votre lien sécurisé de gestion de facturation AuroRatio"
        html_content = f"""
        <div style="font-family:Arial,sans-serif;line-height:1.6">
          <h2>Gérez votre facturation AuroRatio</h2>
          <p>Chaque lien ci-dessous ouvre la gestion sécurisée de la relation de facturation indiquée.</p>
          <ul style="list-style:none;padding:0">{link_rows}</ul>
          <p>Chaque lien expire rapidement et ne peut être utilisé qu’une seule fois.</p>
          <p>Si vous n’avez pas demandé ces liens, vous pouvez ignorer cet email.</p>
        </div>
        """
    else:
        subject = "Your secure AuroRatio billing-management link"
        html_content = f"""
        <div style="font-family:Arial,sans-serif;line-height:1.6">
          <h2>Manage your AuroRatio billing</h2>
          <p>Each link below opens secure billing management for the relationship shown.</p>
          <ul style="list-style:none;padding:0">{link_rows}</ul>
          <p>Each link expires shortly and can be used only once.</p>
          <p>If you did not request these links, you can ignore this email.</p>
        </div>
        """

    return await send_email(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
    )


async def send_private_access_instructions(
    *,
    to_email: str,
    invitations: list[dict],
    locale: str,
) -> bool:
    """Deliver private-channel access instructions with explicit expiry details."""
    if not invitations:
        return False

    rows = ""
    for invitation in invitations:
        label = escape(str(invitation["label"]))
        invite_url = escape(str(invitation["url"]), quote=True)
        raw_expiry = invitation.get("expires_at")
        expires_text = _format_invite_expiry(raw_expiry, locale=locale)

        logger.info(
            "Preparing private-access invitation email: expiry_present=%s expiry_rendered=%s",
            raw_expiry is not None,
            bool(expires_text),
        )

        if locale == "fr":
            button = "Ouvrir l’invitation sécurisée"
            expiry_copy = (
                f'<div style="color:#6b675d;font-size:13px;margin:0 0 10px">'
                f'<strong>Valable jusqu’au :</strong> {escape(expires_text)}</div>'
                if expires_text
                else
                '<div style="color:#6b675d;font-size:13px;margin:0 0 10px">'
                '<strong>Validité :</strong> 24 heures à compter de la création de l’invitation.</div>'
            )
        else:
            button = "Open secure invitation"
            expiry_copy = (
                f'<div style="color:#6b675d;font-size:13px;margin:0 0 10px">'
                f'<strong>Valid until:</strong> {escape(expires_text)}</div>'
                if expires_text
                else
                '<div style="color:#6b675d;font-size:13px;margin:0 0 10px">'
                '<strong>Validity:</strong> 24 hours from invitation creation.</div>'
            )

        rows += f"""
        <li style="margin:0 0 22px">
          <div style="margin-bottom:8px;font-weight:bold">{label}</div>
          {expiry_copy}
          <a href="{invite_url}" style="display:inline-block;background:#C9A84C;color:#0A0A08;padding:12px 18px;text-decoration:none;border-radius:6px;font-weight:bold">
            {button}
          </a>
        </li>
        """

    if locale == "fr":
        subject = "Votre accès privé AuroRatio est prêt"
        html_content = f"""
        <div style="font-family:Arial,sans-serif;line-height:1.6">
          <h2>Votre accès privé est prêt</h2>
          <p>Votre abonnement est actif. Utilisez l’invitation sécurisée ci-dessous pour rejoindre le canal privé AuroRatio.</p>
          <ul style="list-style:none;padding:0">{rows}</ul>
          <p>Chaque invitation est personnelle, ne peut être utilisée qu’une seule fois et expire après 24 heures.</p>
          <p>AuroRatio fournit des signaux et des informations de marché. Vous restez seul responsable de vos décisions et de toute opération effectuée auprès de votre courtier.</p>
          <p>Si votre invitation expire avant que vous ne l’utilisiez, contactez le support.</p>
        </div>
        """
    else:
        subject = "Your private AuroRatio access is ready"
        html_content = f"""
        <div style="font-family:Arial,sans-serif;line-height:1.6">
          <h2>Your private access is ready</h2>
          <p>Your subscription is active. Use the secure invitation below to join the private AuroRatio channel.</p>
          <ul style="list-style:none;padding:0">{rows}</ul>
          <p>Each invitation is personal, can be used only once, and expires after 24 hours.</p>
          <p>AuroRatio provides trading signals and market information. You remain solely responsible for your decisions and for any trades placed through your broker.</p>
          <p>If your invitation expires before you use it, contact support.</p>
        </div>
        """

    return await send_email(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
    )


async def send_email_verification_code(email: str, code: str) -> bool:
    safe_code = escape(code)
    return await send_email(
        to_email=email,
        subject="Your AuroRatio verification code",
        html_content=f"""
        <div style="font-family:Arial,sans-serif;line-height:1.6">
          <h2>Your AuroRatio verification code</h2>
          <p>Use this code to verify your email address:</p>
          <p style="font-size:28px;font-weight:bold;letter-spacing:4px">{safe_code}</p>
          <p>This code expires soon. If you did not request this, you can ignore this email.</p>
        </div>
        """,
    )


async def send_password_reset_email(email: str, reset_url: str) -> bool:
    safe_reset_url = escape(reset_url, quote=True)
    return await send_email(
        to_email=email,
        subject="Reset your AuroRatio password",
        html_content=f"""
        <div style="font-family:Arial,sans-serif;line-height:1.6">
          <h2>Reset your password</h2>
          <p>Click the button below to reset your AuroRatio password:</p>
          <p>
            <a href="{safe_reset_url}" style="background:#C9A84C;color:#0A0A08;padding:12px 18px;text-decoration:none;border-radius:6px;font-weight:bold">
              Reset password
            </a>
          </p>
          <p>If the button does not work, copy this link:</p>
          <p>{safe_reset_url}</p>
          <p>If you did not request this, you can ignore this email.</p>
        </div>
        """,
    )


async def send_contact_message(
    *,
    first_name: str,
    last_name: str,
    email: str,
    phone: str | None,
    description: str,
) -> bool:
    safe_first_name = escape(first_name)
    safe_last_name = escape(last_name)
    safe_email = escape(email)
    safe_phone = escape(phone) if phone else "Not provided"
    safe_description = escape(description).replace("\n", "<br>")

    return await send_email(
        to_email=CONTACT_TO_EMAIL,
        subject=f"New AuroRatio contact message from {safe_first_name} {safe_last_name}",
        html_content=f"""
        <div style="font-family:Arial,sans-serif;line-height:1.6">
          <h2>New contact message</h2>
          <p><strong>Name:</strong> {safe_first_name} {safe_last_name}</p>
          <p><strong>Email:</strong> {safe_email}</p>
          <p><strong>Phone:</strong> {safe_phone}</p>
          <p><strong>Description:</strong></p>
          <p>{safe_description}</p>
        </div>
        """,
    )
