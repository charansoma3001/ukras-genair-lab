// SSE for live events,
// /status for state, /chat + /eval to act, /prompt + /eval/cases to edit.

const log = document.getElementById("log");
const evalRes = document.getElementById("evalresults");
const $ = (id) => document.getElementById(id);

function esc(s) {
  return (s || "").replace(
    /[&<>]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c],
  );
}
function add(cls, html) {
  const d = document.createElement("div");
  d.className = cls;
  d.innerHTML = html;
  log.appendChild(d);
  keepThinkingLast();
  log.scrollTop = log.scrollHeight;
}

// "thinking" indicator
let thinkingEl = null;
function modelLabel() {
  return $("think").checked ? "thinking" : "deciding";
}
function showThinking(label) {
  if (!thinkingEl) {
    thinkingEl = document.createElement("div");
    thinkingEl.className = "msg robot thinking";
    thinkingEl.innerHTML =
      '<span class="think-label"></span><span class="dots"><i></i><i></i><i></i></span>';
  }
  thinkingEl.querySelector(".think-label").textContent = label || "thinking";
  log.appendChild(thinkingEl);
  log.scrollTop = log.scrollHeight;
}
function hideThinking() {
  if (thinkingEl) {
    thinkingEl.remove();
    thinkingEl = null;
  }
}
function keepThinkingLast() {
  if (thinkingEl) log.appendChild(thinkingEl);
}
function addEval(cls, html) {
  const d = document.createElement("div");
  d.className = cls;
  d.innerHTML = html;
  evalRes.appendChild(d);
  evalRes.scrollTop = evalRes.scrollHeight;
}

// live event stream
const ev = new EventSource("/events");
ev.onmessage = (e) => {
  const m = JSON.parse(e.data);
  switch (m.type) {
    case "CHAT_RESPONSE":
      break; // the user's message is already on screen
    case "STEP_STARTED":
      add("step", '<span class="run">▶</span> ' + esc(m.message));
      showThinking("acting");
      break;
    case "STEP_COMPLETED":
      add("step", '<span class="ok">✓</span> ' + esc(m.message));
      showThinking(modelLabel());
      break;
    case "STEP_FAILED":
      add("step", '<span class="fail">✗</span> ' + esc(m.message));
      showThinking(modelLabel());
      break;
    case "THINKING_DONE":
      showThinking("deciding");
      break;
    case "ROBOT_SPEECH":
      add("msg robot", esc(m.message));
      break;
    case "TASK_COMPLETE":
      hideThinking();
      add("done", "✓ " + esc(m.message));
      break;
    case "TASK_FAILED":
      hideThinking();
      add("done", "■ " + esc(m.message));
      break;
    case "TASK_STOPPED":
      hideThinking();
      add("done", "◼ " + esc(m.message));
      break;
    case "SYSTEM_MSG":
      add("sys", esc(m.message));
      break;
    case "ERROR":
      add("step", '<span class="fail">error:</span> ' + esc(m.message));
      break;
    case "CHAT_FINISHED":
      hideThinking();
      setBusy(false);
      $("runeval").disabled = false;
      break;
    // eval
    case "EVAL_STARTED":
      evalRes.innerHTML = "";
      $("evalscore").textContent = "";
      addEval("sys", esc(m.message));
      break;
    case "EVAL_CASE_STARTED":
      addEval(
        "step",
        '<span class="run">▶</span> ' +
          m.data.index +
          "/" +
          m.data.total +
          " " +
          esc(m.message),
      );
      break;
    case "EVAL_CASE_DONE":
      addEval(
        "step",
        (m.data.pass
          ? '<span class="ok">✓ PASS</span> '
          : '<span class="fail">✗ FAIL</span> ') + esc(m.message),
      );
      break;
    case "EVAL_STOPPED":
      addEval("done", "◼ " + esc(m.message));
      break;
    case "EVAL_DONE": {
      const sc = $("evalscore");
      sc.textContent =
        m.data.passed + "/" + m.data.total + " (" + m.data.rate + "%)";
      sc.style.color =
        m.data.rate >= 70
          ? "var(--green)"
          : m.data.rate >= 40
            ? "var(--warn)"
            : "var(--red)";
      addEval("done", "■ " + esc(m.message));
      break;
    }
  }
};

// status polling
let booted = false,
  curModel = "",
  isOllama = false;
async function poll() {
  try {
    const s = await (await fetch("/status")).json();
    const dot = $("dot"),
      txt = $("statetext");
    if (!s.ready) {
      dot.className = "dot";
      txt.textContent = "booting simulator…";
    } else if (s.busy) {
      dot.className = "dot busy";
      txt.textContent = "working…";
    } else {
      dot.className = "dot ready";
      txt.textContent = "ready";
    }
    $("held").textContent = s.held_object ? "holding: " + s.held_object : "";
    $("scene").textContent = s.config.scene;
    // button states (covers chat + eval)
    $("sendbtn").disabled = s.busy || !s.ready;
    $("cmd").disabled = !s.ready;
    $("stopbtn").disabled = !s.busy;
    $("evalstop").disabled = !s.busy;
    $("runeval").disabled = s.busy || !s.ready;
    // Context size last sent to the model, so students know when to clear chat.
    $("ctxtokens").textContent =
      typeof s.context_tokens === "number"
        ? `context: ${s.context_tokens.toLocaleString()} tokens`
        : "";
    // Show/hide the unload button each tick so it appears if Ollama starts after
    // the page loaded (no refresh needed).
    if (typeof s.is_ollama === "boolean") {
      isOllama = s.is_ollama;
      $("unloadbtn").style.display = isOllama ? "" : "none";
    }
    if (s.ready && !booted) {
      booted = true;
      curModel = s.config.model_name;
      $("delay").value = s.config.step_delay;
      $("think").checked = s.config.think === true;
      populateScenes(s.config.scene);
      loadModels(); // will call updateThinkingToggle after fetching caps
    }
  } catch (e) {}
}
setInterval(poll, 1200);
poll();

function setBusy(b) {
  $("sendbtn").disabled = b;
  $("stopbtn").disabled = !b;
  $("evalstop").disabled = !b;
}

// models
let modelCaps = {};
async function loadModels() {
  const sel = $("model");
  try {
    const r = await (await fetch("/models")).json();
    const models = r.models || [];
    isOllama = !!r.is_ollama;
    modelCaps = {};
    models.forEach((m) => {
      modelCaps[m.id] = m;
    });
    const ids = models.map((m) => m.id);
    if (curModel && !ids.includes(curModel)) ids.unshift(curModel);
    sel.innerHTML =
      ids
        .map(
          (id) =>
            `<option ${id === curModel ? "selected" : ""}>${esc(id)}</option>`,
        )
        .join("") || `<option>${esc(curModel || "(no models)")}</option>`;
    updateThinkingToggle();
    $("unloadbtn").style.display = isOllama ? "" : "none";
  } catch (e) {
    sel.innerHTML = `<option>${esc(curModel || "(unavailable)")}</option>`;
  }
}
async function unloadModel() {
  const btn = $("unloadbtn");
  btn.disabled = true;
  try {
    const r = await fetch("/models/unload", { method: "POST" });
    const j = await r.json();
    add("sys", r.ok ? `⏏ ${j.message}` : `⏏ unload failed: ${j.message}`);
  } catch (e) {
    add("sys", "⏏ unload failed: " + e);
  } finally {
    btn.disabled = false;
  }
}
function updateThinkingToggle() {
  const caps = modelCaps[$("model").value] || {};
  const supported = !!caps.thinking;
  $("thinkrow").style.display = supported ? "" : "none";
  if (!supported) $("think").checked = false;
}

// scenes (floor plans)
// the point is to test whether the student's abilities + prompt generalise beyond FloorPlan1.
function populateScenes(current) {
  const sel = $("scenesel");
  const cats = [
    ["Kitchens", 0],
    ["Living Rooms", 200],
    ["Bedrooms", 300],
    ["Bathrooms", 400],
  ];
  sel.innerHTML = cats
    .map(([label, base]) => {
      let opts = "";
      for (let i = 1; i <= 30; i++) {
        const id = "FloorPlan" + (base + i);
        opts += `<option ${id === current ? "selected" : ""}>${id}</option>`;
      }
      return `<optgroup label="${esc(label)}">${opts}</optgroup>`;
    })
    .join("");
}

// config
async function applyConfig() {
  curModel = $("model").value;
  updateThinkingToggle();
  await fetch("/configure", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model_name: curModel,
      step_delay: parseFloat($("delay").value),
      think: $("think").checked,
      scene: $("scenesel").value,
    }),
  });
}
async function clearChat() {
  log.innerHTML = "";
  $("ctxtokens").textContent = "";
  hideThinking();
  await fetch("/chat/reset", { method: "POST" });
}
async function resetScene() {
  await fetch("/reset", { method: "POST" });
}

// chat
async function send() {
  const inp = $("cmd");
  const text = inp.value.trim();
  if (!text) return;
  add("msg user", esc(text));
  inp.value = "";
  setBusy(true);
  showThinking(modelLabel());
  const r = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text }),
  });
  if (r.status === 409) {
    hideThinking();
    add("sys", "robot is busy - wait for the current command");
    setBusy(false);
  } else if (r.status === 503) {
    hideThinking();
    add("sys", "simulator still booting…");
    setBusy(false);
  }
}
async function stopRobot() {
  $("stopbtn").disabled = true;
  $("evalstop").disabled = true;
  await fetch("/stop", { method: "POST" });
  add("sys", "stopping… (finishing the current step)");
}

// prompt editor
async function loadPrompt() {
  const r = await (await fetch("/prompt")).json();
  $("prompt").value = r.prompt;
}
async function savePrompt() {
  await fetch("/prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: $("prompt").value }),
  });
  flash("savedflash");
}
async function resetPrompt() {
  const r = await (await fetch("/prompt/reset", { method: "POST" })).json();
  $("prompt").value = r.prompt;
}
function exportPrompt() {
  const blob = new Blob([$("prompt").value], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "system_prompt.txt";
  a.click();
}
function importPrompt(e) {
  const f = e.target.files[0];
  if (!f) return;
  const r = new FileReader();
  r.onload = () => ($("prompt").value = r.result);
  r.readAsText(f);
}
loadPrompt();

// abilities
function showAbErrors(errors) {
  $("aberrors").textContent = errors && errors.length ? errors.join("\n") : "";
}
async function loadAbilities() {
  const r = await (await fetch("/abilities")).json();
  $("abilities").value = r.text;
  showAbErrors(r.errors);
}
async function saveAbilities() {
  const r = await (
    await fetch("/abilities", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: $("abilities").value }),
    })
  ).json();
  showAbErrors(r.errors);
  flash("absaved");
}
async function resetAbilities() {
  const r = await (await fetch("/abilities/reset", { method: "POST" })).json();
  $("abilities").value = r.text;
  showAbErrors(r.errors);
}
loadAbilities();

// eval
async function loadEval() {
  const r = await (await fetch("/eval/cases")).json();
  $("eval").value = r.text;
}
async function saveEval() {
  await fetch("/eval/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: $("eval").value }),
  });
  flash("evalsaved");
}
async function runEval() {
  const btn = $("runeval");
  btn.disabled = true;
  const r = await fetch("/eval/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: $("eval").value }),
  });
  if (r.ok) {
    showTab("eval");
    return;
  } // stays disabled until EVAL finishes (CHAT_FINISHED)
  if (r.status === 409) addEval("sys", "robot busy - try again when idle");
  else if (r.status === 503) addEval("sys", "simulator still booting…");
  else if (r.status === 400) {
    const j = await r.json();
    addEval("step", '<span class="fail">' + esc(j.message) + "</span>");
  }
  btn.disabled = false;
}
loadEval();

// misc
function flash(id) {
  const f = $(id);
  f.classList.add("show");
  setTimeout(() => f.classList.remove("show"), 1500);
}
function showTab(t) {
  ["chat", "abilities", "prompt", "eval"].forEach((x) => {
    $("pane-" + x).classList.toggle("active", x === t);
    $("tab-" + x).classList.toggle("active", x === t);
  });
}
