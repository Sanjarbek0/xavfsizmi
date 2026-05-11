"""Email delivery — abstract sender plus SMTP and in-memory implementations.

The application code only ever depends on :class:`EmailSender`. Tests substitute
the in-memory :class:`InMemoryEmailSender` so they can assert on the captured
messages without touching SMTP.
"""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from ..config import Settings, get_settings
from ..core.i18n import Locale


@dataclass(slots=True)
class EmailMessageSpec:
    to: str
    subject: str
    text: str
    html: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class EmailSender(Protocol):
    async def send(self, msg: EmailMessageSpec) -> None: ...


class InMemoryEmailSender:
    """Test/dev sender that records every outbound message."""

    def __init__(self) -> None:
        self.outbox: list[EmailMessageSpec] = []

    async def send(self, msg: EmailMessageSpec) -> None:
        self.outbox.append(msg)

    def reset(self) -> None:
        self.outbox.clear()

    def latest_to(self, recipient: str) -> EmailMessageSpec | None:
        for entry in reversed(self.outbox):
            if entry.to.lower() == recipient.lower():
                return entry
        return None


class SMTPEmailSender:
    """Synchronous SMTP sender wrapped in a thread for the FastAPI event loop.

    SMTP is slow and blocking, but auth/verification flows are not on the hot
    path, so we keep the implementation simple and run it in a worker thread.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, msg: EmailMessageSpec) -> None:
        import anyio

        await anyio.to_thread.run_sync(self._send_sync, msg)

    def _send_sync(self, msg: EmailMessageSpec) -> None:
        s = self._settings
        message = EmailMessage()
        message["From"] = s.smtp_from
        message["To"] = msg.to
        message["Subject"] = msg.subject
        for k, v in msg.headers.items():
            message[k] = v
        message.set_content(msg.text)
        if msg.html:
            message.add_alternative(msg.html, subtype="html")

        if s.smtp_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(s.smtp_host, s.smtp_port) as smtp:
                smtp.starttls(context=context)
                if s.smtp_username:
                    smtp.login(s.smtp_username, s.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(s.smtp_host, s.smtp_port) as smtp:
                if s.smtp_username:
                    smtp.login(s.smtp_username, s.smtp_password)
                smtp.send_message(message)


_DEFAULT_SENDER: EmailSender | None = None


def get_email_sender() -> EmailSender:
    """Return a process-wide :class:`EmailSender` for production code paths.

    Tests override this dependency; routers import it through ``deps``.
    """
    global _DEFAULT_SENDER
    if _DEFAULT_SENDER is None:
        _DEFAULT_SENDER = SMTPEmailSender(get_settings())
    return _DEFAULT_SENDER


def reset_email_sender() -> None:
    global _DEFAULT_SENDER
    _DEFAULT_SENDER = None


# Translated subjects + bodies for transactional messages. Each template renders
# to a (subject, text, html) triple. Keep wording short and instruction-led.
def render_magic_link_email(*, link: str, locale: Locale) -> tuple[str, str, str]:
    bundles = {
        "uz": (
            "Xavfsizmi — kirish havolasi",
            (
                "Salom!\n\n"
                "Xavfsizmi hisobingizga kirish uchun quyidagi havolaga o'ting:\n"
                f"{link}\n\n"
                "Havola 15 daqiqa amal qiladi va faqat bir marta ishlaydi.\n"
                "Agar bu so'rov sizdan bo'lmasa, xabarni e'tiborsiz qoldiring."
            ),
            (
                "<p>Salom!</p>"
                "<p>Xavfsizmi hisobingizga kirish uchun quyidagi tugmani bosing:</p>"
                f'<p><a href="{link}" style="background:#0d1f2d;color:#fff;'
                "padding:12px 20px;text-decoration:none;border-radius:6px;"
                'display:inline-block">Hisobga kirish</a></p>'
                f'<p>Yoki havolani brauzerda oching: <a href="{link}">{link}</a></p>'
                "<p>Havola 15 daqiqa amal qiladi va faqat bir marta ishlaydi.</p>"
                "<p style='color:#666;font-size:12px'>Agar bu so'rov sizdan bo'lmasa, "
                "xabarni e'tiborsiz qoldiring.</p>"
            ),
        ),
        "ru": (
            "Xavfsizmi — ссылка для входа",
            (
                "Здравствуйте!\n\n"
                "Чтобы войти в учётную запись Xavfsizmi, перейдите по ссылке:\n"
                f"{link}\n\n"
                "Ссылка действительна 15 минут и сработает только один раз.\n"
                "Если вы не запрашивали вход — просто проигнорируйте письмо."
            ),
            (
                "<p>Здравствуйте!</p>"
                "<p>Нажмите кнопку ниже, чтобы войти в учётную запись Xavfsizmi:</p>"
                f'<p><a href="{link}" style="background:#0d1f2d;color:#fff;'
                "padding:12px 20px;text-decoration:none;border-radius:6px;"
                'display:inline-block">Войти в аккаунт</a></p>'
                f'<p>Или откройте ссылку в браузере: <a href="{link}">{link}</a></p>'
                "<p>Ссылка действительна 15 минут и сработает только один раз.</p>"
                "<p style='color:#666;font-size:12px'>Если вы не запрашивали вход — "
                "просто проигнорируйте письмо.</p>"
            ),
        ),
        "en": (
            "Xavfsizmi — sign-in link",
            (
                "Hi there,\n\n"
                "Click the link below to sign in to your Xavfsizmi account:\n"
                f"{link}\n\n"
                "The link expires in 15 minutes and works only once.\n"
                "If you didn't request this, you can safely ignore the email."
            ),
            (
                "<p>Hi there,</p>"
                "<p>Click the button below to sign in to your Xavfsizmi account:</p>"
                f'<p><a href="{link}" style="background:#0d1f2d;color:#fff;'
                "padding:12px 20px;text-decoration:none;border-radius:6px;"
                'display:inline-block">Sign in</a></p>'
                f'<p>Or open the link in your browser: <a href="{link}">{link}</a></p>'
                "<p>The link expires in 15 minutes and works only once.</p>"
                "<p style='color:#666;font-size:12px'>If you didn't request this, "
                "you can safely ignore the email.</p>"
            ),
        ),
    }
    return bundles[locale]


def render_notification_confirm_email(
    *, confirm_link: str, unsubscribe_link: str, locale: Locale
) -> tuple[str, str, str]:
    bundles = {
        "uz": (
            "Xavfsizmi — obunani tasdiqlang",
            (
                "Salom!\n\n"
                "Xavfsizmi yangi sızıntılar haqida bildirishnomalarga obuna bo'lganingiz uchun rahmat.\n"
                f"Obunani tasdiqlash uchun havolaga o'ting:\n{confirm_link}\n\n"
                f"Obunani bekor qilish: {unsubscribe_link}"
            ),
            (
                "<p>Salom!</p>"
                "<p>Xavfsizmi yangi sızıntılar haqida bildirishnomalarga obuna bo'lganingiz uchun rahmat.</p>"
                f'<p><a href="{confirm_link}" style="background:#0d1f2d;color:#fff;'
                'padding:12px 20px;text-decoration:none;border-radius:6px;display:inline-block">Obunani tasdiqlash</a></p>'
                f'<p>Yoki havolani brauzerda oching: <a href="{confirm_link}">{confirm_link}</a></p>'
                f'<p style="color:#666;font-size:12px">Obunani bekor qilish: <a href="{unsubscribe_link}">bu yerda</a>.</p>'
            ),
        ),
        "ru": (
            "Xavfsizmi — подтвердите подписку",
            (
                "Здравствуйте!\n\n"
                "Спасибо за подписку на уведомления Xavfsizmi о новых утечках.\n"
                f"Подтвердите подписку: {confirm_link}\n\n"
                f"Отписаться: {unsubscribe_link}"
            ),
            (
                "<p>Здравствуйте!</p>"
                "<p>Спасибо за подписку на уведомления Xavfsizmi о новых утечках.</p>"
                f'<p><a href="{confirm_link}" style="background:#0d1f2d;color:#fff;'
                'padding:12px 20px;text-decoration:none;border-radius:6px;display:inline-block">Подтвердить подписку</a></p>'
                f'<p>Или откройте ссылку в браузере: <a href="{confirm_link}">{confirm_link}</a></p>'
                f'<p style="color:#666;font-size:12px">Отписаться: <a href="{unsubscribe_link}">здесь</a>.</p>'
            ),
        ),
        "en": (
            "Xavfsizmi — confirm your subscription",
            (
                "Hi!\n\n"
                "Thanks for subscribing to Xavfsizmi breach notifications.\n"
                f"Please confirm your subscription: {confirm_link}\n\n"
                f"Unsubscribe: {unsubscribe_link}"
            ),
            (
                "<p>Hi!</p>"
                "<p>Thanks for subscribing to Xavfsizmi breach notifications.</p>"
                f'<p><a href="{confirm_link}" style="background:#0d1f2d;color:#fff;'
                'padding:12px 20px;text-decoration:none;border-radius:6px;display:inline-block">Confirm subscription</a></p>'
                f'<p>Or open the link in your browser: <a href="{confirm_link}">{confirm_link}</a></p>'
                f'<p style="color:#666;font-size:12px">Unsubscribe: <a href="{unsubscribe_link}">here</a>.</p>'
            ),
        ),
    }
    return bundles[locale]


def render_breach_notification_email(
    *, breach_title: str, breach_date: str | None, unsubscribe_link: str, locale: Locale
) -> tuple[str, str, str]:
    when = breach_date or "?"
    bundles = {
        "uz": (
            f"Xavfsizmi — yangi sızıntı: {breach_title}",
            (
                f"Salom!\n\n{breach_title} ({when}) sızıntısida sizning email manzilingiz topildi.\n"
                "Tegishli parollarni almashtiring va imkon bo'lsa ikki bosqichli autentifikatsiyani yoqing.\n\n"
                f"Obunani bekor qilish: {unsubscribe_link}"
            ),
            (
                "<p>Salom!</p>"
                f"<p><strong>{breach_title}</strong> ({when}) sızıntısida sizning email manzilingiz topildi.</p>"
                "<p>Tegishli parollarni almashtiring va imkon bo'lsa ikki bosqichli autentifikatsiyani yoqing.</p>"
                f'<p style="color:#666;font-size:12px">Obunani bekor qilish: <a href="{unsubscribe_link}">bu yerda</a>.</p>'
            ),
        ),
        "ru": (
            f"Xavfsizmi — новая утечка: {breach_title}",
            (
                f"Здравствуйте!\n\nВ утечке {breach_title} ({when}) обнаружен ваш адрес.\n"
                "Смените пароли и включите двухфакторную аутентификацию там, где это возможно.\n\n"
                f"Отписаться: {unsubscribe_link}"
            ),
            (
                "<p>Здравствуйте!</p>"
                f"<p>В утечке <strong>{breach_title}</strong> ({when}) обнаружен ваш адрес.</p>"
                "<p>Смените пароли и включите 2FA там, где это возможно.</p>"
                f'<p style="color:#666;font-size:12px">Отписаться: <a href="{unsubscribe_link}">здесь</a>.</p>'
            ),
        ),
        "en": (
            f"Xavfsizmi — new breach: {breach_title}",
            (
                f"Hi!\n\nYour email address appeared in the {breach_title} breach ({when}).\n"
                "Change any reused passwords and enable 2FA where possible.\n\n"
                f"Unsubscribe: {unsubscribe_link}"
            ),
            (
                "<p>Hi!</p>"
                f"<p>Your email address appeared in the <strong>{breach_title}</strong> breach ({when}).</p>"
                "<p>Change any reused passwords and enable 2FA where possible.</p>"
                f'<p style="color:#666;font-size:12px">Unsubscribe: <a href="{unsubscribe_link}">here</a>.</p>'
            ),
        ),
    }
    return bundles[locale]


def render_domain_verification_email(
    *, domain: str, token: str, locale: Locale
) -> tuple[str, str, str]:
    bundles = {
        "uz": (
            f"Xavfsizmi — {domain} domenini tasdiqlash",
            (
                f"Salom! {domain} domeniga egalik huquqingizni tasdiqlash uchun\n"
                f"quyidagi tasdiqlash kodidan foydalaning:\n\n{token}\n\n"
                "Kodni Xavfsizmi panelidagi domen sahifasiga kiriting yoki uni\n"
                "DNS TXT yozuvi sifatida joylashtiring."
            ),
            (
                f"<p>Salom! <strong>{domain}</strong> domeniga egalik huquqingizni "
                "tasdiqlash uchun quyidagi kodni Xavfsizmi panelidagi domen sahifasiga "
                "kiriting yoki uni DNS TXT yozuvi sifatida joylashtiring:</p>"
                f"<p style='font-family:monospace;background:#f3f4f6;padding:8px 12px;"
                f"border-radius:6px;display:inline-block'>{token}</p>"
            ),
        ),
        "ru": (
            f"Xavfsizmi — подтверждение домена {domain}",
            (
                f"Здравствуйте! Чтобы подтвердить владение доменом {domain},\n"
                f"используйте следующий код:\n\n{token}\n\n"
                "Введите его в панели Xavfsizmi или добавьте как DNS TXT-запись."
            ),
            (
                f"<p>Здравствуйте! Чтобы подтвердить владение доменом "
                f"<strong>{domain}</strong>, используйте код ниже — введите его в "
                "панели Xavfsizmi или добавьте как DNS TXT-запись:</p>"
                f"<p style='font-family:monospace;background:#f3f4f6;padding:8px 12px;"
                f"border-radius:6px;display:inline-block'>{token}</p>"
            ),
        ),
        "en": (
            f"Xavfsizmi — verify {domain}",
            (
                f"Hi! To prove ownership of {domain}, use the verification code below:\n\n"
                f"{token}\n\n"
                "Enter it in the Xavfsizmi domain page or publish it as a DNS TXT record."
            ),
            (
                f"<p>Hi! To prove ownership of <strong>{domain}</strong>, use the "
                "verification code below — enter it in the Xavfsizmi domain page or "
                "publish it as a DNS TXT record:</p>"
                f"<p style='font-family:monospace;background:#f3f4f6;padding:8px 12px;"
                f"border-radius:6px;display:inline-block'>{token}</p>"
            ),
        ),
    }
    return bundles[locale]
