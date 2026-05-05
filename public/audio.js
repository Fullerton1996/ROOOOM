class AudioAnalyzer {
  constructor(onVector) {
    this.onVector = onVector;
    this.context = null;
    this.analyser = null;
    this.history = { energy: [], warmth: [], density: [], laughter_rate: [] };
    this.SMOOTHING = 3;
    this.subWindows = [];
  }

  async start() {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      video: false,
    });
    this.context = new AudioContext();
    const source = this.context.createMediaStreamSource(stream);
    this.analyser = this.context.createAnalyser();
    // Smaller fftSize so the buffer fills quickly even in quiet rooms
    this.analyser.fftSize = 2048;
    this.analyser.smoothingTimeConstant = 0.3;
    source.connect(this.analyser);

    setInterval(() => this._collectSubWindow(), 250);
    setInterval(() => this._processWindow(), 5000);
  }

  _collectSubWindow() {
    if (!this.analyser) return;
    const d = new Float32Array(this.analyser.fftSize);
    this.analyser.getFloatTimeDomainData(d);
    const rms = Math.sqrt(d.reduce((a, v) => a + v * v, 0) / d.length);
    this.subWindows.push(rms);
    if (this.subWindows.length > 20) this.subWindows.shift();
  }

  _energy(td) {
    const rms = Math.sqrt(td.reduce((a, v) => a + v * v, 0) / td.length);
    if (rms < 1e-10) return 0;
    const db = 20 * Math.log10(rms);
    // Wider range: -60dB (near silence) to -10dB (loud room)
    return Math.min(1, Math.max(0, (db - (-60)) / ((-10) - (-60))));
  }

  _warmth(fd) {
    const nyquist = this.context.sampleRate / 2;
    const binHz = nyquist / fd.length;
    let wSum = 0, total = 0;
    for (let i = 0; i < fd.length; i++) {
      const p = fd[i] / 255;
      wSum += i * binHz * p;
      total += p;
    }
    const centroid = total > 0 ? wSum / total : 1000;
    return 1 - Math.min(1, Math.max(0, (centroid - 200) / (4000 - 200)));
  }

  _density(td) {
    const frameSize = 256;
    const zcrs = [];
    for (let i = 0; i + frameSize < td.length; i += frameSize) {
      let c = 0;
      for (let j = i + 1; j < i + frameSize; j++) {
        if ((td[j] >= 0) !== (td[j - 1] >= 0)) c++;
      }
      zcrs.push(c / frameSize);
    }
    if (!zcrs.length) return 0;
    const mean = zcrs.reduce((a, b) => a + b) / zcrs.length;
    const variance = zcrs.reduce((a, v) => a + (v - mean) ** 2, 0) / zcrs.length;
    return Math.min(1, variance / 0.005);
  }

  _laughter() {
    if (this.subWindows.length < 4) return 0;
    const mean = this.subWindows.reduce((a, b) => a + b) / this.subWindows.length;
    if (mean < 1e-6) return 0; // true silence — no laughter possible
    const variance = this.subWindows.reduce((a, v) => a + (v - mean) ** 2, 0) / this.subWindows.length;
    // Normalize relative to the signal level so quiet rooms still register bursts
    const normalised = variance / Math.max(mean * mean * 0.1, 1e-8);
    return Math.min(1, normalised);
  }

  _smooth(key, value) {
    this.history[key].push(value);
    if (this.history[key].length > this.SMOOTHING) this.history[key].shift();
    return this.history[key].reduce((a, b) => a + b) / this.history[key].length;
  }

  _processWindow() {
    if (!this.analyser) return;
    const td = new Float32Array(this.analyser.fftSize);
    const fd = new Uint8Array(this.analyser.fftSize / 2);
    this.analyser.getFloatTimeDomainData(td);
    this.analyser.getByteFrequencyData(fd);

    const vector = {
      energy: this._smooth('energy', this._energy(td)),
      warmth: this._smooth('warmth', this._warmth(fd)),
      density: this._smooth('density', this._density(td)),
      laughter_rate: this._smooth('laughter_rate', this._laughter()),
    };
    Object.keys(vector).forEach(k => {
      vector[k] = Math.round(vector[k] * 10000) / 10000;
    });
    this.onVector(vector);
  }
}
