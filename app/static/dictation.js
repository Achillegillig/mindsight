const MAX_DICTATION_SECONDS = 30;
const DICTATION_SAMPLE_RATE = 16000;
const MICROPHONE_SIGNAL_THRESHOLD = 0.002;
const AUTO_VOICE_THRESHOLD = 0.006;
const AUTO_PAUSE_SECONDS = 1.8;
const AUTO_CALIBRATION_SECONDS = 0.6;
const AUTO_NOISE_WINDOW_SECONDS = 1.2;

function microphoneLevel(samples) {
  let power = 0;
  for (const sample of samples) power += sample * sample;
  return Math.sqrt(power / samples.length);
}

function updateNoiseFloor(run, level, duration) {
  const count = Math.ceil(AUTO_NOISE_WINDOW_SECONDS / duration);
  run.background.push(level);
  if (run.background.length > count) run.background.shift();
  const levels = [...run.background].sort((left, right) => left - right);
  const low = levels[Math.floor((levels.length - 1) * 0.2)];
  if (run.noiseFloor === undefined) {
    run.noiseFloor = low;
    return;
  }
  if (levels.length < count) return;

  const high = levels[Math.floor((levels.length - 1) * 0.85)];
  if (low < run.noiseFloor) {
    run.noiseFloor += (low - run.noiseFloor) * Math.min(1, duration * 4);
  } else if (low > Math.max(AUTO_VOICE_THRESHOLD / 2, run.noiseFloor * 1.25)
      && high <= low * 1.5) {
    // A stable rise over the whole window is a new background level.
    run.noiseFloor = low;
    if (run.firstVoice >= run.chunks.length - count - 1) {
      run.firstVoice = undefined;
      run.voiced = 0;
    }
  }
}

async function encodeDictation(chunks, sampleRate) {
  const length = Math.min(chunks.reduce((total, chunk) => total + chunk.length, 0),
    MAX_DICTATION_SECONDS * sampleRate);
  const frames = Math.floor(length * DICTATION_SAMPLE_RATE / sampleRate);
  if (!frames) return null;

  const context = new OfflineAudioContext(1, frames, DICTATION_SAMPLE_RATE);
  const original = context.createBuffer(1, length, sampleRate);
  let offset = 0;
  for (const chunk of chunks) {
    const part = chunk.subarray(0, length - offset);
    original.copyToChannel(part, 0, offset);
    offset += part.length;
    if (offset === length) break;
  }
  const source = context.createBufferSource();
  source.buffer = original;
  source.connect(context.destination);
  source.start();
  const samples = (await context.startRendering()).getChannelData(0);

  const wav = new DataView(new ArrayBuffer(44 + samples.length * 2));
  for (const [position, text] of [[0, "RIFF"], [8, "WAVEfmt "], [36, "data"]]) {
    for (let index = 0; index < text.length; index++) {
      wav.setUint8(position + index, text.charCodeAt(index));
    }
  }
  wav.setUint32(4, wav.byteLength - 8, true);
  wav.setUint32(16, 16, true);
  wav.setUint16(20, 1, true);
  wav.setUint16(22, 1, true);
  wav.setUint32(24, DICTATION_SAMPLE_RATE, true);
  wav.setUint32(28, DICTATION_SAMPLE_RATE * 2, true);
  wav.setUint16(32, 2, true);
  wav.setUint16(34, 16, true);
  wav.setUint32(40, samples.length * 2, true);
  samples.forEach((sample, index) => {
    wav.setInt16(44 + index * 2, Math.max(-32768, Math.min(32767, sample * 32768)), true);
  });
  return new Blob([wav], { type: "audio/wav" });
}

function createDictation(answer, send, questionVoice) {
  const button = document.querySelector("#dictate");
  const status = document.querySelector("#dictation-status");
  const supported = Boolean(navigator.mediaDevices?.getUserMedia && window.AudioContext
    && window.AudioWorkletNode && window.OfflineAudioContext);
  let available = false;
  let blocked = true;
  let current;

  function updateControls() {
    button.hidden = !available;
    button.disabled = blocked || !supported || Boolean(current && current.state !== "recording");
    const recording = current?.state === "recording";
    const automatic = recording && current.automatic;
    button.setAttribute("aria-label", recording ? (automatic ? "Terminer ma réponse" : "Arrêter la dictée") : "Dicter");
    button.toggleAttribute("data-auto-recording", automatic);
    button.toggleAttribute("data-recording", recording);
    send.disabled = blocked || Boolean(current);
  }

  function releaseMicrophone(run) {
    clearTimeout(run.timer);
    run.stream?.getTracks().forEach((track) => track.stop());
    run.stream = undefined;
    if (run.context && run.context.state !== "closed") void run.context.close().catch(() => {});
    run.context = undefined;
  }

  function finish(run, message, ready = false) {
    if (current !== run) return;
    current = undefined;
    releaseMicrophone(run);
    status.textContent = message;
    updateControls();
    run.resolve(ready);
  }

  async function submitAudio(run) {
    if (current !== run || run.state !== "transcribing") return;
    run.state = "uploading";
    const sampleRate = run.context.sampleRate;
    releaseMicrophone(run);
    if (run.firstSignal === undefined) {
      finish(run, "Aucun signal audible. Vérifie que le bon micro est sélectionné et qu’il n’est pas coupé.");
      return;
    }
    const preRoll = Math.ceil(0.2 * sampleRate / run.chunks[0].length);
    const start = run.voiced >= 0.16 ? run.firstVoice : run.firstSignal;
    const speechChunks = run.chunks.slice(Math.max(0, start - preRoll));
    try {
      const audio = await encodeDictation(speechChunks, sampleRate);
      if (current !== run) return;
      if (!audio) {
        finish(run, "Aucun son n’a été enregistré.");
        return;
      }
      const response = await fetch("/api/speech/transcribe", {
        method: "POST",
        headers: { "Content-Type": "audio/wav" },
        body: audio,
        signal: run.abort.signal,
      });
      const result = await response.json();
      if (current !== run) return;
      if (!response.ok) {
        finish(run, result.detail || "La transcription a échoué.");
        return;
      }
      if (!result.text) {
        finish(run, "Du son a été capté, mais Azure n’a reconnu aucune parole. Essaie une phrase entière près du micro.");
        return;
      }
      const separator = answer.value && !/\s$/.test(answer.value) ? " " : "";
      const remaining = answer.maxLength - answer.value.length;
      if (remaining <= separator.length) {
        finish(run, "Le champ de réponse est plein.");
        return;
      }
      const addition = separator + result.text;
      answer.value += addition.slice(0, remaining);
      answer.dispatchEvent(new Event("input", { bubbles: true }));
      finish(run, addition.length > remaining
        ? "La transcription a été raccourcie à la limite du champ."
        : "", addition.length <= remaining);
    } catch {
      finish(run, "La transcription a échoué. Tu peux réessayer.");
    }
  }

  function stop() {
    const run = current;
    if (run?.state !== "recording") return;
    clearTimeout(run.timer);
    run.state = "transcribing";
    status.textContent = "Transcription en cours…";
    updateControls();
    run.timer = setTimeout(() => void submitAudio(run), 500);
    run.node.port.postMessage("flush");
  }

  function detectPause(run, level, duration) {
    run.elapsed += duration;
    if (run.elapsed <= AUTO_CALIBRATION_SECONDS) {
      run.background.push(level);
      return;
    }
    updateNoiseFloor(run, level, duration);
    const speaking = run.voiced >= 0.16;
    const threshold = Math.max(AUTO_VOICE_THRESHOLD, run.noiseFloor * (speaking ? 1.5 : 1.9));
    if (level >= threshold) {
      run.voiced += duration;
      run.silence = 0;
      run.firstVoice ??= run.chunks.length - 1;
    } else {
      run.silence += duration;
      if (!speaking && run.silence >= 0.25) {
        run.voiced = 0;
        run.firstVoice = undefined;
      }
    }
    if (speaking && run.silence >= AUTO_PAUSE_SECONDS) stop();
    else if (!speaking && run.elapsed >= 12) {
      finish(run, "Aucune voix détectée au-dessus du bruit ambiant. Rapproche-toi du micro ou termine ta réponse manuellement au prochain essai.");
    }
  }

  async function record(automatic = false) {
    if (blocked || current || !available || !supported) return false;
    const run = {
      state: "starting", automatic, chunks: [], elapsed: 0, background: [],
      voiced: 0, silence: 0, abort: new AbortController(),
    };
    const result = new Promise((resolve) => { run.resolve = resolve; });
    current = run;
    updateControls();
    status.textContent = "";
    try {
      run.context = new AudioContext();
      const resuming = run.context.resume();
      // Handle a context closed by a reset while the permission dialog is open.
      void resuming.catch(() => {});
      run.stream = await navigator.mediaDevices.getUserMedia({
        audio: { noiseSuppression: true, echoCancellation: true },
      });
      if (current !== run) {
        releaseMicrophone(run);
        return;
      }
      await resuming;
      await run.context.audioWorklet.addModule("/static/microphone.js");
      if (current !== run) return;
      questionVoice.stopPlayback();
      const [track] = run.stream.getAudioTracks();
      track.addEventListener("ended", () => finish(run, "Le microphone a été déconnecté."), { once: true });
      run.node = new AudioWorkletNode(run.context, "microphone-recorder", {
        channelCount: 1, channelCountMode: "explicit",
      });
      run.node.port.onmessage = ({ data }) => {
        if (current !== run) return;
        if (data) {
          const level = microphoneLevel(data);
          if (run.firstSignal === undefined && level >= MICROPHONE_SIGNAL_THRESHOLD) {
            run.firstSignal = run.chunks.length;
          }
          run.chunks.push(data);
          if (automatic && run.state === "recording") {
            detectPause(run, level, data.length / run.context.sampleRate);
          }
        } else if (run.state === "transcribing") void submitAudio(run);
      };
      const source = run.context.createMediaStreamSource(run.stream);
      source.connect(run.node).connect(run.context.destination);
      run.state = "recording";
      run.timer = setTimeout(stop, MAX_DICTATION_SECONDS * 1000);
      updateControls();
    } catch (error) {
      const errors = {
        NotAllowedError: "Accès au microphone refusé. Autorise-le dans les paramètres du site.",
        NotFoundError: "Aucun microphone détecté. Branche un micro ou sélectionne une entrée audio.",
        NotReadableError: "Le microphone est inaccessible. Vérifie les réglages audio et les applications qui l’utilisent.",
      };
      finish(run, errors[error.name] || "Impossible de démarrer le microphone.");
    }
    return result;
  }

  function cancel() {
    if (!current) {
      if (supported) status.textContent = "";
      return;
    }
    current.abort.abort();
    finish(current, "");
  }

  button.addEventListener("click", () => {
    if (current?.state === "recording") stop();
    else void record();
  });
  window.addEventListener("pagehide", cancel);

  return {
    cancel,
    record,
    get supported() {
      return supported;
    },
    setAvailable(value) {
      available = Boolean(value);
      if (available && !supported) {
        status.textContent = "La dictée requiert un navigateur compatible sur HTTPS ou localhost.";
      }
      updateControls();
    },
    setBlocked(value) {
      blocked = value;
      updateControls();
    },
    get active() {
      return Boolean(current);
    },
  };
}
