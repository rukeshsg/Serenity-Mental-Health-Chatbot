"""
Notification delivery services for OTP email and emergency SMS alerts.
"""

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)


class DeliveryError(Exception):
    """Raised when a delivery provider fails or is not configured."""


@dataclass
class DeliveryResult:
    provider: str
    recipient_masked: str
    message_id: str | None = None


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    masked_local = f"{local[:2]}***" if local else "***"
    return f"{masked_local}@{domain}"


def _mask_phone(phone: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"



class SmsService:
    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_phone = os.getenv("TWILIO_FROM_PHONE", "")

    def _ensure_configured(self):
        if not self.account_sid or not self.auth_token or not self.from_phone:
            raise DeliveryError(
                "SMS delivery is not configured. Set TWILIO_ACCOUNT_SID, "
                "TWILIO_AUTH_TOKEN, and TWILIO_FROM_PHONE."
            )

    def send_emergency_support_message(self, recipient_phone: str, message_text: str) -> DeliveryResult:
        self._ensure_configured()
        try:
            from twilio.rest import Client
        except ImportError as exc:
            raise DeliveryError("Twilio SDK is not installed. Add 'twilio' to requirements.") from exc

        try:
            client = Client(self.account_sid, self.auth_token)
            message = client.messages.create(
                body=message_text,
                from_=self.from_phone,
                to=recipient_phone,
            )
        except Exception as exc:
            raise DeliveryError(f"SMS delivery failed: {exc}") from exc

        logger.info("Emergency SMS sent via Twilio to %s", _mask_phone(recipient_phone))
        return DeliveryResult(
            provider="twilio",
            recipient_masked=_mask_phone(recipient_phone),
            message_id=getattr(message, "sid", None),
        )


class NotificationService:

    def send_otp_email(self, recipient_email: str, otp: str, expiry_minutes: int):
        url = "https://api.brevo.com/v3/smtp/email"

        headers = {
            "accept": "application/json",
            "api-key": os.getenv("BREVO_API_KEY"),
            "content-type": "application/json"
        }

        data = {
            "sender": {
                "email": os.getenv("SENDER_EMAIL"),
                "name": "Serenity Team"
            },
            "to": [{"email": recipient_email}],
            "subject": "Serenity Verification Code",
            "htmlContent": f"""
            <html>
              <body style="margin: 0; padding: 24px; font-family: Arial, sans-serif; color: #2f2347; line-height: 1.7; background: #f7f3ff;">
                <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border: 1px solid #eadfff; border-radius: 18px; padding: 28px 32px; box-shadow: 0 12px 30px rgba(124, 77, 255, 0.08);">
                <p>Hello,</p>
                <p>Your One-Time Password (OTP) for verification is:</p>
                <p style="margin: 18px 0 20px; font-size: 32px; font-weight: 700; color: #7c4dff; letter-spacing: 3px;">{otp}</p>
                <p>
                  This code is valid for the next <strong>{expiry_minutes} minutes</strong>.
                  Please do not share this code with anyone for security reasons.
                </p>
                <p>
                  If you did not request this code, please ignore this email or contact support immediately.
                </p>
                <p>
                  Best regards,<br />
                  <strong>Serenity Team</strong><br />
                  Mental Wellness Assistant &#128156;
                </p>
                </div>
              </body>
            </html>
            """,
            "textContent": f"Your OTP is {otp}"
        
        }

        response = requests.post(url, json=data, headers=headers)

        if response.status_code not in [200, 201]:
            raise DeliveryError(f"Email failed: {response.text}")

        return DeliveryResult(
            provider="brevo",
            recipient_masked=_mask_email(recipient_email)
        )

notification_service = NotificationService()
