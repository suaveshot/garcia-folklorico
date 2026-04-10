import re
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, STUDIO_EMAIL, FROM_EMAIL
from services.events import publish_event

LOGO_URL = "https://garciafolklorico.com/images/logo.png"
SITE_URL = "https://garciafolklorico.com"
STUDIO_ADDRESS = "2012 Saviers Rd., Oxnard, CA 93033"
STUDIO_FULL = f"Garcia Folklorico Studio, {STUDIO_ADDRESS}"
MAPS_URL = "https://maps.google.com/?q=2012+Saviers+Rd+Oxnard+CA+93033"


# ── Send ─────────────────────────────────────────────────────────────

async def _send_email(to: str, subject: str, html_body: str,
                      plain_text: str | None = None,
                      ics_data: str | None = None):
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"[EMAIL SKIPPED] No SMTP credentials. Would send to {to}: {subject}")
        return

    msg = MIMEMultipart("mixed")
    msg["From"] = f"Garcia Folklorico Studio <{FROM_EMAIL or SMTP_USER}>"
    msg["To"] = to
    msg["Subject"] = subject

    # Text + HTML alternative part
    alt = MIMEMultipart("alternative")
    if plain_text:
        alt.attach(MIMEText(plain_text, "plain", "utf-8"))
    else:
        alt.attach(MIMEText(_strip_html(html_body), "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    # Optional .ics calendar invite
    if ics_data:
        ics_part = MIMEText(ics_data, "calendar", "utf-8")
        ics_part.add_header("Content-Disposition", "attachment", filename="event.ics")
        msg.attach(ics_part)

    use_tls = SMTP_PORT == 465
    await aiosmtplib.send(
        msg,
        hostname=SMTP_HOST,
        port=SMTP_PORT,
        use_tls=use_tls,
        start_tls=not use_tls,
        username=SMTP_USER,
        password=SMTP_PASSWORD,
    )


def _strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&middot;", "·", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&#\d+;", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── .ics Calendar ────────────────────────────────────────────────────

def _make_ics(summary: str, start: datetime, end: datetime,
              description: str = "", location: str = STUDIO_FULL) -> str:
    fmt = "%Y%m%dT%H%M%S"
    now = datetime.utcnow().strftime(fmt) + "Z"
    uid = f"{start.strftime(fmt)}-{hash(summary) & 0xFFFFFFFF:08x}@garciafolklorico.com"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Garcia Folklorico Studio//Booking//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"DTSTART:{start.strftime(fmt)}",
        f"DTEND:{end.strftime(fmt)}",
        f"DTSTAMP:{now}",
        f"UID:{uid}",
        f"SUMMARY:{summary}",
        f"LOCATION:{location}",
        f"DESCRIPTION:{description}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines)


# ── HTML Template Shell ──────────────────────────────────────────────

def _email(content: str, preheader: str = "") -> str:
    pre = ""
    if preheader:
        pre = (
            f'<div style="display:none;font-size:1px;color:#FFF5E6;line-height:1px;'
            f'max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;">'
            f'{preheader}</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<!--[if mso]>
<noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript>
<![endif]-->
<title>Garcia Folklorico Studio</title>
<style>
  @media (prefers-color-scheme: dark) {{
    .email-body {{ background-color: #2A1A2E !important; }}
    .email-card {{ background-color: #3D2440 !important; }}
    .email-card td {{ color: #F5E6D0 !important; }}
    .text-purple {{ color: #E8D0F0 !important; }}
    .text-muted {{ color: #C9A0DC !important; }}
    .text-orange {{ color: #FFB347 !important; }}
    .footer-text {{ color: #C9A0DC !important; }}
    .callout-cell {{ background-color: #4A2A4E !important; }}
    .detail-label {{ color: #FFB347 !important; }}
    .banner-bg {{ background-color: #4A154B !important; }}
    .btn-bg {{ background-color: #E8620A !important; }}
    a {{ color: #FFB347 !important; }}
  }}
  @media only screen and (max-width: 620px) {{
    .email-card {{ border-radius: 0 !important; }}
    .content-pad {{ padding-left: 20px !important; padding-right: 20px !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;width:100%;background-color:#FFF5E6;font-family:'Nunito',-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;-webkit-text-size-adjust:100%;">
{pre}

<table role="presentation" cellpadding="0" cellspacing="0" width="100%" class="email-body" style="background-color:#FFF5E6;">
<tr><td align="center" style="padding:20px 12px;">

<table role="presentation" cellpadding="0" cellspacing="0" width="600" class="email-card" style="max-width:600px;width:100%;background-color:#ffffff;border-radius:14px;overflow:hidden;">

<!-- Papel picado top stripe -->
<tr>
<td style="font-size:0;line-height:0;height:8px;" width="20%" bgcolor="#E8620A">&nbsp;</td>
<td style="font-size:0;line-height:0;height:8px;" width="20%" bgcolor="#FFB347">&nbsp;</td>
<td style="font-size:0;line-height:0;height:8px;" width="20%" bgcolor="#C9A0DC">&nbsp;</td>
<td style="font-size:0;line-height:0;height:8px;" width="20%" bgcolor="#4A154B">&nbsp;</td>
<td style="font-size:0;line-height:0;height:8px;" width="20%" bgcolor="#E8620A">&nbsp;</td>
</tr>

<!-- Gradient header banner with logo + name -->
<tr><td colspan="5" align="center" class="banner-bg" bgcolor="#E8620A" style="background:linear-gradient(135deg,#E8620A 0%,#FFB347 40%,#C9A0DC 100%);background-color:#E8620A;padding:28px 32px 24px;">
<table role="presentation" cellpadding="0" cellspacing="0"><tr><td align="center">
<img src="{LOGO_URL}" alt="Garcia Folklorico Studio" width="64" height="64" style="display:block;margin:0 auto;border-radius:50%;border:3px solid rgba(255,255,255,0.4);">
<p style="margin:10px 0 0;font-family:'Abril Fatface',Georgia,'Times New Roman',serif;font-size:16px;color:#ffffff;text-align:center;letter-spacing:0.5px;text-shadow:0 1px 3px rgba(0,0,0,0.2);">Garcia Folklorico Studio</p>
<p style="margin:3px 0 0;font-family:'Great Vibes',cursive,Georgia,serif;font-size:15px;color:rgba(255,255,255,0.9);text-align:center;">La Casa del Folklor</p>
</td></tr></table>
</td></tr>

<!-- Content -->
<tr><td colspan="5" class="content-pad" style="padding:24px 32px 28px;background-color:#ffffff;">
<table role="presentation" cellpadding="0" cellspacing="0" width="100%">
<tr><td style="text-align:left;">
{content}
</td></tr>
</table>
</td></tr>

<!-- Footer divider -->
<tr><td colspan="5" style="padding:0 32px;background-color:#ffffff;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="border-top:1px solid #f0e6d6;font-size:0;line-height:0;">&nbsp;</td></tr></table></td></tr>

<!-- Footer -->
<tr><td colspan="5" align="center" style="padding:16px 32px 20px;background-color:#ffffff;">
<p class="footer-text" style="margin:0 0 4px;font-family:'Nunito',-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;font-size:12px;color:#b8a080;text-align:center;"><a href="{MAPS_URL}" style="color:#b8a080;text-decoration:none;">{STUDIO_ADDRESS}</a></p>
<p style="margin:0 0 8px;font-family:'Nunito',-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;font-size:12px;text-align:center;"><a href="mailto:itzel@garciafolklorico.com" style="color:#E8620A;text-decoration:none;">itzel@garciafolklorico.com</a></p>
<p style="margin:0;text-align:center;">
<a href="https://www.instagram.com/garciafolkloricostudio/" style="color:#C9A0DC;text-decoration:none;font-size:11px;padding:0 6px;">Instagram</a>
<span style="color:#e0d6cc;">&middot;</span>
<a href="https://www.facebook.com/garciafolklorico" style="color:#C9A0DC;text-decoration:none;font-size:11px;padding:0 6px;">Facebook</a>
<span style="color:#e0d6cc;">&middot;</span>
<a href="{SITE_URL}" style="color:#E8620A;text-decoration:none;font-size:11px;font-weight:700;padding:0 6px;">Website</a>
</p>
</td></tr>

<!-- Bottom papel picado stripe -->
<tr>
<td style="font-size:0;line-height:0;height:8px;" width="20%" bgcolor="#E8620A">&nbsp;</td>
<td style="font-size:0;line-height:0;height:8px;" width="20%" bgcolor="#FFB347">&nbsp;</td>
<td style="font-size:0;line-height:0;height:8px;" width="20%" bgcolor="#C9A0DC">&nbsp;</td>
<td style="font-size:0;line-height:0;height:8px;" width="20%" bgcolor="#4A154B">&nbsp;</td>
<td style="font-size:0;line-height:0;height:8px;" width="20%" bgcolor="#E8620A">&nbsp;</td>
</tr>

</table>

</td></tr>
</table>

</body>
</html>"""


# ── Helpers ──────────────────────────────────────────────────────────

def _heading(text):
    return (
        f'<h1 class="text-purple" style="margin:0 0 6px;font-family:\'Abril Fatface\','
        f'Georgia,\'Times New Roman\',serif;font-size:22px;font-weight:400;color:#4A154B;'
        f'text-align:left;line-height:1.3;">{text}</h1>'
    )


def _sub(text):
    return (
        f'<p class="text-muted" style="margin:0 0 16px;font-family:\'Nunito\',-apple-system,'
        f'\'Segoe UI\',Helvetica,Arial,sans-serif;font-size:15px;color:#8a7a6a;'
        f'text-align:left;line-height:1.5;">{text}</p>'
    )


def _section_header(text):
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%" '
        f'style="margin:20px 0 10px;"><tr><td>'
        f'<div style="width:32px;height:3px;background:#E8620A;border-radius:3px;margin-bottom:8px;"></div>'
        f'<p class="text-purple" style="margin:0;font-family:\'Nunito\',-apple-system,\'Segoe UI\','
        f'Helvetica,Arial,sans-serif;font-size:12px;font-weight:700;letter-spacing:1.5px;'
        f'text-transform:uppercase;color:#4A154B;">{text}</p>'
        f'</td></tr></table>'
    )


def _detail_row(label, value):
    return (
        f'<tr>'
        f'<td class="detail-label" style="padding:5px 0;font-family:\'Nunito\',-apple-system,'
        f'\'Segoe UI\',Helvetica,Arial,sans-serif;font-size:11px;letter-spacing:1.5px;'
        f'text-transform:uppercase;color:#E8620A;font-weight:700;vertical-align:top;'
        f'width:100px;white-space:nowrap;">{label}</td>'
        f'<td class="text-purple" style="padding:5px 0 5px 12px;font-family:\'Nunito\',-apple-system,'
        f'\'Segoe UI\',Helvetica,Arial,sans-serif;font-size:15px;color:#4A154B;'
        f'line-height:1.5;vertical-align:top;">{value}</td>'
        f'</tr>'
    )


def _detail_table(*rows):
    inner = "".join(rows)
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%" '
        f'style="margin:0 0 16px;">{inner}</table>'
    )


def _divider():
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" width="100%" '
        'style="margin:12px 0;"><tr><td style="border-top:1px solid #f0e6d6;'
        'font-size:0;line-height:0;">&nbsp;</td></tr></table>'
    )


def _callout(text, border="#E8620A", bg="#FFF5E6"):
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:0 0 16px;"><tr><td class="callout-cell" style="background-color:{bg};'
        f'border-left:4px solid {border};border-radius:0 8px 8px 0;padding:12px 16px;'
        f'text-align:left;"><p class="text-purple" style="margin:0;font-family:\'Nunito\',-apple-system,'
        f'\'Segoe UI\',Helvetica,Arial,sans-serif;font-size:14px;color:#4A154B;'
        f'line-height:1.6;">{text}</p></td></tr></table>'
    )


def _price(amount, label_en="Total Due at Studio", label_es=None):
    label = label_es or label_en
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="margin:8px 0 20px;"><tr><td style="padding:14px 32px;'
        f'background-color:#4A154B;border-radius:14px;">'
        f'<p style="margin:0 0 2px;font-family:\'Nunito\',-apple-system,\'Segoe UI\','
        f'Helvetica,Arial,sans-serif;font-size:10px;letter-spacing:2px;'
        f'text-transform:uppercase;color:#C9A0DC;">{label}</p>'
        f'<p style="margin:0;font-family:\'Abril Fatface\',Georgia,\'Times New Roman\','
        f'serif;font-size:28px;color:#FFB347;">{amount}</p>'
        f'</td></tr></table>'
    )


def _btn(text, href="mailto:itzel@garciafolklorico.com"):
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" align="center" '
        f'style="margin:16px auto 8px;"><tr><td class="btn-bg" align="center" style="padding:13px 36px;'
        f'background-color:#E8620A;border-radius:50px;">'
        f'<a href="{href}" style="font-family:\'Nunito\',-apple-system,\'Segoe UI\','
        f'Helvetica,Arial,sans-serif;font-size:14px;font-weight:700;color:#ffffff;'
        f'text-decoration:none;display:block;">{text}</a>'
        f'</td></tr></table>'
    )


def _warm_welcome(child_name, cls, is_es):
    if is_es:
        txt = (f"Estamos muy emocionados de darle la bienvenida a <strong>{child_name}</strong> "
               f"a nuestra familia de <strong>{cls}</strong>! "
               f"Prepárense para un viaje maravilloso de baile, cultura y alegría.")
    else:
        txt = (f"We're so excited to welcome <strong>{child_name}</strong> "
               f"to our <strong>{cls}</strong> family! "
               f"Get ready for a wonderful journey of dance, culture, and joy.")
    return (
        f'<p class="text-muted" style="margin:0 0 20px;font-family:\'Nunito\',-apple-system,'
        f'\'Segoe UI\',Helvetica,Arial,sans-serif;font-size:14px;color:#8a7a6a;'
        f'text-align:left;line-height:1.6;font-style:italic;">{txt}</p>'
    )


def _first_day_info(is_es):
    if is_es:
        title = "Para el Primer Día"
        items = [
            "Ropa cómoda o falda de folklórico si tiene",
            "Botella de agua",
            "Llegar 10 minutos antes",
            f'<a href="{MAPS_URL}" style="color:#E8620A;text-decoration:none;">Ver ubicación del estudio en Google Maps</a>',
        ]
    else:
        title = "For the First Day"
        items = [
            "Comfortable clothes or folklorico skirt if available",
            "Water bottle",
            "Arrive 10 minutes early",
            f'<a href="{MAPS_URL}" style="color:#E8620A;text-decoration:none;">View studio location on Google Maps</a>',
        ]

    bullets = "".join(
        f'<tr><td style="padding:3px 0;vertical-align:top;width:20px;color:#FFB347;font-size:14px;">&#9670;</td>'
        f'<td class="text-purple" style="padding:3px 0 3px 6px;font-family:\'Nunito\',-apple-system,\'Segoe UI\','
        f'Helvetica,Arial,sans-serif;font-size:14px;color:#4A154B;line-height:1.5;">{item}</td></tr>'
        for item in items
    )
    return (
        _section_header(title)
        + f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%" '
          f'style="margin:0 0 16px;">{bullets}</table>'
    )


def _ref_number(prefix, record_id, year=None):
    yr = year or datetime.utcnow().year
    return f"{prefix}-{yr}-{record_id:04d}"


# ═══════════════════════════════════════════════════════════════════
# CLASS REGISTRATION
# ═══════════════════════════════════════════════════════════════════

async def send_registration_email(reg, class_type, block, schedule_en, schedule_es):
    from routes.schedule import format_date_en, format_date_es

    is_es = reg.language == "es"
    cls = class_type.name_es if is_es else class_type.name_en
    sched = (schedule_es if is_es else schedule_en).replace(", ", "<br>")
    ages = class_type.age_range_text_es if is_es else class_type.age_range_text_en
    fd = format_date_es if is_es else format_date_en
    block_range = f"{fd(block.start_date)} — {fd(block.end_date)}"

    if reg.status == "registered":
        ref = _ref_number("GFS", reg.id)

        # Subject
        enrolled_word = "inscrito/a en" if is_es else "enrolled in"
        subject = f"\U0001f483 {reg.child_name} {enrolled_word} {cls}! — Garcia Folklorico Studio"

        # Preheader
        session_word = "para" if is_es else "for"
        preheader = f"{reg.child_name} {enrolled_word} {cls} {session_word} {block.name}!"

        # Content
        welcome = "Bienvenido/a," if is_es else "Welcome,"
        c = _heading(f"{welcome} {reg.child_name}!")
        enrolled_text = f"{'Inscrito/a en' if is_es else 'Enrolled in'} <strong>{cls}</strong>"
        c += _sub(enrolled_text)
        c += _warm_welcome(reg.child_name, cls, is_es)
        c += _section_header("Detalles de Clase" if is_es else "Class Details")
        c += _detail_table(
            _detail_row("Ref", f"<strong>{ref}</strong>"),
            _detail_row("Clase" if is_es else "Class", f"<strong>{cls}</strong> &middot; {ages}"),
            _detail_row("Periodo" if is_es else "Session", f"<strong>{block.name}</strong><br><span style='font-size:13px;color:#8a7a6a;'>{block_range}</span>"),
            _detail_row("Horario" if is_es else "Schedule", sched),
        )
        c += _first_day_info(is_es)
        c += _divider()
        c += _callout(
            "Para cambios o cancelaciones, contáctenos." if is_es
            else "For changes or cancellations, contact us."
        )
        c += _btn("Contáctenos" if is_es else "Contact Us")

        # .ics for first day of session
        start_dt = datetime.combine(block.start_date, datetime.min.time().replace(hour=9))
        end_dt = start_dt + timedelta(hours=1)
        ics = _make_ics(
            summary=f"{cls} — Garcia Folklorico Studio",
            start=start_dt,
            end=end_dt,
            description=f"{reg.child_name} — {cls} ({ages})\n{block.name}: {block_range}\nRef: {ref}",
        )
        await _send_email(reg.email, subject, _email(c, preheader), ics_data=ics)
        try:
            publish_event("email", "sent", {
                "to": reg.email,
                "contact_name": reg.parent_name,
                "child_name": reg.child_name,
                "email_type": "registration_confirmation" if reg.status == "registered" else "waitlist_notification",
                "subject": subject,
                "class_name": class_type.name_en,
            })
        except Exception:
            pass

    else:
        # Waitlisted
        wl_label = "en lista de espera para" if is_es else "on the waitlist for"
        subject = f"\U0001f483 {reg.child_name} {wl_label} {cls} — Garcia Folklorico Studio"
        preheader = f"{reg.child_name} {wl_label} {cls}."

        c = _heading("Lista de Espera" if is_es else "Waitlist")
        if is_es:
            c += _sub(f"<strong>{cls}</strong> está lleno. <strong>{reg.child_name}</strong> está en la lista.")
        else:
            c += _sub(f"<strong>{cls}</strong> is full. <strong>{reg.child_name}</strong> is on the waitlist.")
        c += _callout(
            "Le enviaremos un correo cuando se abra un espacio. Tendrá <strong>48 horas</strong> para confirmar."
            if is_es else
            "We'll email you when a spot opens. You'll have <strong>48 hours</strong> to confirm.",
            "#C9A0DC", "#f8f0ff"
        )

        await _send_email(reg.email, subject, _email(c, preheader))
        try:
            publish_event("email", "sent", {
                "to": reg.email,
                "contact_name": reg.parent_name,
                "child_name": reg.child_name,
                "email_type": "registration_confirmation" if reg.status == "registered" else "waitlist_notification",
                "subject": subject,
                "class_name": class_type.name_en,
            })
        except Exception:
            pass


async def send_registration_notification(reg, class_type, block, schedule_en):
    if not STUDIO_EMAIL:
        return
    from routes.schedule import format_date_en

    is_reg = reg.status == "registered"
    reg_type = "Registration" if is_reg else "Waitlist"
    subject = f"{reg_type}: {reg.child_name} — {class_type.name_en}"
    preheader = f"New {reg_type.lower()}: {reg.child_name} — {class_type.name_en}"

    c = _heading(f"New {reg_type}")
    c += _sub(f"<strong>{reg.child_name}</strong> &middot; {class_type.name_en}")

    c += _section_header("Student Info")
    c += _detail_table(
        _detail_row("Child", f"<strong>{reg.child_name}</strong> &middot; Age {reg.child_age}"),
        _detail_row("Parent", reg.parent_name),
        _detail_row("Contact", f"{reg.phone}<br><a href='mailto:{reg.email}' style='color:#E8620A;text-decoration:none;'>{reg.email}</a>"),
        _detail_row("Emergency", reg.emergency_contact),
    )

    c += _section_header("Enrollment")
    c += _detail_table(
        _detail_row("Class", f"<strong>{class_type.name_en}</strong> &middot; {class_type.age_range_text_en}"),
        _detail_row("Session", f"{block.name} &middot; {format_date_en(block.start_date)} — {format_date_en(block.end_date)}"),
    )

    await _send_email(STUDIO_EMAIL, subject, _email(c, preheader))
    try:
        publish_event("email", "sent", {
            "to": STUDIO_EMAIL,
            "contact_name": "Studio Team",
            "child_name": reg.child_name,
            "email_type": "registration_staff_notification",
            "subject": subject,
            "class_name": class_type.name_en,
        })
    except Exception:
        pass


async def send_waitlist_promotion_email(reg, class_type, block):
    is_es = reg.language == "es"
    cls = class_type.name_es if is_es else class_type.name_en

    if is_es:
        subject = f"\U0001f483 Se abrió un espacio para {reg.child_name} en {cls}! — Garcia Folklorico Studio"
        preheader = f"Se abrió un lugar en {cls} para {reg.child_name}."
    else:
        subject = f"\U0001f483 A spot opened for {reg.child_name} in {cls}! — Garcia Folklorico Studio"
        preheader = f"A spot opened in {cls} for {reg.child_name}."

    c = _heading("¡Espacio Disponible!" if is_es else "Spot Available!")
    if is_es:
        c += _sub(f"Se abrió un lugar en <strong>{cls}</strong> para <strong>{reg.child_name}</strong>.")
    else:
        c += _sub(f"A spot opened in <strong>{cls}</strong> for <strong>{reg.child_name}</strong>.")

    c += _callout(
        "Tiene <strong>48 horas</strong> para confirmar su lugar."
        if is_es else
        "You have <strong>48 hours</strong> to confirm your spot.",
        "#2e7d32", "#f0f8f0"
    )
    c += _btn("Confirmar" if is_es else "Confirm Now")

    await _send_email(reg.email, subject, _email(c, preheader))
    try:
        publish_event("email", "sent", {
            "to": reg.email,
            "contact_name": reg.parent_name,
            "child_name": reg.child_name,
            "email_type": "waitlist_promotion",
            "subject": subject,
            "class_name": class_type.name_en,
        })
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
# RENTAL BOOKING
# ═══════════════════════════════════════════════════════════════════

async def send_rental_confirmation(booking):
    start = booking.start_time.strftime("%I:%M %p").lstrip("0")
    end = booking.end_time.strftime("%I:%M %p").lstrip("0")
    date_str = booking.date.strftime("%A, %B %d, %Y")
    date_short = booking.date.strftime("%B %d, %Y")
    rate = booking.total_price / booking.hours
    is_es = booking.language == "es"

    ref = _ref_number("GFR", booking.id)

    if is_es:
        subject = f"\U0001f3e0 Su renta de estudio está confirmada! — {date_short}"
        preheader = f"Reserva confirmada: {date_str}, {start} — {end}."
    else:
        subject = f"\U0001f3e0 Your studio rental is confirmed! — {date_short}"
        preheader = f"Rental confirmed: {date_str}, {start} — {end}."

    c = _heading("Reserva Confirmada" if is_es else "Rental Confirmed")
    c += _sub("Su espacio está reservado" if is_es else "Your space is reserved")

    c += _section_header("Detalles de Reserva" if is_es else "Booking Details")
    hrs_label = "horas" if is_es else "hours"
    c += _detail_table(
        _detail_row("Ref", f"<strong>{ref}</strong>"),
        _detail_row("Fecha" if is_es else "Date", f"<strong>{date_str}</strong>"),
        _detail_row("Horario" if is_es else "Time", f"{start} — {end} &middot; {booking.hours} {hrs_label}"),
        _detail_row("Tarifa" if is_es else "Rate", f"${ rate:.0f}/{'hora' if is_es else 'hour'}"),
    )

    c += _price(
        f"${booking.total_price:.0f}",
        label_en="Total Due at Studio",
        label_es="Total a Pagar en Estudio" if is_es else None,
    )
    c += _callout(
        "El pago se realiza en el estudio." if is_es
        else "Payment is due at the studio."
    )
    c += _btn("Contáctenos" if is_es else "Contact Us")

    # .ics for booking
    start_dt = datetime.combine(booking.date, booking.start_time)
    end_dt = datetime.combine(booking.date, booking.end_time)
    ics = _make_ics(
        summary="Studio Rental — Garcia Folklorico",
        start=start_dt,
        end=end_dt,
        description=f"{booking.renter_name}\n{booking.purpose}\n${booking.total_price:.0f} due at studio",
    )

    await _send_email(booking.email, subject, _email(c, preheader), ics_data=ics)
    try:
        publish_event("email", "sent", {
            "to": booking.email,
            "contact_name": booking.renter_name,
            "child_name": "",
            "email_type": "rental_confirmation",
            "subject": subject,
            "class_name": "",
        })
    except Exception:
        pass


async def send_rental_notification(booking):
    if not STUDIO_EMAIL:
        return

    start = booking.start_time.strftime("%I:%M %p").lstrip("0")
    end = booking.end_time.strftime("%I:%M %p").lstrip("0")
    date_str = booking.date.strftime("%A, %B %d, %Y")

    subject = f"New Rental: {booking.renter_name} — {date_str}"
    preheader = f"New rental booking: {booking.renter_name}, {date_str}, {start} — {end}."

    c = _heading("New Studio Rental")
    c += _sub(f"<strong>{booking.renter_name}</strong> &middot; {date_str}")

    c += _section_header("Booking Details")
    c += _detail_table(
        _detail_row("Date", f"<strong>{date_str}</strong>"),
        _detail_row("Time", f"{start} — {end} &middot; {booking.hours} hours"),
        _detail_row("Purpose", booking.purpose),
        _detail_row("Renter", f"{booking.renter_name}<br>{booking.phone}<br><a href='mailto:{booking.email}' style='color:#E8620A;text-decoration:none;'>{booking.email}</a>"),
    )

    c += _price(f"${booking.total_price:.0f}")

    await _send_email(STUDIO_EMAIL, subject, _email(c, preheader))
    try:
        publish_event("email", "sent", {
            "to": STUDIO_EMAIL,
            "contact_name": "Studio Team",
            "child_name": "",
            "email_type": "rental_staff_notification",
            "subject": subject,
            "class_name": "",
        })
    except Exception:
        pass
