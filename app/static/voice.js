function createQuestionVoice() {
  const toggle = document.querySelector("#voice-toggle");
  const toggleState = toggle.querySelector("span");
  const replay = document.querySelector("#voice-replay");
  const status = document.querySelector("#voice-status");
  const synthesis = window.speechSynthesis;
  const browserVoice = Boolean(synthesis && window.SpeechSynthesisUtterance);
  let azureVoice = false;
  let enabled = false;
  let automatic = false;
  let question = "";
  let currentSpeech = null;
  let request = null;
  let audio = null;
  let audioUrl = "";
  let cachedAudio = null;

  function stop() {
    request?.abort();
    request = null;
    if (audio) audio.pause();
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    audio = null;
    audioUrl = "";
    if (currentSpeech) {
      currentSpeech = null;
      synthesis.cancel();
    }
  }

  function speakInBrowser(text, signal, azureError = "") {
    if (!browserVoice) {
      status.textContent = azureError || "Lecture vocale indisponible.";
      return false;
    }
    const frenchVoices = synthesis.getVoices().filter((voice) => /^fr(?:-|_|$)/i.test(voice.lang));
    const voice = frenchVoices.find((voice) => voice.localService) ?? frenchVoices[0];
    const speech = new window.SpeechSynthesisUtterance(text);
    speech.lang = voice?.lang ?? "fr-FR";
    if (voice) speech.voice = voice;

    return new Promise((resolve) => {
      currentSpeech = speech;
      speech.onend = () => resolve(true);
      speech.onerror = () => {
        if (!signal.aborted) {
          status.textContent = azureError
            ? `${azureError} La voix du navigateur a également échoué.`
            : "Lecture indisponible. Vérifie les voix françaises disponibles dans ton navigateur.";
        }
        resolve(false);
      };
      signal.addEventListener("abort", () => resolve(false), { once: true });
      try {
        synthesis.speak(speech);
      } catch {
        resolve(false);
      }
    });
  }

  async function play(text, useCache = false) {
    stop();
    status.textContent = "";
    const playback = new AbortController();
    request = playback;
    const { signal } = playback;
    const timeout = setTimeout(() => {
      if (request === playback) stop();
    }, 60000);
    let azureError = "Voix Azure indisponible.";
    try {
      if (!azureVoice) return await speakInBrowser(text, signal);
      let clip = useCache ? cachedAudio : null;
      if (!clip) {
        const response = await fetch("/api/speech", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
          signal,
        });
        if (!response.ok) {
          const { detail } = await response.json();
          if (typeof detail === "string") azureError = detail;
          throw new Error(azureError);
        }
        clip = await response.blob();
        if (signal.aborted) return false;
        if (useCache) cachedAudio = clip;
      }
      audioUrl = URL.createObjectURL(clip);
      audio = new Audio(audioUrl);
      const player = audio;
      return await new Promise((resolve, reject) => {
        player.addEventListener("ended", () => resolve(true), { once: true });
        player.addEventListener("error", () => reject(new Error(azureError)), { once: true });
        signal.addEventListener("abort", () => resolve(false), { once: true });
        player.play().catch(reject);
      });
    } catch {
      if (signal.aborted) return false;
      audio?.pause();
      if (useCache) cachedAudio = null;
      status.textContent = `${azureError} Lecture avec la voix du navigateur.`;
      return await speakInBrowser(text, signal, azureError);
    } finally {
      clearTimeout(timeout);
      if (request === playback) {
        request = null;
        currentSpeech = null;
        if (audioUrl) URL.revokeObjectURL(audioUrl);
        audio = null;
        audioUrl = "";
      }
    }
  }

  function speak() {
    if (enabled && question && !automatic) void play(question, true);
  }

  function updateControls() {
    toggle.disabled = !browserVoice && !azureVoice;
    toggle.setAttribute("aria-pressed", String(enabled));
    toggleState.textContent = enabled ? "activée" : "désactivée";
    replay.hidden = !enabled || !question;
  }

  updateControls();
  if (!browserVoice) status.textContent = "La voix du navigateur est indisponible.";
  toggle.addEventListener("click", () => {
    enabled = !enabled;
    updateControls();
    if (enabled) speak();
    else {
      stop();
      status.textContent = "";
    }
  });
  replay.addEventListener("click", speak);

  return {
    setAzureVoice(available) {
      azureVoice = available;
      if (available) status.textContent = "";
      updateControls();
    },
    setQuestion(text) {
      question = text;
      cachedAudio = null;
      updateControls();
      speak();
    },
    setAutomatic(value) {
      automatic = value;
    },
    play,
    stopPlayback: stop,
    reset() {
      stop();
      question = "";
      cachedAudio = null;
      if (browserVoice || azureVoice) status.textContent = "";
      updateControls();
    },
  };
}
