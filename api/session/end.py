from http.server import BaseHTTPRequestHandler
import base64, json, os, urllib.parse, urllib.request


def _get_access_token():
    client_id = os.environ['SPOTIFY_CLIENT_ID']
    client_secret = os.environ['SPOTIFY_CLIENT_SECRET']
    refresh_token = os.environ['SPOTIFY_REFRESH_TOKEN']

    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data = urllib.parse.urlencode({
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }).encode()

    req = urllib.request.Request(
        'https://accounts.spotify.com/api/token',
        data=data,
        headers={
            'Authorization': f'Basic {credentials}',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())['access_token']


def _spotify_request(method, path, token, body=None):
    url = f'https://api.spotify.com/v1{path}'
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }
    )
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def _create_playlist(token, session_name, tracks):
    user_resp = _spotify_request('GET', '/me', token)
    user_id = user_resp['id']

    playlist = _spotify_request('POST', f'/users/{user_id}/playlists', token, {
        'name': session_name,
        'public': True,
        'description': 'Created by ROOOOM — Read the Room',
    })
    playlist_id = playlist['id']
    playlist_url = playlist['external_urls']['spotify']

    uris = [t['uri'] for t in tracks if t.get('uri')]
    for i in range(0, len(uris), 100):
        _spotify_request('POST', f'/playlists/{playlist_id}/tracks', token, {
            'uris': uris[i:i + 100],
        })

    return playlist_url


def _send_sms(phones, session_name, playlist_url):
    account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
    auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
    from_number = os.environ.get('TWILIO_FROM_NUMBER')

    if not all([account_sid, auth_token, from_number]):
        print('[session_end] Twilio env vars not set, skipping SMS')
        return

    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    message_body = f"Thanks for being part of {session_name}. Here's tonight's playlist: {playlist_url}"

    for phone in phones:
        try:
            data = urllib.parse.urlencode({
                'To': phone,
                'From': from_number,
                'Body': message_body,
            }).encode()
            req = urllib.request.Request(
                f'https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json',
                data=data,
                headers={
                    'Authorization': f'Basic {credentials}',
                    'Content-Type': 'application/x-www-form-urlencoded',
                }
            )
            with urllib.request.urlopen(req) as resp:
                resp.read()
            print(f'[session_end] SMS sent to {phone}')
        except Exception as e:
            print(f'[session_end] SMS failed for {phone}: {e}')


def _send_emails(emails, session_name, playlist_url):
    api_key = os.environ.get('RESEND_API_KEY')
    from_email = os.environ.get('RESEND_FROM_EMAIL', 'noreply@roooom.app')

    if not api_key:
        print('[session_end] RESEND_API_KEY not set, skipping email')
        return

    subject = f"Tonight's playlist — {session_name}"
    html_body = (
        f"<p>Thanks for being part of <strong>{session_name}</strong>.</p>"
        f"<p>Here's tonight's playlist: "
        f"<a href=\"{playlist_url}\">{playlist_url}</a></p>"
    )

    for email in emails:
        try:
            payload = json.dumps({
                'from': from_email,
                'to': [email],
                'subject': subject,
                'html': html_body,
            }).encode()
            req = urllib.request.Request(
                'https://api.resend.com/emails',
                data=payload,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                }
            )
            with urllib.request.urlopen(req) as resp:
                resp.read()
            print(f'[session_end] Email sent to {email}')
        except Exception as e:
            print(f'[session_end] Email failed for {email}: {e}')


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        tracks = body.get('tracks', [])
        session_name = body.get('session_name', os.environ.get('SESSION_NAME', 'Read the Room'))
        contacts = body.get('contacts', {})
        phones = [p.strip() for p in contacts.get('phones', []) if p.strip()]
        emails = [e.strip() for e in contacts.get('emails', []) if e.strip()]

        try:
            token = body.get('access_token') or _get_access_token()
            playlist_url = _create_playlist(token, session_name, tracks)
        except Exception as e:
            error_body = json.dumps({'error': str(e)}).encode()
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', len(error_body))
            self.end_headers()
            self.wfile.write(error_body)
            return

        _send_sms(phones, session_name, playlist_url)
        _send_emails(emails, session_name, playlist_url)

        resp_body = json.dumps({'playlist_url': playlist_url}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', len(resp_body))
        self.end_headers()
        self.wfile.write(resp_body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
