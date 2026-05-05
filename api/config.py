from http.server import BaseHTTPRequestHandler
import json, os, yaml


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        root = os.path.join(os.path.dirname(__file__), '..')
        with open(os.path.join(root, 'moods.yaml')) as f:
            config = yaml.safe_load(f)
        body = json.dumps(config).encode()
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
