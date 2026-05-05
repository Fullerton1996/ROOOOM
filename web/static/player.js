const CROSSFADE_MS = 8000;
const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

let spotifyPlayer = null;
let deviceId = null;
let ws = null;
let currentMood = null;
let crossfadeInProgress = false;
let _cachedToken = null;

async function fetchToken() {
  if (_cachedToken) return _cachedToken;
  const res = await fetch("/token");
  const data = await res.json();
  _cachedToken = data.access_token;
  // Refresh before expiry (tokens last 1hr — refresh every 50min)
  setTimeout(() => { _cachedToken = null; }, 50 * 60 * 1000);
  return _cachedToken;
}

// ── Spotify Web Playback SDK ────────────────────────────────────────────────

window.onSpotifyWebPlaybackSDKReady = () => {
  spotifyPlayer = new Spotify.Player({
    name: "Read the Room",
    getOAuthToken: async (cb) => cb(await fetchToken()),
    volume: 0.8,
  });

  spotifyPlayer.addListener("ready", ({ device_id }) => {
    deviceId = device_id;
    console.log("[spotify] ready, device_id:", device_id);
    document.getElementById("pulse").classList.remove("inactive");
  });

  spotifyPlayer.addListener("not_ready", ({ device_id }) => {
    console.warn("[spotify] device went offline:", device_id);
    deviceId = null;
    document.getElementById("pulse").classList.add("inactive");
  });

  spotifyPlayer.addListener("player_state_changed", (state) => {
    if (!state) return;
    // Notify Python backend of the now-playing track for session logging
    if (ws && ws.readyState === WebSocket.OPEN) {
      const track = state.track_window?.current_track;
      if (track) {
        ws.send(JSON.stringify({
          type: "track_playing",
          uri: track.uri,
          name: track.name,
          artist: track.artists?.[0]?.name ?? "",
        }));
      }
    }
  });

  spotifyPlayer.addListener("initialization_error", ({ message }) => console.error("[spotify] init error:", message));
  spotifyPlayer.addListener("authentication_error", ({ message }) => console.error("[spotify] auth error:", message));
  spotifyPlayer.addListener("account_error", ({ message }) => console.error("[spotify] account error:", message));

  spotifyPlayer.connect();
};

// ── Crossfade + mood transition ─────────────────────────────────────────────

async function handleMoodChange(mood, vector) {
  if (mood === currentMood || crossfadeInProgress) return;
  crossfadeInProgress = true;

  const label = document.getElementById("mood-label");
  label.classList.add("transitioning");

  await fadeVolume(0, CROSSFADE_MS);

  // Signal Python to switch playlist (Python selects the track and calls play_track)
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "request_playlist_switch", mood }));
  }

  currentMood = mood;
  label.textContent = mood.replace(/_/g, " ");

  // Wait for Python to confirm playback started before fading back in
  await new Promise((resolve) => setTimeout(resolve, 1500));
  label.classList.remove("transitioning");
  await fadeVolume(0.8, CROSSFADE_MS);

  crossfadeInProgress = false;
}

async function fadeVolume(targetVolume, durationMs) {
  if (!spotifyPlayer) return;

  const state = await spotifyPlayer.getCurrentState();
  const startVolume = state ? (await spotifyPlayer.getVolume()) : 0.8;
  const steps = 40;
  const stepMs = durationMs / steps;
  const delta = (targetVolume - startVolume) / steps;

  for (let i = 0; i <= steps; i++) {
    const v = Math.min(1, Math.max(0, startVolume + delta * i));
    await spotifyPlayer.setVolume(v);
    await new Promise((resolve) => setTimeout(resolve, stepMs));
  }
}

// ── WebSocket ───────────────────────────────────────────────────────────────

function connectWS() {
  ws = new WebSocket(WS_URL);
  const dot = document.getElementById("connection-dot");

  ws.onopen = () => {
    dot.classList.add("connected");
    console.log("[ws] connected");
  };

  ws.onmessage = (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch { return; }

    if (msg.type === "mood_change") {
      handleMoodChange(msg.mood, msg.vector);
      updateVectorDebug(msg.vector);
    }
  };

  ws.onclose = () => {
    dot.classList.remove("connected");
    console.warn("[ws] disconnected — reconnecting in 3s");
    setTimeout(connectWS, 3000);
  };

  ws.onerror = (err) => console.error("[ws] error:", err);
}

function updateVectorDebug(vector) {
  if (!vector) return;
  const el = document.getElementById("vector-debug");
  el.textContent = Object.entries(vector)
    .map(([k, v]) => `${k} ${Number(v).toFixed(2)}`)
    .join("  ·  ");
}

// ── Public API (callable from console for testing) ──────────────────────────

window.roooom = {
  play: (trackUri) => {
    if (!deviceId) return console.error("No Spotify device ready");
    fetch(`https://api.spotify.com/v1/me/player/play?device_id=${deviceId}`, {
      method: "PUT",
      headers: { Authorization: `Bearer ${SPOTIFY_ACCESS_TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({ uris: [trackUri] }),
    });
  },
  pause: () => spotifyPlayer?.pause(),
  resume: () => spotifyPlayer?.resume(),
  next: () => spotifyPlayer?.nextTrack(),
  getState: () => spotifyPlayer?.getCurrentState(),
};

connectWS();
