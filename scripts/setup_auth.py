"""
Run once locally to get a Spotify refresh token.

    pip install spotipy python-dotenv
    python scripts/setup_auth.py

Then add the printed token to Vercel:

    vercel env add SPOTIFY_REFRESH_TOKEN
"""

import os
from dotenv import load_dotenv
import spotipy.oauth2 as oauth2

load_dotenv()

SCOPES = ' '.join([
    'streaming',
    'user-read-email',
    'user-read-private',
    'user-read-playback-state',
    'user-modify-playback-state',
    'playlist-modify-public',
    'playlist-modify-private',
])

REDIRECT_URI = 'http://localhost:8888/callback'

client_id = os.environ.get('SPOTIFY_CLIENT_ID') or input('SPOTIFY_CLIENT_ID: ').strip()
client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET') or input('SPOTIFY_CLIENT_SECRET: ').strip()

sp_oauth = oauth2.SpotifyOAuth(
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri=REDIRECT_URI,
    scope=SCOPES,
    open_browser=True,
)

print('\nOpening Spotify login in your browser...')
print('If it does not open automatically, visit this URL:\n')
auth_url = sp_oauth.get_authorize_url()
print(auth_url)
print()

redirected = input('Paste the full redirect URL here: ').strip()
code = sp_oauth.parse_response_code(redirected)
token_info = sp_oauth.get_access_token(code, as_dict=True)
refresh_token = token_info['refresh_token']

print('\n' + '=' * 60)
print('SPOTIFY_REFRESH_TOKEN:')
print(refresh_token)
print('=' * 60)
print('\nAdd this to Vercel with:')
print('  vercel env add SPOTIFY_REFRESH_TOKEN')
print()
