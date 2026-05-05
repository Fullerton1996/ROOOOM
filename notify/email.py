import os

import resend


def send_playlist_link(to_emails: list[str], playlist_url: str, session_name: str) -> None:
    resend.api_key = os.environ["RESEND_API_KEY"]
    from_email = os.environ["RESEND_FROM_EMAIL"]

    html = f"""
    <html>
    <body style="font-family: -apple-system, sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 2rem;">
      <h2 style="font-weight: 300; letter-spacing: 0.05em;">{session_name}</h2>
      <p style="margin-top: 1.5rem; color: #aaa;">
        Thanks for being part of the room tonight.
      </p>
      <p style="margin-top: 1rem;">
        <a href="{playlist_url}"
           style="display: inline-block; padding: 0.75rem 1.5rem; background: #1db954;
                  color: #000; text-decoration: none; border-radius: 2rem; font-weight: 500;">
          Open the playlist
        </a>
      </p>
    </body>
    </html>
    """

    for email in to_emails:
        resend.Emails.send({
            "from": from_email,
            "to": email,
            "subject": f"Your playlist from {session_name}",
            "html": html,
        })
        print(f"[email] sent to {email}")
