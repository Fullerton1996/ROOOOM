from http.server import BaseHTTPRequestHandler
import base64, json, os, urllib.parse, urllib.request


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
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
            token_data = json.loads(resp.read())

        body = json.dumps({'access_token': token_data['access_token']}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
