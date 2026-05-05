import os

from twilio.rest import Client


def send_playlist_link(to_numbers: list[str], playlist_url: str, session_name: str) -> None:
    client = Client(
        os.environ["TWILIO_ACCOUNT_SID"],
        os.environ["TWILIO_AUTH_TOKEN"],
    )
    from_number = os.environ["TWILIO_FROM_NUMBER"]
    body = f"Thanks for being part of {session_name}. Here's the playlist from tonight: {playlist_url}"

    for number in to_numbers:
        client.messages.create(body=body, from_=from_number, to=number)
        print(f"[sms] sent to {number}")
