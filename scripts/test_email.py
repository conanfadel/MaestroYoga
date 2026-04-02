import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv() -> bool:
        return False

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.mailer import send_email_verification_email


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Send a test verification email using current mail settings.")
    parser.add_argument("--to", required=True, help="Recipient email address")
    args = parser.parse_args()

    provider = os.getenv("MAIL_PROVIDER", "smtp")
    host = os.getenv("SMTP_HOST", "")
    user = os.getenv("SMTP_USER", "")
    sender = os.getenv("SMTP_FROM", "")

    print(f"MAIL_PROVIDER={provider}")
    print(f"SMTP_HOST={host}")
    print(f"SMTP_USER={user}")
    print(f"SMTP_FROM={sender}")

    test_link = "https://example.com/verify?token=test"
    sent, info = send_email_verification_email(args.to, test_link)
    if sent:
        print("SUCCESS: Test email was sent.")
    else:
        print(f"FAILED: {info}")
        print("Tip: for Gmail, use a 16-character App Password (not your normal Gmail password).")


if __name__ == "__main__":
    main()
