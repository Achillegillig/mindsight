function createQuestionVoice() {
  const toggle = document.querySelector("#voice-toggle");
  const replay = document.querySelector("#voice-replay");
  const status = document.querySelector("#voice-status");
  const synthesis = window.speechSynthesis;
  const browserVoice = Boolean(synthesis && window.SpeechSynthesisUtterance);
  let azureVoice = false;
  let enabled = false;
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

  function speakInBrowser(azureError = "") {
    if (!browserVoice) {
      status.textContent = azureError || "Lecture vocale indisponible.";
      return;
    }
    const frenchVoices = synthesis.getVoices().filter((voice) => /^fr(?:-|_|$)/i.test(voice.lang));
    const voice = frenchVoices.find((voice) => voice.localService) ?? frenchVoices[0];
    const speech = new window.SpeechSynthesisUtterance(question);
    speech.lang = voice?.lang ?? "fr-FR";
    if (voice) speech.voice = voice;

    speech.onend = () => {
      if (currentSpeech === speech) currentSpeech = null;
    };
    speech.onerror = () => {
      if (currentSpeech !== speech) return;
      currentSpeech = null;
      status.textContent = azureError
        ? `${azureError} La voix du navigateur a également échoué.`
        : "Lecture indisponible. Vérifie les voix françaises disponibles dans ton navigateur.";
    };
    currentSpeech = speech;
    synthesis.speak(speech);
  }

  async function speak() {
    if (!enabled || !question) return;

    stop();
    status.textContent = "";
    if (!azureVoice) {
      speakInBrowser();
      return;
    }

    const playback = new AbortController();
    request = playback;
    let azureError = "Voix Azure indisponible.";
    try {
      if (!cachedAudio) {
        const response = await fetch("/api/speech", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: question }),
          signal: playback.signal,
        });
        if (!response.ok) {
          const { detail } = await response.json();
          if (typeof detail === "string") azureError = detail;
          throw new Error(azureError);
        }
        const result = await response.blob();
        if (playback.signal.aborted) return;
        cachedAudio = result;
      }
      audioUrl = URL.createObjectURL(cachedAudio);
      audio = new Audio(audioUrl);
      await audio.play();
    } catch {
      if (playback.signal.aborted) return;
      stop();
      cachedAudio = null;
      status.textContent = `${azureError} Lecture avec la voix du navigateur.`;
      speakInBrowser(azureError);
    } finally {
      if (request === playback) request = null;
    }
  }

  function updateControls() {
    toggle.disabled = !browserVoice && !azureVoice;
    toggle.textContent = enabled ? "Couper la voix" : "Activer la voix";
    replay.disabled = !enabled || !question;
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
    reset() {
      stop();
      question = "";
      cachedAudio = null;
      if (browserVoice || azureVoice) status.textContent = "";
      updateControls();
    },
  };
}
