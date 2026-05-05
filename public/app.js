(() => {
  const sessionTracks = [];
  let currentMood = null;
  let player = null;
  let deviceId = null;
  let config = null;

  const startBtn = document.getElementById('start-btn');
  const spotifyBtn = document.getElementById('spotify-btn');
  const mainUI = document.getElementById('main-ui');
  const moodLabel = document.getElementById('mood-label');
  const pulse = document.getElementById('pulse');
  const vectorDebug = document.getElementById('vector-debug');
  const endBtn = document.getElementById('end-btn');
  const connectionDot = document.getElementById('connection-dot');

  // ── PKCE Auth ───────────────────────────────────────────────────────────────

  async function generatePKCE() {
    const verifier = Array.from(crypto.getRandomValues(new Uint8Array(48)))
      .map(b => b.toString(16).padStart(2, '0')).join('');
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
    const challenge = btoa(String.fromCharCode(...new Uint8Array(digest)))
      .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
    return { verifier, challenge };
  }

  async function startSpotifyLogin() {
    if (!config) config = await fetch('/api/config').then(r => r.json());
    const { verifier, challenge } = await generatePKCE();
    const redirectUri = `${location.origin}/callback`;

    sessionStorage.setItem('pkce_verifier', verifier);
    sessionStorage.setItem('spotify_client_id', config.spotify_client_id);
    sessionStorage.setItem('spotify_redirect_uri', redirectUri);

    const scopes = [
      'streaming', 'user-read-email', 'user-read-private',
      'user-read-playback-state', 'user-modify-playback-state',
      'playlist-modify-public', 'playlist-modify-private',
    ].join(' ');

    const params = new URLSearchParams({
      client_id: config.spotify_client_id,
      response_type: 'code',
      redirect_uri: redirectUri,
      code_challenge_method: 'S256',
      code_challenge: challenge,
      scope: scopes,
    });

    window.location = `https://accounts.spotify.com/authorize?${params}`;
  }

  async function getToken() {
    const expiresAt = parseInt(sessionStorage.getItem('spotify_token_expires_at') || '0');
    if (Date.now() < expiresAt - 60000) {
      return sessionStorage.getItem('spotify_access_token');
    }
    // Refresh using stored refresh token
    const refreshToken = sessionStorage.getItem('spotify_refresh_token');
    const clientId = sessionStorage.getItem('spotify_client_id');
    if (!refreshToken || !clientId) return null;

    const res = await fetch('https://accounts.spotify.com/api/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        client_id: clientId,
        grant_type: 'refresh_token',
        refresh_token: refreshToken,
      }),
    });
    const data = await res.json();
    if (data.access_token) {
      sessionStorage.setItem('spotify_access_token', data.access_token);
      sessionStorage.setItem('spotify_token_expires_at', Date.now() + data.expires_in * 1000);
      if (data.refresh_token) sessionStorage.setItem('spotify_refresh_token', data.refresh_token);
    }
    return data.access_token || null;
  }

  function isLoggedIn() {
    return !!sessionStorage.getItem('spotify_access_token');
  }

  // ── Playlist / Playback ─────────────────────────────────────────────────────

  function extractPlaylistId(uri) {
    if (!uri || uri.includes('FILL_ME')) return null;
    if (uri.startsWith('https://')) return uri.split('/playlist/')[1]?.split('?')[0] ?? null;
    if (uri.startsWith('spotify:playlist:')) return uri.replace('spotify:playlist:', '');
    return null;
  }

  async function getPlaylistTracks(playlistId, token) {
    const res = await fetch(
      `https://api.spotify.com/v1/playlists/${playlistId}/tracks?limit=100&fields=items(track(uri,name,artists))`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    const data = await res.json();
    return (data.items || []).map(i => i.track).filter(Boolean);
  }

  async function startPlaylist(playlistId) {
    if (!deviceId || !playlistId) return;
    const token = await getToken();
    if (!token) return;
    const tracks = await getPlaylistTracks(playlistId, token).catch(() => []);
    if (!tracks.length) return;

    const stored = sessionStorage.getItem(`idx_${playlistId}`);
    let idx = stored ? parseInt(stored, 10) : Math.floor(Math.random() * tracks.length);
    idx = idx % tracks.length;
    sessionStorage.setItem(`idx_${playlistId}`, (idx + 1) % tracks.length);

    await fetch(`https://api.spotify.com/v1/me/player/play?device_id=${deviceId}`, {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ uris: [...tracks.slice(idx), ...tracks.slice(0, idx)].map(t => t.uri) }),
    });
  }

  async function fadeVolume(target, durationMs) {
    if (!player) return;
    const steps = 40;
    const stepMs = durationMs / steps;
    const start = await player.getVolume();
    const delta = (target - start) / steps;
    for (let i = 0; i <= steps; i++) {
      await player.setVolume(Math.min(1, Math.max(0, start + delta * i)));
      await new Promise(r => setTimeout(r, stepMs));
    }
  }

  let pendingPlaylistId = null;   // set on mood change, consumed at next track transition
  let transitionInProgress = false;
  let lastTrackUri = null;

  async function onMoodChange(mood) {
    currentMood = mood;
    moodLabel.classList.add('transitioning');
    await new Promise(r => setTimeout(r, 600));
    moodLabel.textContent = mood.replace(/_/g, ' ');
    moodLabel.classList.remove('transitioning');
    // Queue the new playlist — it will start at the next natural track ending
    pendingPlaylistId = extractPlaylistId(config?.moods?.[mood]?.playlist_uri);
  }

  async function handleTrackEnding(timeLeftMs) {
    if (transitionInProgress) return;
    transitionInProgress = true;

    // Fade out over whatever time is left (min 3s so it doesn't snap)
    await fadeVolume(0, Math.max(timeLeftMs - 500, 3000));

    const nextId = pendingPlaylistId || extractPlaylistId(config?.moods?.[currentMood]?.playlist_uri);
    pendingPlaylistId = null;

    if (nextId) await startPlaylist(nextId);

    await fadeVolume(0.8, 4000);
    transitionInProgress = false;
  }

  function logTrack(state) {
    const track = state?.track_window?.current_track;
    if (!track) return;
    if (sessionTracks.length && sessionTracks[sessionTracks.length - 1].uri === track.uri) return;
    sessionTracks.push({
      uri: track.uri,
      name: track.name,
      artist: track.artists?.[0]?.name ?? '',
      mood: currentMood,
      timestamp: new Date().toISOString(),
    });
  }

  // ── Session End ─────────────────────────────────────────────────────────────

  async function endSession() {
    await fadeVolume(0, 4000);
    if (player) player.pause();

    const phonesRaw = prompt('Guest phone numbers (comma-separated, or leave blank):') || '';
    const emailsRaw = prompt('Guest emails (comma-separated, or leave blank):') || '';
    const phones = phonesRaw.split(',').map(s => s.trim()).filter(Boolean);
    const emails = emailsRaw.split(',').map(s => s.trim()).filter(Boolean);
    const sessionName = `Read the Room — ${new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}`;
    const token = await getToken();

    try {
      const res = await fetch('/api/session/end', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tracks: sessionTracks, session_name: sessionName, contacts: { phones, emails }, access_token: token }),
      });
      const data = await res.json();
      if (data.playlist_url) {
        alert(`Playlist created: ${data.playlist_url}`);
        window.open(data.playlist_url, '_blank');
      } else {
        alert(data.error || 'Session ended.');
      }
    } catch (e) {
      alert(`Error: ${e.message}`);
    }
  }

  // ── Spotify Player ──────────────────────────────────────────────────────────

  function initSpotifyPlayer() {
    player = new Spotify.Player({
      name: 'ROOOOM',
      getOAuthToken: cb => getToken().then(t => cb(t)),
      volume: 0.8,
    });

    player.addListener('ready', async ({ device_id }) => {
      deviceId = device_id;
      pulse.classList.remove('inactive');
      connectionDot.classList.add('connected');
      // Start arrival playlist immediately — don't wait for mood classifier
      currentMood = 'arrival';
      moodLabel.textContent = 'arrival';
      const arrivalId = extractPlaylistId(config?.moods?.arrival?.playlist_uri);
      if (arrivalId) await startPlaylist(arrivalId);
    });

    player.addListener('not_ready', () => {
      deviceId = null;
      pulse.classList.add('inactive');
      connectionDot.classList.remove('connected');
    });

    player.addListener('player_state_changed', state => {
      if (!state) return;
      logTrack(state);

      // Reset transition flag when a new track starts
      const uri = state.track_window?.current_track?.uri;
      if (uri && uri !== lastTrackUri) {
        lastTrackUri = uri;
        transitionInProgress = false;
      }

      // When a track is within 15 seconds of ending, start the crossfade
      if (!state.paused && !transitionInProgress) {
        const timeLeft = state.duration - state.position;
        if (timeLeft > 0 && timeLeft < 15000) {
          handleTrackEnding(timeLeft);
        }
      }
    });
    player.addListener('initialization_error', ({ message }) => console.error('[spotify]', message));
    player.addListener('authentication_error', ({ message }) => console.error('[spotify] auth:', message));
    player.addListener('account_error', ({ message }) => console.error('[spotify] account:', message));
    player.connect();
  }

  // ── Boot ────────────────────────────────────────────────────────────────────

  async function startSession() {
    startBtn.style.display = 'none';
    mainUI.style.display = 'block';
    moodLabel.textContent = '—';

    const analyzer = new AudioAnalyzer(vector => {
      vectorDebug.textContent =
        `energy ${vector.energy.toFixed(2)}  ·  warmth ${vector.warmth.toFixed(2)}  ·  ` +
        `density ${vector.density.toFixed(2)}  ·  laughter ${vector.laughter_rate.toFixed(2)}`;
      classifier.classify(vector);
    });

    const classifier = new MoodClassifier(mood => onMoodChange(mood));

    try {
      await analyzer.start();
    } catch (e) {
      alert(`Microphone access denied: ${e.message}`);
      startBtn.style.display = '';
      mainUI.style.display = 'none';
      return;
    }

    initSpotifyPlayer();
  }

  window.onSpotifyWebPlaybackSDKReady = () => {};

  async function boot() {
    config = await fetch('/api/config').then(r => r.json()).catch(() => null);

    if (isLoggedIn()) {
      spotifyBtn.style.display = 'none';
      startBtn.style.display = '';
    } else {
      startBtn.style.display = 'none';
      spotifyBtn.style.display = '';
    }
  }

  spotifyBtn.addEventListener('click', startSpotifyLogin);
  startBtn.addEventListener('click', startSession);
  endBtn.addEventListener('click', endSession);

  window.roooom = {
    pause: () => player?.pause(),
    resume: () => player?.resume(),
    endSession,
    getState: () => ({ currentMood, sessionTracks: [...sessionTracks], deviceId }),
  };

  boot();
})();
