class MoodClassifier {
  constructor(onMoodChange) {
    this.onMoodChange = onMoodChange;
    this.currentMood = null;
    this.candidateMood = null;
    this.candidateSince = null;
    this.config = null;
    this._loadConfig();
    setInterval(() => this._loadConfig(), 5000);
  }

  async _loadConfig() {
    try {
      const res = await fetch('/api/config');
      this.config = await res.json();
    } catch (e) {
      console.warn('[mood] config fetch failed', e);
    }
  }

  classify(vector) {
    if (!this.config) return this.currentMood || 'arrival';
    const moods = this.config.moods || {};
    const defaultHysteresis = this.config.hysteresis_seconds || 45;
    const now = Date.now() / 1000;

    if (this.currentMood === 'afterglow') {
      const cfg = moods.afterglow || {};
      if (cfg.sticky && vector.energy < (cfg.sticky_exit_energy ?? 0.5)) return 'afterglow';
    }

    const candidates = Object.entries(moods)
      .filter(([, cfg]) =>
        vector.energy <= (cfg.energy_max ?? 1) &&
        vector.density <= (cfg.density_max ?? 1) &&
        vector.warmth >= (cfg.warmth_min ?? 0)
      )
      .sort((a, b) => (a[1].priority ?? 99) - (b[1].priority ?? 99));

    if (!candidates.length) return this.currentMood || 'arrival';
    const best = candidates[0][0];

    if (best === this.currentMood) {
      this.candidateMood = null;
      this.candidateSince = null;
      return this.currentMood;
    }

    if (best !== this.candidateMood) {
      this.candidateMood = best;
      this.candidateSince = now;
    }

    const hysteresis = moods[best]?.hysteresis_seconds ?? defaultHysteresis;
    const stable = now - this.candidateSince;

    if (stable >= hysteresis) {
      const old = this.currentMood;
      this.currentMood = best;
      this.candidateMood = null;
      this.candidateSince = null;
      console.log(`[mood] ${old} → ${this.currentMood} (stable ${stable.toFixed(0)}s)`);
      this.onMoodChange(this.currentMood);
    }

    return this.currentMood || best;
  }
}
