#!/usr/bin/env python3
"""
Diagnostic CLI tool to test SMTP email configuration directly from terminal or container.
Usage:
    python test_smtp_cli.py [recipient@example.com]
"""

import sys
import os
import smtplib
import ssl
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import parseaddr, formatdate, make_msgid

from email_service import get_smtp_config

def run_smtp_diagnostic(recipient: str = None):
    print("=" * 60)
    print(" COOKED - SMTP CONNECTION & EMAIL DELIVERY DIAGNOSTIC")
    print("=" * 60)

    cfg = get_smtp_config()
    print(f"SMTP Host:       {cfg['host'] or '(NOT SET)'}")
    print(f"SMTP Port:       {cfg['port']}")
    print(f"SMTP User:       {cfg['user'] or '(NOT SET)'}")
    print(f"SMTP Password:   {'*' * len(cfg['password']) if cfg['password'] else '(NOT SET)'}")
    print(f"Use TLS:         {cfg['use_tls']}")
    print(f"Use SSL:         {cfg['use_ssl']}")
    print(f"From Address:    {cfg['from_addr']}")
    print(f"App Base URL:    {cfg['base_url']}")
    print(f"Configured:      {cfg['is_configured']}")
    print("-" * 60)

    if not cfg["is_configured"]:
        print("[!] SMTP is NOT configured (SMTP_HOST, SMTP_USER, or SMTP_PASSWORD missing).")
        print("    In development mode, emails are logged to the console without sending.")
        print("    Set SMTP_HOST, SMTP_USER, and SMTP_PASSWORD in your environment variables.")
        return False

    to_addr = recipient or cfg["user"]
    print(f"Sending test diagnostic email to: {to_addr}")

    envelope_from = parseaddr(cfg["from_addr"])[1] or cfg["user"]
    smtp_password = cfg["password"].strip().strip("'\"")
    if "gmail.com" in cfg["host"].lower():
        smtp_password = smtp_password.replace(" ", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Cooked - SMTP Test Email Delivery"
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_addr
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="comecook.app")

    text_body = "This is a test email sent from Cooked to confirm your SMTP configuration works perfectly!"
    html_body = f"""
    <div style="font-family: sans-serif; padding: 20px; background-color: #f8fafc; border-radius: 8px;">
        <h2 style="color: #ea580c;">🍳 Cooked SMTP Test Successful!</h2>
        <p>Your SMTP mailer is fully operational and ready to send password resets and notifications.</p>
        <p style="color: #64748b; font-size: 13px;">Sent from Cooked mailer via {cfg['host']}:{cfg['port']}</p>
    </div>
    """
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        print(f"1. Connecting to {cfg['host']}:{cfg['port']}...")
        if cfg["use_ssl"]:
            server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context, timeout=20)
        else:
            server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=20)
            print("2. Sending EHLO...")
            server.ehlo()
            if cfg["use_tls"]:
                print("3. Upgrading to TLS (STARTTLS)...")
                server.starttls(context=context)
                server.ehlo()

        print(f"4. Authenticating as '{cfg['user']}'...")
        server.login(cfg["user"], smtp_password)

        print(f"5. Transmitting message from <{envelope_from}> to <{to_addr}>...")
        server.sendmail(envelope_from, [to_addr], msg.as_string())
        server.quit()

        print("=" * 60)
        print("✅ SUCCESS! Test email was successfully accepted by SMTP server.")
        print(f"   Check the inbox of: {to_addr}")
        print("=" * 60)
        return True
    except smtplib.SMTPAuthenticationError as e:
        print("\n❌ AUTHENTICATION ERROR:")
        print(f"   The server rejected your credentials: {e}")
        print("   If using Gmail:")
        print("   1. Make sure 2-Step Verification is turned ON for cooked.noreply@gmail.com")
        print("   2. Generate a 16-character App Password at: https://myaccount.google.com/apppasswords")
        print("   3. Put that 16-character App Password into SMTP_PASSWORD / SMTP_PASS")
        return False
    except smtplib.SMTPConnectError as e:
        print("\n❌ CONNECTION ERROR:")
        print(f"   Could not connect to {cfg['host']}:{cfg['port']}: {e}")
        print("   Check your server firewall or outbound port 587 rules.")
        return False
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR ({type(e).__name__}): {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    success = run_smtp_diagnostic(target)
    sys.exit(0 if success else 1)
