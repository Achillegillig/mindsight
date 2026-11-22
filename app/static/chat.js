const form = document.querySelector("form");
const answer = document.querySelector("#answer");
const send = document.querySelector("#send");
const reset = document.querySelector("#reset");
const replay = document.querySelector("#voice-replay");
const autoControls = document.querySelector("#auto-controls");
const autoToggle = document.querySelector("#auto-toggle");
const autoStatus = document.querySelector("#auto-status");
const playResult = document.querySelector("#play-result");
const chatColumn = form.closest(".chat-column");
const composer = form.closest(".composer");
const messages = document.querySelector("#messages");
const status = document.querySelector("#status");
const reasoning = document.querySelector("#reasoning");
const reasoningStatus = document.querySelector("#reasoning-status");
const reasoningTurns = document.querySelector("#reasoning-turns");
const reasoningDimensions = document.querySelector("#reasoning-dimensions");
const page = document.querySelector("main");
const scoresPanel = document.querySelector("#trait-scores");
const scoresStatus = document.querySelector("#trait-scores-status");
const scoresList = document.querySelector("#trait-scores-list");
const scoresNote = document.querySelector("#trait-scores-note");
const questionVoice = createQuestionVoice();
let history = [];
let finished = false;
let sessionId;
let pendingRequest;
let reasoningRun = 0;
let scoresRun = 0;
let busy = false;
let autoRun;
let portraitVoiceDrop = false;
let openingSession = false;
let turnRequest;
let finalAnnouncement;
const demo = document.querySelector("#demo-data");
const dictation = demo ? null : createDictation(answer, send, questionVoice);

const analysisLabels = {
  idle: "L’analyse commencera après ta première réponse.",
  pending: "Analyse en cours…",
  ready: "Analyse à jour.",
  partial: "Analyse partielle. Les observations disponibles sont affichées.",
  failed: "Analyse indisponible pour le dernier tour.",
  simulated: "Mode simulé. Aucune analyse de traits n’est exécutée.",
};
const subjects = { participant: "Participant", tiers: "Tiers", personnage: "Personnage", incertain: "Incertain" };
const modes = {
  vecu: "Vécu raconté", declaration: "Déclaration", fiction: "Fiction", citation: "Citation",
  hypothetique: "Hypothèse",
};
const strengths = { direct: "direct", indirect: "indirect" };
const intensities = { leger: "léger", net: "net", frappant: "frappant" };
const formatNumber = new Intl.NumberFormat("fr", { maximumFractionDigits: 3 });

function textElement(tag, text) {
  const element = document.createElement(tag);
  element.textContent = text;
  return element;
}

async function showPortraitPreview() {
  const preview = document.querySelector("#portrait-preview");
  const image = preview.querySelector("img");
  for (let attempt = 0; attempt < 20; attempt++) {
    try {
      const response = await fetch("/api/portrait/preview", { cache: "no-store" });
      if (response.ok) {
        const url = URL.createObjectURL(await response.blob());
        image.src = url;
        try {
          await image.decode();
          preview.hidden = false;
          page.classList.add("with-portrait");
          return;
        } finally {
          URL.revokeObjectURL(url);
        }
      }
    } catch {
      // OpenGL peut encore être en train de préparer la première image.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

async function sendPortraitDrop(id) {
  const response = await fetch("/api/portrait/drop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: id }),
  });
  if (!response.ok) throw new Error("Signal du portrait indisponible.");
}

function renderReasoningTurn(turn, labels) {
  const details = document.createElement("details");
  details.dataset.turn = turn.turn;
  details.append(textElement("summary", `Tour ${turn.turn} · ${analysisLabels[turn.status]}`));
  const extraction = turn.extraction;
  if (!extraction) return details;

  const steps = document.createElement("ol");
  const observations = document.createElement("li");
  const counts = extraction.trace?.observation_candidates;
  const review = counts == null ? "" : ` · ${extraction.observations.length}/${counts} propositions validées`;
  observations.append(textElement("strong", `Citations vérifiées et attribution${review}`));
  const excerpts = document.createElement("ul");
  for (const item of extraction.observations) {
    const source = `t${turn.turn}:${item.id}`;
    excerpts.append(textElement("li",
      `${source} · « ${item.quote} » · ${item.label} · ${subjects[item.subject]} · ${modes[item.mode]}`));
  }
  observations.append(excerpts.childElementCount ? excerpts : textElement("p", "Aucune citation retenue."));
  steps.append(observations);

  const interpretation = document.createElement("li");
  const proposed = extraction.trace?.interpretation_candidates;
  const checked = proposed == null ? "" : ` · ${extraction.dimensions.length}/${proposed} liens validés`;
  interpretation.append(textElement("strong", `Interprétation des traits${checked}`));
  const links = document.createElement("ul");
  for (const [index, item] of (extraction.dimensions || []).entries()) {
    const label = labels.get(item.dimension_id) || item.dimension_id;
    const refs = item.observation_ids.map((id) => `t${turn.turn}:${id}`).join(", ");
    const episode = turn.episode_ids[index];
    const labelEpisode = episode === "unknown" ? "Épisode incertain" : `Épisode ${episode}`;
    const level = intensities[item.intensity] ?? strengths[item.strength];
    links.append(textElement("li", `${label} · Indice ${level}. `
      + `${item.reading} (${refs} · ${labelEpisode})`));
  }
  interpretation.append(links.childElementCount ? links : textElement("p",
    extraction.dimensions === null ? "Interprétation indisponible." : "Aucun lien suffisamment étayé."));
  steps.append(interpretation);
  details.append(steps);
  return details;
}

function renderAttribution(item) {
  const details = document.createElement("details");
  const state = item.status === "sans_indice" ? "Sans indice retenu" : "Appuyée dans le récit";
  details.append(textElement("summary", `${item.label} · ${state}`));
  details.append(textElement("p", item.definition));
  if (item.status !== "sans_indice") {
    const calc = item.calculation;
    const n = formatNumber.format;
    details.append(textElement("p",
      `Score ${n(item.score)} / 10 · Épisodes ${item.episode_count}`));
    const calculation = textElement("p", calc.strategy === "contrast"
      ? "Le meilleur indice fixe la base. Jusqu’à deux autres épisodes peuvent relever la note."
      : `Total des points ${n(calc.total_points)} · Plafond ${n(calc.max_score)}`);
    calculation.className = "reasoning-note";
    details.append(calculation);
    const sources = document.createElement("ul");
    for (const index of calc.selected) {
      const episode = index.episode_id === "unknown" ? "Épisode incertain" : index.episode_id;
      sources.append(textElement("li", `${episode} · `
        + `Poids ${n(index.weight)} · ${index.source_refs.join(", ")}`));
    }
    details.append(sources);
  }
  return details;
}

function renderReasoning(snapshot) {
  reasoningStatus.textContent = analysisLabels[snapshot.analysis_status];
  const labels = new Map(snapshot.dimensions.map((item) => [item.id, item.label]));
  const previousTurns = new Map([...reasoningTurns.children].map((item) => [item.dataset.turn, item.open]));
  reasoningTurns.replaceChildren(...snapshot.turns.map((turn) => {
    const item = renderReasoningTurn(turn, labels);
    item.open = previousTurns.get(item.dataset.turn) ?? (turn.turn === snapshot.through_turn);
    return item;
  }));

  const open = new Set([...reasoningDimensions.querySelectorAll("details[open]")]
    .map((item) => item.dataset.dimension));
  reasoningDimensions.replaceChildren();
  const families = new Map();
  for (const item of snapshot.dimensions) {
    if (!families.has(item.family)) {
      const family = document.createElement("section");
      family.append(textElement("h4", item.family));
      families.set(item.family, family);
      reasoningDimensions.append(family);
    }
    const group = families.get(item.family);
    const details = renderAttribution(item);
    details.dataset.dimension = item.id;
    details.open = open.has(item.id);
    group.append(details);
  }
}

async function refreshReasoning(targetTurn = 0) {
  if (reasoning.hidden) return;
  const run = ++reasoningRun;
  const id = sessionId;
  let displayed = "";
  while (run === reasoningRun) {
    try {
      const response = await fetch(`/api/conversation/session/${encodeURIComponent(id)}/reasoning`, { cache: "no-store" });
      if (!response.ok) throw new Error();
      const snapshot = await response.json();
      if (run !== reasoningRun) return;
      const state = `${snapshot.through_turn}/${snapshot.analysis_status}`;
      if (state !== displayed) {
        renderReasoning(snapshot);
        displayed = state;
      }
      if (snapshot.through_turn >= targetTurn) return;
    } catch {
      if (run === reasoningRun) reasoningStatus.textContent = "Impossible de charger l’analyse.";
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
}

function renderScores(snapshot) {
  scoresList.replaceChildren(...snapshot.traits.map((trait) => {
    const row = document.createElement("li");
    const label = textElement("strong", trait.label);
    const score = textElement("span", `${formatNumber.format(trait.score)} / 10`);
    const bar = document.createElement("meter");
    bar.max = 10;
    bar.value = trait.score;
    bar.setAttribute("aria-hidden", "true");
    const count = trait.episode_count;
    const evidence = textElement("span", count === 0 ? "Aucun indice retenu"
      : `${count} ${count === 1 ? "épisode avec indice" : "épisodes avec indices"}`);
    row.append(label, score, bar, evidence);
    return row;
  }));
  scoresStatus.textContent = analysisLabels[snapshot.analysis_status];
  scoresList.hidden = false;
  scoresNote.hidden = false;
}

async function showFinalScores() {
  scoresPanel.hidden = false;
  page.classList.add("with-scores");
  if (demo) {
    scoresStatus.textContent = "L’analyse des traits est disponible avec le serveur MindSight.";
    return;
  }
  const run = ++scoresRun;
  const url = `/api/conversation/session/${encodeURIComponent(sessionId)}/scores`;
  scoresStatus.textContent = "Calcul des scores en cours…";
  while (run === scoresRun) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) throw new Error();
      const snapshot = await response.json();
      if (run !== scoresRun) return;
      if (snapshot.ready) {
        renderScores(snapshot);
        return snapshot;
      }
    } catch {
      if (run === scoresRun) scoresStatus.textContent = "Impossible de charger les scores.";
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
}

async function openSession() {
  if (demo) return { opening: JSON.parse(demo.textContent).opening };
  const response = await fetch("/api/conversation/session", { method: "POST" });
  if (!response.ok) throw new Error();
  return response.json();
}

async function getReply(messages, signal) {
  if (demo) {
    const { questions, replies, closing, skipPattern } = JSON.parse(demo.textContent);
    const assistantMessages = messages.filter(({ role }) => role === "assistant");
    const questionPositions = assistantMessages
      .map(({ content }, index) => questions.includes(content) ? index : -1)
      .filter((index) => index >= 0);
    const asked = questionPositions.length;
    const followups = assistantMessages.length - questionPositions.at(-1) - 1;
    const skip = new RegExp(skipPattern, "i").test(messages.at(-1).content);
    if (!skip && followups < replies.length) return { reply: replies[followups], done: false };
    return { reply: questions[asked] ?? closing, done: asked === questions.length };
  }
  const response = await fetch("/api/conversation/turn", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal,
    body: JSON.stringify({
      messages,
      session_id: sessionId,
      request_id: pendingRequest.id,
    }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail);
  return result;
}

function append(message, isQuestion = false) {
  const item = document.createElement("li");
  item.dataset.role = message.role;
  const author = document.createElement("strong");
  author.textContent = message.role === "user" ? "Toi" : "MindSight";
  const content = document.createElement("p");
  content.textContent = message.content;
  item.append(author, content);
  if (isQuestion) {
    messages.querySelector(".latest-question")?.classList.remove("latest-question");
    item.classList.add("latest-question");
    item.append(replay);
  }
  messages.append(item);
  return item;
}

function revealMessage(message) {
  requestAnimationFrame(() => {
    if (!message.isConnected) return;
    const bounds = message.getBoundingClientRect();
    const bottom = window.innerHeight - composer.getBoundingClientRect().height - 12;
    const top = bounds.top - 12;
    const offset = top < 0 ? top : Math.max(0, Math.min(top, bounds.bottom - bottom));
    if (offset) {
      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollBy({ top: offset, behavior: reducedMotion ? "instant" : "smooth" });
    }
  });
}

function updateAutoControls() {
  autoToggle.disabled = !autoRun && (busy || finished || !history.length || !dictation?.supported);
  autoToggle.textContent = autoRun ? "Arrêter l’échange vocal" : "Démarrer l’échange vocal";
  chatColumn.classList.toggle("automatic", Boolean(autoRun));
}

function stopAutomatic(message = "") {
  if (autoRun) {
    autoRun = undefined;
    questionVoice.stopPlayback();
    questionVoice.setAutomatic(false);
    if (dictation.active) dictation.cancel();
  }
  autoStatus.textContent = message;
  updateAutoControls();
}

async function playAutomatically(run, text) {
  if (autoRun !== run) return false;
  const played = await questionVoice.play(text);
  if (autoRun !== run) return false;
  if (!played) stopAutomatic("Lecture audio impossible. Tu peux relancer l’échange vocal ou continuer au clavier.");
  return played;
}

async function askAutomatically(run, question) {
  autoStatus.textContent = "MindSight pose la question…";
  if (!await playAutomatically(run, question)) return;
  autoStatus.textContent = "";
  const ready = await dictation.record(true);
  if (autoRun !== run) return;
  if (ready) await submitAnswer();
  else stopAutomatic("Échange vocal arrêté. Tu peux le relancer ou écrire ta réponse.");
}

async function announceResult(announcement) {
  if (finalAnnouncement !== announcement) return;
  playResult.hidden = true;
  const played = await questionVoice.play(announcement.message);
  if (finalAnnouncement !== announcement) return;
  if (!played) {
    status.textContent = "La lecture automatique a échoué. Tu peux lancer l’annonce manuellement.";
    playResult.hidden = false;
    return;
  }
  finalAnnouncement = undefined;
  status.textContent = "Conversation terminée.";
  if (portraitVoiceDrop && announcement.sessionId) {
    try {
      await sendPortraitDrop(announcement.sessionId);
    } catch {
      if (sessionId === announcement.sessionId && !openingSession) {
        status.textContent = "Le portrait se déclenchera automatiquement dans quelques secondes.";
      }
    }
  }
}

async function concludeConversation(scores) {
  const run = scoresRun;
  stopAutomatic();
  const snapshot = await scores;
  if (scoresRun !== run || openingSession || !finished) return;
  const message = snapshot && !["failed", "simulated"].includes(snapshot.analysis_status)
    ? "Voici à quoi ressemble votre profil psychologique sous forme visuelle."
    : "La synthèse n’est pas disponible pour cette conversation.";
  finalAnnouncement = { message, sessionId: snapshot?.ready ? snapshot.session_id : undefined };
  await announceResult(finalAnnouncement);
}

function setBusy(value) {
  busy = value;
  reset.disabled = openingSession;
  form.hidden = finished;
  answer.readOnly = busy || finished;
  send.disabled = busy || finished || history.length === 0;
  dictation?.setBlocked(send.disabled);
  updateAutoControls();
}

async function start() {
  if (openingSession) return;
  openingSession = true;
  finalAnnouncement = undefined;
  playResult.hidden = true;
  if (turnRequest) {
    turnRequest.controller.abort();
    turnRequest.submitted.remove();
    turnRequest.waiting.remove();
    answer.value = turnRequest.draft;
    turnRequest = undefined;
  }
  stopAutomatic();
  dictation?.cancel();
  questionVoice.reset();
  setBusy(true);
  status.textContent = "Ouverture d’une nouvelle conversation…";
  try {
    const { opening, session_id, reasoning: showReasoning } = await openSession();
    sessionId = session_id;
    reasoningRun++;
    scoresRun++;
    scoresPanel.hidden = true;
    page.classList.remove("with-scores");
    scoresList.hidden = true;
    scoresNote.hidden = true;
    scoresList.replaceChildren();
    scoresStatus.textContent = "";
    reasoning.hidden = !showReasoning;
    reasoning.open = false;
    reasoningTurns.replaceChildren();
    reasoningDimensions.replaceChildren();
    reasoningStatus.textContent = "";
    void refreshReasoning();
    pendingRequest = undefined;
    history = [opening];
    finished = false;
    messages.replaceChildren();
    const firstQuestion = append(opening, true);
    questionVoice.setQuestion(opening.content);
    revealMessage(firstQuestion);
    answer.value = "";
    status.textContent = "";
  } catch {
    status.textContent = "Impossible d’ouvrir une nouvelle session. Clique sur Recommencer pour réessayer.";
  } finally {
    openingSession = false;
    setBusy(false);
  }
}

answer.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  if (!event.repeat && !send.disabled && answer.value.trim()) {
    form.requestSubmit(send);
  }
});

async function submitAnswer() {
  const draft = answer.value;
  const content = draft.trim();
  if (!content || send.disabled || dictation?.active) return;

  const run = autoRun;
  const controller = new AbortController();
  let next;
  const userMessage = { role: "user", content };
  if (!demo && pendingRequest?.content !== content) {
    pendingRequest = { id: crypto.randomUUID(), content };
  }
  setBusy(true);
  status.textContent = "";
  const submitted = append(userMessage);
  answer.value = "";
  dictation?.cancel();
  const waiting = textElement("li", "MindSight prépare la suite…");
  waiting.className = "waiting";
  messages.append(waiting);
  const request = { controller, submitted, waiting, draft };
  turnRequest = request;
  revealMessage(waiting);
  try {
    const { reply, done } = await getReply([...history, userMessage], controller.signal);
    if (controller.signal.aborted) return;
    finished = done;
    const assistantMessage = { role: "assistant", content: reply };
    history.push(userMessage, assistantMessage);
    pendingRequest = undefined;
    waiting.remove();
    if (done) messages.querySelector(".latest-question")?.classList.remove("latest-question");
    const response = append(assistantMessage, !done);
    if (done) {
      const scores = showFinalScores();
      next = () => concludeConversation(scores);
    } else {
      questionVoice.setQuestion(reply);
      if (run && autoRun === run) next = () => askAutomatically(run, reply);
    }
    void refreshReasoning((history.length - 1) / 2);
    status.textContent = finished ? "Conversation terminée." : "";
    revealMessage(response);
  } catch (error) {
    if (controller.signal.aborted) return;
    if (run && autoRun === run) stopAutomatic("Échange vocal arrêté. Tu peux renvoyer ta réponse.");
    submitted.remove();
    waiting.remove();
    answer.value = draft;
    status.textContent = error instanceof TypeError || !error.message
      ? "La relance a échoué. Ta réponse est conservée."
      : error.message + " Ta réponse est conservée.";
  } finally {
    if (turnRequest === request) {
      turnRequest = undefined;
      setBusy(false);
      if (!finished && !autoRun) answer.focus({ preventScroll: true });
    }
  }
  if (next) void next();
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (send.disabled || !answer.value.trim()) return;
  if (autoRun) stopAutomatic();
  void submitAnswer();
});

autoToggle.addEventListener("click", () => {
  if (autoRun) {
    stopAutomatic("Échange vocal arrêté.");
    return;
  }
  if (answer.value.trim() || dictation.active) {
    autoStatus.textContent = "Envoie ou efface ton brouillon avant de démarrer l’échange vocal.";
    return;
  }
  const run = {};
  autoRun = run;
  questionVoice.setAutomatic(true);
  updateAutoControls();
  void askAutomatically(run, history.at(-1).content);
});

playResult.addEventListener("click", () => {
  if (finalAnnouncement) void announceResult(finalAnnouncement);
});

reset.addEventListener("click", async () => {
  await start();
  if (!finished) answer.focus({ preventScroll: true });
});
start();

if (!demo) {
  fetch("/api/conversation/mode")
    .then((response) => response.json())
    .then(({ model, azureSpeech, azureTranscription, auto, portraitPreview, portraitVoiceDrop: voiceDrop }) => {
      questionVoice.setAzureVoice(azureSpeech);
      dictation.setAvailable(azureTranscription);
      portraitVoiceDrop = Boolean(voiceDrop);
      autoControls.hidden = !auto;
      chatColumn.classList.toggle("auto-mode", Boolean(auto));
      if (auto && !dictation.supported) {
        autoStatus.textContent = "L’échange vocal requiert un navigateur compatible sur HTTPS ou localhost.";
      }
      updateAutoControls();
      if (portraitPreview) void showPortraitPreview();
      document.querySelector("#mode").textContent = model ? "" : "Conversation simulée";
    })
    .catch(() => {
      document.querySelector("#mode").textContent = "Serveur indisponible";
    });
}
