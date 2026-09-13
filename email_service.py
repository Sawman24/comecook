"""
Cooked - Transactional Email Service Module
Supports standard SMTP (Gmail, Google Workspace, Brevo, SendGrid, Amazon SES, Mailgun, Postmark, custom SMTP).
"""

import os
import smtplib
import threading
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

logger = logging.getLogger("cooked.email")

def get_smtp_config():
    """Load SMTP configuration from environment variables."""
    host = os.environ.get("SMTP_HOST", "").strip()
    port = int(os.environ.get("SMTP_PORT", "587").strip() or "587")
    user = os.environ.get("SMTP_USER", os.environ.get("SMTP_USERNAME", "")).strip()
    password = os.environ.get("SMTP_PASSWORD", os.environ.get("SMTP_PASS", "")).strip()
    
    # Auto-detect TLS/SSL if not explicitly set
    use_tls_env = os.environ.get("SMTP_USE_TLS")
    if use_tls_env is not None:
        use_tls = use_tls_env.lower() in ("1", "true", "yes")
    else:
        use_tls = (port in (587, 25))

    use_ssl_env = os.environ.get("SMTP_USE_SSL")
    if use_ssl_env is not None:
        use_ssl = use_ssl_env.lower() in ("1", "true", "yes")
    else:
        use_ssl = (port == 465)

    from_name = os.environ.get("SMTP_FROM_NAME", "Cooked").strip()
    from_email = os.environ.get("SMTP_FROM_EMAIL", os.environ.get("EMAIL_FROM", os.environ.get("MAIL_DEFAULT_SENDER", ""))).strip()
    if not from_email:
        from_email = user if user else "cooked.noreply@gmail.com"

    if "<" in from_email and ">" in from_email:
        from_addr = from_email
    else:
        from_addr = f"{from_name} <{from_email}>"

    base_url = os.environ.get("APP_URL", os.environ.get("BASE_URL", "https://comecook.app")).rstrip("/")

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "use_tls": use_tls,
        "use_ssl": use_ssl,
        "from_addr": from_addr,
        "base_url": base_url,
        "is_configured": bool(host and user and password)
    }

def _send_smtp_payload(to_email: str, subject: str, html_body: str, text_body: str):
    """Internal blocking worker to connect to SMTP and transmit email."""
    cfg = get_smtp_config()
    
    if not cfg["is_configured"]:
        logger.info(
            f"\n[EMAIL DISPATCH - DEV / LOCAL FALLBACK MODE]\n"
            f"To: {to_email}\n"
            f"From: {cfg['from_addr']}\n"
            f"Subject: {subject}\n"
            f"Content:\n{text_body}\n"
            f"--------------------------------------------------"
        )
        return True

    from email.utils import parseaddr, formatdate, make_msgid
    import ssl
    import sys
    import traceback

    # Envelope sender (MAIL FROM) MUST be a raw email address without display name
    envelope_from = parseaddr(cfg["from_addr"])[1] or cfg["user"] or "cooked.noreply@gmail.com"

    # Clean password (remove quotes/spaces commonly copied from Google App Passwords)
    smtp_password = cfg["password"].strip().strip("'\"")
    if "gmail.com" in cfg["host"].lower():
        smtp_password = smtp_password.replace(" ", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_email
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="comecook.app")

    # Attach plain text and HTML versions
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        print(f"[SMTP] Attempting connection to {cfg['host']}:{cfg['port']} for recipient {to_email}...", flush=True)
        context = ssl.create_default_context()

        if cfg["use_ssl"]:
            server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context, timeout=20)
        else:
            server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=20)
            server.ehlo()
            if cfg["use_tls"]:
                server.starttls(context=context)
                server.ehlo()

        server.login(cfg["user"], smtp_password)
        server.sendmail(envelope_from, [to_email], msg.as_string())
        server.quit()

        print(f"[SMTP SUCCESS] Email delivered to {to_email}: '{subject}'", flush=True)
        logger.info(f"Email successfully sent to {to_email}: '{subject}'")
        return True
    except Exception as e:
        err_trace = traceback.format_exc()
        print(f"[SMTP ERROR] Failed to send email to {to_email}: {e}\n{err_trace}", file=sys.stderr, flush=True)
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False

def send_email_async(to_email: str, subject: str, html_body: str, text_body: str):
    """Dispatch email in background thread to keep HTTP response times instant."""
    thread = threading.Thread(
        target=_send_smtp_payload,
        args=(to_email, subject, html_body, text_body),
        daemon=True
    )
    thread.start()
    return thread

# ==============================================================================
# EMAIL TEMPLATES
# ==============================================================================

def get_base_html_template(title: str, preheader: str, content_html: str, base_url: str = "https://comecook.app") -> str:
    """Standard responsive culinary HTML email shell."""
    clean_host = base_url.replace("https://", "").replace("http://", "").rstrip("/")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background-color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      color: #1e293b;
      -webkit-font-smoothing: antialiased;
    }}
    .wrapper {{
      width: 100%;
      background-color: #f8fafc;
      padding: 30px 15px;
      box-sizing: border-box;
    }}
    .container {{
      max-width: 560px;
      margin: 0 auto;
      background-color: #ffffff;
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
      border: 1px solid #e2e8f0;
    }}
    .header {{
      background: linear-gradient(135deg, #f97316 0%, #ea580c 100%);
      padding: 28px 24px;
      text-align: center;
      color: #ffffff;
    }}
    .header h1 {{
      margin: 0;
      font-size: 26px;
      font-weight: 800;
      letter-spacing: -0.5px;
    }}
    .body {{
      padding: 32px 28px;
      line-height: 1.6;
      font-size: 15px;
      color: #334155;
    }}
    .btn {{
      display: inline-block;
      background: #f97316;
      color: #ffffff !important;
      text-decoration: none;
      font-weight: 700;
      font-size: 15px;
      padding: 14px 28px;
      border-radius: 9999px;
      text-align: center;
      margin: 20px 0;
      box-shadow: 0 4px 12px rgba(249, 115, 22, 0.3);
    }}
    .footer {{
      background-color: #f1f5f9;
      padding: 20px 24px;
      text-align: center;
      font-size: 12px;
      color: #64748b;
      border-top: 1px solid #e2e8f0;
    }}
    .footer a {{
      color: #f97316;
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <div style="display:none;font-size:1px;color:#333333;line-height:1px;max-height:0px;max-width:0px;opacity:0;overflow:hidden;">
    {preheader}
  </div>
  <div class="wrapper">
    <div class="container">
      <div class="header">
        <h1>🍳 Cooked</h1>
      </div>
      <div class="body">
        {content_html}
      </div>
      <div class="footer">
        <p style="margin: 0 0 6px 0;">Cooked — The Modern Culinary Community</p>
        <p style="margin: 0;">Need help? Visit our kitchen at <a href="{base_url}">{clean_host}</a></p>
      </div>
    </div>
  </div>
</body>
</html>"""

def send_password_reset_email(to_email: str, username: str, reset_token: str, base_url: str = "https://comecook.app"):
    """Generate and dispatch password reset email."""
    reset_url = f"{base_url}/#/reset-password?token={reset_token}"
    subject = "Reset Your Cooked Password"
    preheader = f"Use this link to reset your Cooked account password (expires in 1 hour)."

    content_html = f"""
      <h2 style="margin-top: 0; color: #0f172a; font-size: 20px; font-weight: 700;">Password Reset Request</h2>
      <p>Hello <strong>@{username}</strong>,</p>
      <p>We received a request to reset the password for your Cooked account. Click the button below to set a new password:</p>
      
      <div style="text-align: center; margin: 28px 0;">
        <a href="{reset_url}" class="btn">Reset My Password</a>
      </div>

      <p style="font-size: 13px; color: #64748b; margin-top: 20px; word-break: break-all;">
        If the button above doesn't work, copy and paste this link into your browser:<br>
        <a href="{reset_url}" style="color: #f97316;">{reset_url}</a>
      </p>

      <div style="margin-top: 28px; padding: 14px; background-color: #fef3c7; border-left: 4px solid #f59e0b; border-radius: 6px; font-size: 13px; color: #92400e;">
        <strong>⏳ Expiration Notice:</strong> This password reset link will expire in <strong>1 hour</strong> for your security. If you did not request this password reset, you can safely ignore this email.
      </div>
    """

    text_body = f"""Hello @{username},

We received a request to reset the password for your Cooked account.

To reset your password, visit the following link:
{reset_url}

This link is single-use and will expire in 1 hour.

If you did not make this request, you can safely ignore this email.

— The Cooked Culinary Team
{base_url}
"""

    return send_email_async(to_email, subject, get_base_html_template(subject, preheader, content_html, base_url=base_url), text_body)

def send_welcome_email(to_email: str, username: str, display_name: str, base_url: str = "https://comecook.app"):
    """Generate and dispatch welcome email on registration."""
    subject = "Welcome to the Cooked Kitchen! 👨‍🍳"
    preheader = f"Welcome to Cooked, Chef {display_name}! Start exploring recipes and sharing your culinary craft."

    content_html = f"""
      <h2 style="margin-top: 0; color: #0f172a; font-size: 20px; font-weight: 700;">Welcome to Cooked, Chef {display_name}! 👨‍🍳</h2>
      <p>Your account (<strong>@{username}</strong>) is ready to cook.</p>
      <p>Here are a few great ways to get started:</p>
      
      <ul style="padding-left: 20px; line-height: 1.8; color: #334155;">
        <li><strong>Import Recipes:</strong> Paste any recipe URL to automatically import ingredients and steps.</li>
        <li><strong>Join Station Communities:</strong> Explore Baking, Grilling, Sourdough, Pasta, and Vegan stations.</li>
        <li><strong>Share "I Made This!" Snaps:</strong> Post photos and reviews when you remake dishes from other chefs.</li>
        <li><strong>Kitchen Whispers:</strong> Chat and share secret recipes with your culinary friends.</li>
      </ul>

      <div style="text-align: center; margin: 28px 0;">
        <a href="{base_url}" class="btn">Explore Cooked Now</a>
      </div>
    """

    text_body = f"""Welcome to Cooked, Chef {display_name}!

Your account (@{username}) has been created successfully.

Get started:
- Import recipes with 1-click from any website
- Join Station communities (Baking, Grilling, Sourdough, Vegan, and more)
- Share your cook snaps and recipe variations
- Whisper with fellow chefs

Start cooking now: {base_url}

— The Cooked Culinary Team
"""

    return send_email_async(to_email, subject, get_base_html_template(subject, preheader, content_html, base_url=base_url), text_body)

def send_password_changed_email(to_email: str, username: str, base_url: str = "https://comecook.app"):
    """Security notification sent when a password is changed."""
    subject = "Your Cooked Password Has Been Changed"
    preheader = f"Security Alert: The password for your Cooked account @{username} was recently updated."

    content_html = f"""
      <h2 style="margin-top: 0; color: #0f172a; font-size: 20px; font-weight: 700;">Security Alert: Password Updated</h2>
      <p>Hello <strong>@{username}</strong>,</p>
      <p>The password for your Cooked account was successfully changed on {datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")}.</p>
      <p>All previous active sessions have been signed out for security.</p>
      <p style="color: #64748b; font-size: 13px;">If you made this change, no further action is required.</p>
      <div style="margin-top: 20px; padding: 14px; background-color: #fee2e2; border-left: 4px solid #ef4444; border-radius: 6px; font-size: 13px; color: #991b1b;">
        <strong>⚠️ Did not change your password?</strong> Please contact an administrator or reset your password immediately at <a href="{base_url}" style="color: #b91c1c;">{base_url}</a>.
      </div>
    """

    text_body = f"""Hello @{username},

The password for your Cooked account was successfully changed.

If you made this change, no further action is needed.

If you did NOT make this change, please reset your password immediately at {base_url} and contact an administrator.

— The Cooked Security Team
"""

    return send_email_async(to_email, subject, get_base_html_template(subject, preheader, content_html, base_url=base_url), text_body)
