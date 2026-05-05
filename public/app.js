(() => {
  const sessionTracks = [];
  let currentMood = null;
  let player = null;
  let deviceId = null;
  let accessToken = null;
  let tokenFetchedAt = null;
  let config = null;

  const startBtn = document.getElementById('start-btn');
  const mainUI = document.getElementById('main-ui');
  const moodLabel = document.getElementById('mood-label');
  const pulse = document.getElementById('pulse');
  const vectorDebug = document.getElementById('vector-debug');
  const endBtn = document.getElementById('end-btn');
  const connectionDot = document.getElementById('connection-dot');

  async function getToken() {
    const now = Date.now();
    if (accessToken && tokenFetchedAt && now - tokenFetchedAt < 50 * 60 * 1000) {
      return accessToken;
    }
    const res = await fetch('/api/token');
    const data = await res.json();
    accessToken = data.access_token;
    tokenFetchedAt = now;
    return accessToken;
  }

  async function loadConfig() {
    try {
      const res = await fetch('/api/config');
      config = await res.json();
    } catch (e) {
      console.warn('[app] config fetch failed', e);
    }
  }

  function extractPlaylistId(uri) {
    if (!uri) return null;
    if (uri.startsWith('https://')) {
      return uri.split('/playlist/')[1]?.split('?')[0] ?? null;
    }
    if (uri.startsWith('spotify:playlist:')) {
      const id = uri.replace('spotify:playlist:', '');
      return id === 'FILL_ME' ? null : id;
    }
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
    let tracks = [];
    try {
      tracks = await getPlaylistTracks(playlistId, token);
    } catch (e) {
      console.warn('[app] failed to fetch playlist tracks', e);
    }
    if (!tracks.length) return;

    const stored = sessionStorage.getItem(`idx_${playlistId}`);
    let idx = stored ? parseInt(stored, 10) : Math.floor(Math.random() * tracks.length);
    idx = idx % tracks.length;
    sessionStorage.setItem(`idx_${playlistId}`, (idx + 1) % tracks.length);

    const uris = [
      ...tracks.slice(idx).map(t => t.uri),
      ...tracks.slice(0, idx).map(t => t.uri),
    ];

    await fetch(`https://api.spotify.com/v1/me/player/play?device_id=${deviceId}`, {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ uris }),
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

  async function onMoodChange(mood) {
    currentMood = mood;

    moodLabel.classList.add('transitioning');
    await new Promise(r => setTimeout(r, 600));
    moodLabel.textContent = mood.replace(/_/g, ' ');
    moodLabel.classList.remove('transitioning');

    const moodCfg = config?.moods?.[mood];
    const playlistId = moodCfg ? extractPlaylistId(moodCfg.playlist_uri) : null;
    if (!playlistId) {
      console.log(`[app] no valid playlist for mood: ${mood}`);
      return;
    }

    await fadeVolume(0, 8000);
    await startPlaylist(playlistId);
    await fadeVolume(0.8, 8000);
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

  async function endSession() {
    await fadeVolume(0, 4000);
    if (player) player.pause();

    const phonesRaw = prompt('Enter guest phone numbers (comma-separated):') || '';
    const emailsRaw = prompt('Enter guest emails (comma-separated):') || '';
    const phones = phonesRaw.split(',').map(s => s.trim()).filter(Boolean);
    const emails = emailsRaw.split(',').map(s => s.trim()).filter(Boolean);

    const sessionName = config?.session_name ||
      `${(config?.name || 'Read the Room')} — ${new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}`;

    try {
      const res = await fetch('/api/session/end', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tracks: sessionTracks, session_name: sessionName, contacts: { phones, emails } }),
      });
      const data = await res.json();
      if (data.playlist_url) {
        alert(`Playlist created: ${data.playlist_url}`);
        window.open(data.playlist_url, '_blank');
      } else {
        alert(data.error || 'Session ended, but no playlist URL returned.');
      }
    } catch (e) {
      alert(`Error ending session: ${e.message}`);
    }
  }

  function initSpotifyPlayer(token) {
    player = new Spotify.Player({
      name: 'ROOOOM',
      getOAuthToken: cb => {
        getToken().then(cb);
      },
      volume: 0.8,
    });

    player.addListener('ready', ({ device_id }) => {
      deviceId = device_id;
      pulse.classList.remove('inactive');
      connectionDot.classList.add('connected');
      console.log('[app] Spotify player ready, device:', device_id);
    });

    player.addListener('not_ready', ({ device_id }) => {
      deviceId = null;
      pulse.classList.add('inactive');
      connectionDot.classList.remove('connected');
      console.warn('[app] Spotify player not ready, device:', device_id);
    });

    player.addListener('player_state_changed', state => {
      if (!state) return;
      logTrack(state);
    });

    player.addListener('initialization_error', ({ message }) => {
      console.error('[app] Spotify init error:', message);
    });

    player.addListener('authentication_error', ({ message }) => {
      console.error('[app] Spotify auth error:', message);
    });

    player.addListener('account_error', ({ message }) => {
      console.error('[app] Spotify account error:', message);
    });

    player.connect();
  }

  async function startSession() {
    startBtn.style.display = 'none';
    mainUI.style.display = 'block';
    moodLabel.textContent = '—';

    await loadConfig();

    const analyzer = new AudioAnalyzer(vector => {
      vectorDebug.textContent =
        `energy ${vector.energy.toFixed(2)}  ·  warmth ${vector.warmth.toFixed(2)}  ·  ` +
        `density ${vector.density.toFixed(2)}  ·  laughter ${vector.laughter_rate.toFixed(2)}`;
      classifier.classify(vector);
    });

    const classifier = new MoodClassifier(mood => {
      onMoodChange(mood);
    });

    try {
      await analyzer.start();
    } catch (e) {
      alert(`Microphone access denied: ${e.message}`);
      startBtn.style.display = '';
      mainUI.style.display = 'none';
      return;
    }

    try {
      const token = await getToken();
      initSpotifyPlayer(token);
    } catch (e) {
      console.error('[app] Failed to init Spotify player:', e);
    }
  }

  window.onSpotifyWebPlaybackSDKReady = () => {
    console.log('[app] Spotify SDK ready');
  };

  startBtn.addEventListener('click', startSession);
  endBtn.addEventListener('click', endSession);

  window.roooom = {
    play: () => player?.resume(),
    pause: () => player?.pause(),
    resume: () => player?.resume(),
    endSession,
    getState: () => ({
      currentMood,
      sessionTracks: [...sessionTracks],
      deviceId,
      tokenAge: tokenFetchedAt ? Math.round((Date.now() - tokenFetchedAt) / 1000) + 's' : null,
    }),
  };
})();
