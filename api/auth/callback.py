from http.server import BaseHTTPRequestHandler
import base64, json, os, urllib.parse, urllib.request


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        error = params.get("error", [None])[0]
        if error:
            self._respond_html(f"<h2>Auth failed: {error}</h2>")
            return

        code = params.get("code", [None])[0]
        if not code:
            self._respond_html("<h2>No code returned from Spotify.</h2>")
            return

        client_id = os.environ["SPOTIFY_CLIENT_ID"]
        client_secret = os.environ["SPOTIFY_CLIENT_SECRET"]
        redirect_uri = os.environ["SPOTIFY_REDIRECT_URI"]

        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        data = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }).encode()

        req = urllib.request.Request(
            "https://accounts.spotify.com/api/token",
            data=data,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )

        try:
            with urllib.request.urlopen(req) as resp:
                token_data = json.loads(resp.read())
        except Exception as e:
            self._respond_html(f"<h2>Token exchange failed: {e}</h2>")
            return

        refresh_token = token_data.get("refresh_token", "")

        html = f"""<!DOCTYPE html>
<html>
<head>
  <title>Spotify Connected — ROOOOM</title>
  <style>
    body {{ background: #0a0a0a; color: #e0e0e0; font-family: -apple-system, sans-serif;
            display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
    .card {{ max-width: 560px; text-align: center; padding: 2rem; }}
    h1 {{ font-weight: 300; font-size: 1.8rem; margin-bottom: 0.5rem; }}
    p {{ color: #888; line-height: 1.6; }}
    .token {{ background: #1a1a1a; border: 1px solid #333; border-radius: 8px;
              padding: 1rem; font-family: monospace; font-size: 0.8rem;
              word-break: break-all; color: #4ade80; margin: 1.5rem 0; text-align: left; }}
    .step {{ background: #111; border-radius: 8px; padding: 1rem 1.2rem;
             margin: 0.75rem 0; text-align: left; font-size: 0.9rem; }}
    .step strong {{ color: #fff; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Spotify connected.</h1>
    <p>Copy the token below and add it to your Vercel project.</p>
    <div class="token">{refresh_token}</div>
    <div class="step"><strong>1.</strong> Go to your Vercel project → Settings → Environment Variables</div>
    <div class="step"><strong>2.</strong> Add a new variable: <strong>SPOTIFY_REFRESH_TOKEN</strong></div>
    <div class="step"><strong>3.</strong> Paste the token above as the value</div>
    <div class="step"><strong>4.</strong> Redeploy the project</div>
    <p style="margin-top:2rem; font-size:0.8rem; color:#555;">
      You only need to do this once. The token doesn't expire unless you revoke Spotify access.
    </p>
  </div>
</body>
</html>"""

        self._respond_html(html)

    def _respond_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)
