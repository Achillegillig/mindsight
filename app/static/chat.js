const form = document.querySelector("form");
const answer = document.querySelector("#answer");
const send = document.querySelector("#send");
const reset = document.querySelector("#reset");
const messages = document.querySelector("#messages");
const status = document.querySelector("#status");
const reasoning = document.querySelector("#reasoning");
const reasoningStatus = document.querySelector("#reasoning-status");
const reasoningTurns = document.querySelector("#reasoning-turns");
const reasoningDimensions = document.querySelector("#reasoning-dimensions");
const page = document.querySelector("main");
const scoresPanel = document.querySelector("#trait-scores");
const scoresStatus = document.querySelector("#trait-scores-status");
const scoresTable = document.querySelector("#trait-scores-table");
const scoresBody = scoresTable.querySelector("tbody");
const scoresNote = document.querySelector("#trait-scores-note");
const questionVoice = createQuestionVoice();
let history = [];
let finished = false;
let sessionId;
let pendingRequest;
let reasoningRun = 0;
let scoresRun = 0;
const demo = document.querySelector("#demo-data");

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
const formatNumber = new Intl.NumberFormat("fr", { maximumFractionDigits: 3 });

function textElement(tag, text) {
  const element = document.createElement(tag);
  element.textContent = text;
  return element;
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
    links.append(textElement("li", `${label} · Appui ${strengths[item.strength]}. `
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
    const calculation = textElement("p",
      `Total des points ${n(calc.total_points)} · Plafond ${n(calc.max_score)}`);
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
  const evidenceLabels = {
    sans_indice: "Aucun indice",
    documentee: "Indices relevés",
  };
  scoresBody.replaceChildren(...snapshot.traits.map((trait) => {
    const row = document.createElement("tr");
    const label = textElement("th", trait.label);
    label.scope = "row";
    row.append(label, textElement("td", formatNumber.format(trait.score)),
      textElement("td", evidenceLabels[trait.status]));
    return row;
  }));
  scoresStatus.textContent = analysisLabels[snapshot.analysis_status];
  scoresTable.hidden = false;
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
        return;
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

async function getReply(messages) {
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

function append(message) {
  const item = document.createElement("li");
  item.dataset.role = message.role;
  const author = document.createElement("strong");
  author.textContent = message.role === "user" ? "Toi" : "MindSight";
  const content = document.createElement("p");
  content.textContent = message.content;
  item.append(author, content);
  messages.append(item);
}

function setBusy(busy) {
  reset.disabled = busy;
  form.hidden = finished;
  answer.readOnly = busy || finished;
  send.disabled = busy || finished || history.length === 0;
}

async function start() {
  questionVoice.reset();
  setBusy(true);
  status.textContent = "";
  try {
    const { opening, session_id, reasoning: showReasoning } = await openSession();
    sessionId = session_id;
    reasoningRun++;
    scoresRun++;
    scoresPanel.hidden = true;
    page.classList.remove("with-scores");
    scoresTable.hidden = true;
    scoresNote.hidden = true;
    scoresBody.replaceChildren();
    scoresStatus.textContent = "";
    reasoning.hidden = !showReasoning;
    reasoningTurns.replaceChildren();
    reasoningDimensions.replaceChildren();
    reasoningStatus.textContent = "";
    void refreshReasoning();
    pendingRequest = undefined;
    history = [opening];
    finished = false;
    messages.replaceChildren();
    append(opening);
    questionVoice.setQuestion(opening.content);
    answer.value = "";
  } catch {
    status.textContent = "Impossible de charger la question. Clique sur Recommencer pour réessayer.";
  } finally {
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

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = answer.value.trim();
  if (!content || send.disabled) return;

  const userMessage = { role: "user", content };
  if (!demo && pendingRequest?.content !== content) {
    pendingRequest = { id: crypto.randomUUID(), content };
  }
  setBusy(true);
  status.textContent = "Analyse en cours…";
  try {
    const { reply, done } = await getReply([...history, userMessage]);
    finished = done;
    const assistantMessage = { role: "assistant", content: reply };
    history.push(userMessage, assistantMessage);
    pendingRequest = undefined;
    append(userMessage);
    append(assistantMessage);
    if (done) void showFinalScores();
    else questionVoice.setQuestion(reply);
    void refreshReasoning((history.length - 1) / 2);
    answer.value = "";
    status.textContent = finished ? "Conversation terminée." : "";
  } catch (error) {
    status.textContent = error instanceof TypeError || !error.message
      ? "La relance a échoué. Ta réponse est conservée."
      : error.message + " Ta réponse est conservée.";
  } finally {
    setBusy(false);
    if (!finished) answer.focus();
  }
});

reset.addEventListener("click", async () => {
  await start();
  if (!finished) answer.focus();
});
start();

if (!demo) {
  fetch("/api/conversation/mode")
    .then((response) => response.json())
    .then(({ model, azureSpeech }) => {
      questionVoice.setAzureVoice(azureSpeech);
      document.querySelector("#mode").textContent = model ? `OpenRouter · ${model}` : "Conversation simulée";
    })
    .catch(() => {
      document.querySelector("#mode").textContent = "Serveur indisponible";
    });
}
