from http.server import BaseHTTPRequestHandler
import os, urllib.parse

SCOPES = " ".join([
    "streaming",
    "user-read-email",
    "user-read-private",
    "user-read-playback-state",
    "user-modify-playback-state",
    "playlist-modify-public",
    "playlist-modify-private",
])


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        client_id = os.environ["SPOTIFY_CLIENT_ID"]
        redirect_uri = os.environ["SPOTIFY_REDIRECT_URI"]

        params = urllib.parse.urlencode({
            "response_type": "code",
            "client_id": client_id,
            "scope": SCOPES,
            "redirect_uri": redirect_uri,
        })

        url = f"https://accounts.spotify.com/authorize?{params}"

        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()
