const form = document.querySelector("form");
const answer = document.querySelector("#answer");
const send = document.querySelector("#send");
const reset = document.querySelector("#reset");
const messages = document.querySelector("#messages");
const status = document.querySelector("#status");
const questionVoice = createQuestionVoice();
let history = [];
const demo = document.querySelector("#demo-data");

async function getOpening() {
  if (demo) return JSON.parse(demo.textContent).opening;
  const response = await fetch("/api/conversation/opening");
  if (!response.ok) throw new Error();
  return response.json();
}

async function getReply(messages) {
  if (demo) {
    const { replies } = JSON.parse(demo.textContent);
    return replies[(messages.length / 2 - 1) % replies.length];
  }
  const response = await fetch("/api/conversation/turn", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail);
  return result.reply;
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
  answer.readOnly = busy;
  send.disabled = busy || history.length === 0;
}

async function start() {
  questionVoice.reset();
  setBusy(true);
  status.textContent = "";
  try {
    const opening = await getOpening();
    history = [opening];
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
  setBusy(true);
  status.textContent = "Relance en cours…";
  try {
    const reply = await getReply([...history, userMessage]);
    const assistantMessage = { role: "assistant", content: reply };
    history.push(userMessage, assistantMessage);
    append(userMessage);
    append(assistantMessage);
    questionVoice.setQuestion(reply);
    answer.value = "";
    status.textContent = "";
  } catch (error) {
    status.textContent = error instanceof TypeError || !error.message
      ? "La relance a échoué. Ta réponse est conservée."
      : error.message + " Ta réponse est conservée.";
  } finally {
    setBusy(false);
    answer.focus();
  }
});

reset.addEventListener("click", async () => {
  await start();
  answer.focus();
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
