const DEFAULT_API_BASE =
  window.location.origin.startsWith("http") && !window.location.origin.endsWith(":5500")
    ? window.location.origin
    : "http://localhost:8000";

const STORAGE_KEYS = {
  apiBase: "credit-assistant.api-base",
  selectedUserId: "credit-assistant.selected-user-id",
};

const SAMPLE_PROMPTS = [
  "Why did this customer's score move recently?",
  "What is the biggest credit risk for this profile?",
  "What should this customer do in the next 30 days?",
  "Explain the score drivers in plain English.",
];

const state = {
  apiBase: localStorage.getItem(STORAGE_KEYS.apiBase) || DEFAULT_API_BASE,
  users: [],
  selectedUserId: localStorage.getItem(STORAGE_KEYS.selectedUserId) || "",
  selectedUser: null,
  profile: null,
  conversations: {},
  activity: [],
  pendingAssistantMessageId: null,
  abortController: null,
};

const elements = {
  apiBase: document.querySelector("#api-base"),
  saveConfig: document.querySelector("#save-config"),
  connectionStatus: document.querySelector("#connection-status"),
  refreshUsers: document.querySelector("#refresh-users"),
  userList: document.querySelector("#user-list"),
  heroTitle: document.querySelector("#hero-title"),
  heroSubtitle: document.querySelector("#hero-subtitle"),
  selectedUserChip: document.querySelector("#selected-user-chip"),
  profileSummary: document.querySelector("#profile-summary"),
  signalList: document.querySelector("#signal-list"),
  promptList: document.querySelector("#prompt-list"),
  chatLog: document.querySelector("#chat-log"),
  activityFeed: document.querySelector("#activity-feed"),
  chatForm: document.querySelector("#chat-form"),
  chatInput: document.querySelector("#chat-input"),
  sendMessage: document.querySelector("#send-message"),
  stopStream: document.querySelector("#stop-stream"),
  chatStatus: document.querySelector("#chat-status"),
  clearChat: document.querySelector("#clear-chat"),
  loadProfile: document.querySelector("#load-profile"),
  userCardTemplate: document.querySelector("#user-card-template"),
};

bootstrap().catch((error) => {
  console.error(error);
  setConnectionStatus(`Initialization failed: ${error.message}`, true);
});

async function bootstrap() {
  elements.apiBase.value = state.apiBase;
  renderPromptChips();
  bindEvents();
  renderChat();
  renderActivity();
  await checkHealth();
  await loadUsers();
  if (state.selectedUserId) {
    await selectUser(state.selectedUserId);
  }
}

function bindEvents() {
  elements.saveConfig.addEventListener("click", async () => {
    state.apiBase = normalizeApiBase(elements.apiBase.value);
    localStorage.setItem(STORAGE_KEYS.apiBase, state.apiBase);
    setConnectionStatus("Saved backend URL. Rechecking...", false);
    await checkHealth();
    await loadUsers();
  });

  elements.refreshUsers.addEventListener("click", async () => {
    await loadUsers();
  });

  elements.loadProfile.addEventListener("click", async () => {
    if (!state.selectedUserId) {
      return;
    }
    await loadSelectedUserContext(state.selectedUserId);
  });

  elements.clearChat.addEventListener("click", () => {
    if (!state.selectedUserId) {
      return;
    }
    state.conversations[state.selectedUserId] = [];
    renderChat();
  });

  elements.stopStream.addEventListener("click", () => {
    if (state.abortController) {
      state.abortController.abort();
    }
  });

  elements.chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await sendCurrentMessage();
  });

  elements.chatInput.addEventListener("keydown", async (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      await sendCurrentMessage();
    }
  });
}

async function checkHealth() {
  try {
    const response = await fetch(buildUrl("/health"));
    if (!response.ok) {
      throw new Error(`Health check failed with ${response.status}`);
    }
    setConnectionStatus("Backend reachable.", false);
  } catch (error) {
    setConnectionStatus(`Backend unavailable: ${error.message}`, true);
  }
}

async function loadUsers() {
  elements.userList.innerHTML = `<div class="empty-state">Loading customers...</div>`;
  try {
    const data = await getJson("/users");
    state.users = data.users || [];
    renderUsers();
    if (!state.selectedUserId && state.users.length > 0) {
      await selectUser(state.users[0].user_id);
    } else if (state.selectedUserId && !state.users.some((user) => user.user_id === state.selectedUserId) && state.users[0]) {
      await selectUser(state.users[0].user_id);
    }
  } catch (error) {
    elements.userList.innerHTML = `<div class="empty-state">Could not load customers. ${escapeHtml(error.message)}</div>`;
  }
}

function renderUsers() {
  if (!state.users.length) {
    elements.userList.innerHTML = `<div class="empty-state">No customers returned by the backend.</div>`;
    return;
  }

  elements.userList.innerHTML = "";
  for (const user of state.users) {
    const node = elements.userCardTemplate.content.firstElementChild.cloneNode(true);
    node.querySelector(".user-name").textContent = user.full_name;
    node.querySelector(".user-meta").textContent = `${user.occupation}`;
    node.querySelector(".persona-badge").textContent = formatPersona(user.persona);
    node.querySelector(".user-location").textContent = `${user.city}, ${user.state} • ${user.user_id}`;
    node.classList.toggle("active", user.user_id === state.selectedUserId);
    node.addEventListener("click", async () => {
      await selectUser(user.user_id);
    });
    elements.userList.appendChild(node);
  }
}

async function selectUser(userId) {
  state.selectedUserId = userId;
  localStorage.setItem(STORAGE_KEYS.selectedUserId, userId);
  renderUsers();
  await loadSelectedUserContext(userId);
  renderChat();
}

async function loadSelectedUserContext(userId) {
  setChatStatus("Loading profile", true);
  elements.profileSummary.innerHTML = `<div class="empty-state">Loading profile summary...</div>`;
  elements.signalList.innerHTML = `<div class="empty-state">Loading key signals...</div>`;
  try {
    const [user, profile, recommendations] = await Promise.all([
      getJson(`/users/${userId}`),
      getJson(`/credit/profile/${userId}`),
      getJson(`/credit/recommendations/${userId}`),
    ]);

    state.selectedUser = user;
    state.profile = { ...profile, recommendations: recommendations.recommendations || [] };
    renderHero();
    renderProfile();
    renderChat();
    setChatStatus("Ready", false);
  } catch (error) {
    state.selectedUser = null;
    state.profile = null;
    renderHero();
    elements.profileSummary.innerHTML = `<div class="empty-state">Could not load profile. ${escapeHtml(error.message)}</div>`;
    elements.signalList.innerHTML = `<div class="empty-state">Profile signals unavailable.</div>`;
    setChatStatus("Profile error", false);
  }
}

function renderHero() {
  if (!state.selectedUser) {
    elements.heroTitle.textContent = "Select a customer to begin";
    elements.heroSubtitle.textContent = "The assistant will use the selected user ID when calling the backend.";
    elements.selectedUserChip.textContent = "No user selected";
    return;
  }

  const profile = state.profile?.credit_report;
  elements.heroTitle.textContent = `${state.selectedUser.full_name} • ${state.selectedUser.user_id}`;
  elements.heroSubtitle.textContent = profile
    ? `${state.selectedUser.occupation} in ${state.selectedUser.city}, ${state.selectedUser.state}. Current bureau report generated ${profile.generated_at}.`
    : `${state.selectedUser.occupation} in ${state.selectedUser.city}, ${state.selectedUser.state}.`;
  elements.selectedUserChip.textContent = formatPersona(state.selectedUser.persona);
}

function renderProfile() {
  if (!state.profile || !state.selectedUser) {
    return;
  }

  const { credit_report: report, metrics, recommendations = [] } = state.profile;
  const scoreDelta = formatSignedNumber(report.score_change_30d);
  const utilizationPct = formatPercent(metrics.revolving_utilization);
  const paymentRatio = formatPercent(metrics.on_time_payment_ratio);

  elements.profileSummary.innerHTML = `
    <div class="metric-card">
      <p class="metric-label">Credit Score</p>
      <p class="metric-value">${report.score}</p>
      <p class="metric-detail">${capitalizeWords(report.score_band)} band • ${scoreDelta} in 30d</p>
    </div>
    <div class="metric-card">
      <p class="metric-label">Utilization</p>
      <p class="metric-value">${utilizationPct}</p>
      <p class="metric-detail">$${formatNumber(metrics.revolving_balance_total)} of $${formatNumber(metrics.revolving_limit_total)}</p>
    </div>
    <div class="metric-card">
      <p class="metric-label">On-Time Payments</p>
      <p class="metric-value">${paymentRatio}</p>
      <p class="metric-detail">${metrics.delinquent_accounts} delinquent account(s)</p>
    </div>
    <div class="metric-card">
      <p class="metric-label">Available Credit</p>
      <p class="metric-value">$${formatNumber(metrics.total_available_credit)}</p>
      <p class="metric-detail">${report.total_open_accounts} open account(s)</p>
    </div>
  `;

  const trendCards = metrics.trends
    .map(
      (trend) => `
        <div class="signal-card">
          <div class="activity-meta">
            <h4>${capitalizeWords(trend.metric.replaceAll("_", " "))}</h4>
            <span class="trend-badge ${trendClass(trend.direction)}">${capitalizeWords(trend.direction)}</span>
          </div>
          <p>${escapeHtml(trend.detail)}</p>
        </div>
      `,
    )
    .join("");

  const recommendationCards = recommendations
    .slice(0, 2)
    .map(
      (item) => `
        <div class="recommendation-card">
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml(item.rationale || item.description || "No rationale provided.")}</p>
        </div>
      `,
    )
    .join("");

  const summaryCard = `
    <div class="signal-card">
      <div class="activity-meta">
        <h4>Report Summary</h4>
        <span class="trend-badge ${trendClass(report.score_change_30d >= 0 ? "improving" : "worsening")}">${scoreDelta}</span>
      </div>
      <p>${escapeHtml(report.summary)}</p>
    </div>
  `;

  elements.signalList.innerHTML = `${summaryCard}${trendCards}${recommendationCards}`;
}

function renderPromptChips() {
  elements.promptList.innerHTML = "";
  for (const prompt of SAMPLE_PROMPTS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "prompt-chip";
    button.textContent = prompt;
    button.addEventListener("click", () => {
      elements.chatInput.value = prompt;
      elements.chatInput.focus();
    });
    elements.promptList.appendChild(button);
  }
}

function renderChat() {
  const messages = getConversation();
  if (!messages.length) {
    elements.chatLog.innerHTML = `<div class="empty-state">Ask a question once a customer is selected. The chat will show only the question and final answer.</div>`;
    return;
  }

  elements.chatLog.innerHTML = "";
  for (const message of messages) {
    const article = document.createElement("article");
    article.className = `message ${message.role}`;
    article.innerHTML = `
      <div class="message-header">
        <span class="message-role">${escapeHtml(message.label)}</span>
        <span class="message-time">${escapeHtml(message.timestamp)}</span>
      </div>
      <div class="message-body">${renderMessageBody(message)}</div>
    `;
    elements.chatLog.appendChild(article);
  }
  elements.chatLog.scrollTop = elements.chatLog.scrollHeight;
}

function renderMessageBody(message) {
  const visibleContent = message.isStreaming
    ? formatStreamingAssistantContent(message.rawContent || message.content || "")
    : message.content || "";

  if (message.isStreaming) {
    const streamedText = visibleContent
      ? `<div class="streaming-text">${escapeHtml(visibleContent)}</div>`
      : "";
    return `
      ${streamedText}
      <span class="typing-row">
        <span class="typing-label">Thinking</span>
        <span class="typing-dots" aria-label="Assistant is typing">
          <span></span>
          <span></span>
          <span></span>
        </span>
      </span>
    `;
  }
  return escapeHtml(visibleContent);
}

function renderActivity() {
  if (!state.activity.length) {
    elements.activityFeed.innerHTML = `<div class="empty-state">Streaming progress events will appear here during each request.</div>`;
    return;
  }

  elements.activityFeed.innerHTML = state.activity
    .map(
      (item) => `
        <div class="activity-item">
          <div class="activity-meta">
            <h4>${escapeHtml(item.title)}</h4>
            <span class="status-chip ${item.live ? "live" : ""}">${escapeHtml(item.event)}</span>
          </div>
          <p>${escapeHtml(item.detail)}</p>
        </div>
      `,
    )
    .join("");
  elements.activityFeed.scrollTop = elements.activityFeed.scrollHeight;
}

async function sendCurrentMessage() {
  const message = elements.chatInput.value.trim();
  if (!message || !state.selectedUserId || state.abortController) {
    return;
  }

  const userMessage = createMessage({
    role: "user",
    label: "Advisor",
    content: message,
  });

  const assistantMessage = createMessage({
    role: "assistant",
    label: "CreditAssistant",
    content: "",
    rawContent: "",
    isStreaming: true,
  });

  const conversation = getConversation();
  conversation.push(userMessage, assistantMessage);
  state.pendingAssistantMessageId = assistantMessage.id;
  elements.chatInput.value = "";
  state.activity = [];
  renderChat();
  renderActivity();
  setChatStatus("Streaming", true);
  toggleComposer(true);

  state.abortController = new AbortController();

  try {
    await postSse("/chat", { user_id: state.selectedUserId, message, stream: true }, handleStreamEvent, state.abortController.signal);
    finalizeAssistantMessage();
    setChatStatus("Ready", false);
  } catch (error) {
    if (error.name === "AbortError") {
      setPendingAssistantContent("Response stopped before the final answer completed.");
      setChatStatus("Stopped", false);
    } else {
      setPendingAssistantContent(`Unable to complete the request: ${error.message}`);
      setChatStatus("Error", false);
    }
  } finally {
    state.abortController = null;
    state.pendingAssistantMessageId = null;
    toggleComposer(false);
    renderChat();
    renderActivity();
  }
}

function handleStreamEvent(eventName, data) {
  if (shouldShowActivityEvent(eventName)) {
    const event = describeEvent(eventName, data);
    state.activity.push(event);
    renderActivity();
  }

  switch (eventName) {
    case "data":
      appendAssistantText(data.delta || "");
      break;
    case "end":
      break;
    case "error":
      setPendingAssistantContent(`The backend reported an error: ${data.message || "Unknown streaming error."}`);
      break;
    default:
      break;
  }

  renderChat();
}

function shouldShowActivityEvent(eventName) {
  return ["plan", "tool_start", "tool_result", "retrieval_start", "retrieval_result", "end", "error"].includes(eventName);
}

function finalizeAssistantMessage() {
  const assistantMessage = getPendingAssistantMessage();
  if (!assistantMessage) {
    return;
  }
  assistantMessage.isStreaming = false;
  assistantMessage.content = normalizeAssistantContent(assistantMessage.rawContent);
  if (!assistantMessage.content.trim()) {
    assistantMessage.content = "The backend completed without returning answer text.";
  }
}

function appendAssistantText(delta) {
  const assistantMessage = getPendingAssistantMessage();
  if (!assistantMessage) {
    return;
  }
  assistantMessage.rawContent += delta;
}

function setPendingAssistantContent(content) {
  const assistantMessage = getPendingAssistantMessage();
  if (!assistantMessage) {
    return;
  }
  assistantMessage.isStreaming = false;
  assistantMessage.content = content;
}

function appendConversation(message) {
  const conversation = getConversation();
  conversation.push(message);
}

function getPendingAssistantMessage() {
  return getConversation().find((message) => message.id === state.pendingAssistantMessageId);
}

function getConversation() {
  if (!state.selectedUserId) {
    return [];
  }
  if (!state.conversations[state.selectedUserId]) {
    state.conversations[state.selectedUserId] = [];
  }
  return state.conversations[state.selectedUserId];
}

function createMessage({ role, label, content, rawContent = "", isStreaming = false }) {
  return {
    id: crypto.randomUUID(),
    role,
    label,
    content,
    rawContent,
    isStreaming,
    timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
  };
}

function setConnectionStatus(text, isError) {
  elements.connectionStatus.textContent = text;
  elements.connectionStatus.style.color = isError ? "#f9b3a7" : "";
}

function setChatStatus(text, isLive) {
  elements.chatStatus.textContent = text;
  elements.chatStatus.classList.toggle("live", isLive);
  elements.chatStatus.classList.toggle("idle", !isLive);
}

function toggleComposer(isBusy) {
  elements.sendMessage.disabled = isBusy;
  elements.stopStream.disabled = !isBusy;
}

function describeEvent(eventName, data) {
  const base = {
    event: eventName.replaceAll("_", " "),
    live: !["end", "error"].includes(eventName),
  };

  switch (eventName) {
    case "start":
      return { ...base, title: "Stream opened", detail: "Waiting for classification and planning steps." };
    case "classification":
      return { ...base, title: "Query classified", detail: `${prettyCategory(data.category)}. ${sentenceCase(data.normalized_message || "Message normalized.")}` };
    case "plan":
      return {
        ...base,
        title: "Execution plan",
        detail: buildPlanDetail(data),
      };
    case "tool_start":
      return { ...base, title: "Tool started", detail: formatToolDetail(data.tool_name, data.reasoning) };
    case "tool_result":
      return { ...base, title: "Tool completed", detail: sentenceCase(data.summary || data.source || "Tool execution completed.") };
    case "retrieval_start":
      return { ...base, title: "Knowledge retrieval started", detail: sentenceCase(data.query || "Searching the knowledge base.") };
    case "retrieval_result":
      return {
        ...base,
        title: "Knowledge retrieval completed",
        detail: buildRetrievalResultDetail(data),
      };
    case "compose":
      return { ...base, title: "Answer composition started", detail: "Preparing the grounded final answer." };
    case "data":
      return { ...base, title: "Answer streaming", detail: "Response text is arriving from the backend." };
    case "end":
      return { ...base, title: "Request completed", detail: `${data.streamed_chunks || 0} response chunk(s) streamed.` };
    case "error":
      return { ...base, title: "Request failed", detail: sentenceCase(data.message || "Unknown backend error.") };
    default:
      return { ...base, title: sentenceCase(eventName.replaceAll("_", " ")), detail: "Additional backend activity received." };
  }
}

async function getJson(path) {
  const response = await fetch(buildUrl(path));
  if (!response.ok) {
    throw await toError(response);
  }
  return response.json();
}

async function postSse(path, payload, onEvent, signal) {
  const response = await fetch(buildUrl(path), {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    throw await toError(response);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Readable stream not supported in this browser.");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    buffer = processSseBuffer(buffer, onEvent);
    if (done) {
      break;
    }
  }

  if (buffer.trim()) {
    processSseChunk(buffer, onEvent);
  }
}

function processSseBuffer(buffer, onEvent) {
  const normalized = buffer.replaceAll("\r\n", "\n");
  const chunks = normalized.split("\n\n");
  const remainder = chunks.pop() || "";
  for (const chunk of chunks) {
    processSseChunk(chunk, onEvent);
  }
  return remainder;
}

function processSseChunk(chunk, onEvent) {
  const lines = chunk.split("\n");
  let eventName = "message";
  const dataLines = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  const payloadText = dataLines.join("\n");
  let payload = {};
  if (payloadText) {
    payload = JSON.parse(payloadText);
  }
  onEvent(eventName, payload);
}

async function toError(response) {
  const text = await response.text();
  try {
    const data = JSON.parse(text);
    return new Error(data.detail || data.message || response.statusText);
  } catch {
    return new Error(text || response.statusText);
  }
}

function buildUrl(path) {
  return `${normalizeApiBase(state.apiBase)}${path}`;
}

function normalizeApiBase(value) {
  return (value || DEFAULT_API_BASE).trim().replace(/\/+$/, "");
}

function loadJson(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key) || "null") ?? fallback;
  } catch {
    return fallback;
  }
}

function formatPersona(value) {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatPercent(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatSignedNumber(value) {
  return `${value > 0 ? "+" : ""}${value}`;
}

function capitalizeWords(value) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function trendClass(direction) {
  if (direction === "improving") {
    return "good";
  }
  if (direction === "worsening") {
    return "bad";
  }
  return "warn";
}

function normalizeAssistantContent(rawContent) {
  const text = String(rawContent || "").trim();
  if (!text) {
    return "";
  }

  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed === "object") {
      return formatStructuredResponse(parsed);
    }
  } catch {
    return text;
  }

  return text;
}

function formatStreamingAssistantContent(rawContent) {
  const text = String(rawContent || "");
  const normalized = normalizeAssistantContent(text);

  if (normalized !== text) {
    return normalized;
  }

  if (shouldSuppressRawStreamingContent(text)) {
    const preview = buildStructuredPreview(text);
    return preview || "";
  }

  if (!looksLikeStructuredPayload(text)) {
    return text;
  }

  const preview = buildStructuredPreview(text);
  return preview || "";
}

function formatStructuredResponse(payload) {
  const sections = [];

  if (typeof payload.message === "string" && payload.message.trim()) {
    sections.push(payload.message.trim());
  }

  if (Array.isArray(payload.causes) && payload.causes.length) {
    sections.push(`Main reasons: ${payload.causes.map(extractReadableText).filter(Boolean).join(" ")}`);
  }

  if (Array.isArray(payload.evidence) && payload.evidence.length) {
    sections.push(`Supporting evidence: ${payload.evidence.map(extractReadableText).filter(Boolean).join(" ")}`);
  }

  if (Array.isArray(payload.suggested_actions) && payload.suggested_actions.length) {
    sections.push(`Recommended actions: ${payload.suggested_actions.map(extractReadableText).filter(Boolean).join(" ")}`);
  }

  return sections.join("\n\n").trim();
}

function looksLikeStructuredPayload(value) {
  const text = String(value || "").trimStart();
  return text.startsWith("{") || text.startsWith("[");
}

function shouldSuppressRawStreamingContent(value) {
  const text = String(value || "").trimStart();
  if (!text) {
    return false;
  }

  return (
    text.startsWith("{") ||
    text.startsWith("[") ||
    text.startsWith("```json") ||
    text.startsWith("```") ||
    /"message"\s*:/.test(text) ||
    /"causes"\s*:/.test(text) ||
    /"evidence"\s*:/.test(text) ||
    /"suggested_actions"\s*:/.test(text)
  );
}

function buildStructuredPreview(rawContent) {
  const text = String(rawContent || "");
  const sections = [];

  const message = extractJsonStringField(text, "message");
  if (message) {
    sections.push(message);
  }

  const causes = extractJsonArrayValues(text, "causes");
  if (causes.length) {
    sections.push(`Main reasons: ${causes.join(" ")}`);
  }

  const evidence = extractJsonArrayValues(text, "evidence");
  if (evidence.length) {
    sections.push(`Supporting evidence: ${evidence.join(" ")}`);
  }

  const actions = extractJsonArrayValues(text, "suggested_actions");
  if (actions.length) {
    sections.push(`Recommended actions: ${actions.join(" ")}`);
  }

  return sections.join("\n\n").trim();
}

function extractJsonStringField(rawContent, fieldName) {
  const pattern = new RegExp(`"${escapeRegExp(fieldName)}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)"`);
  const match = rawContent.match(pattern);
  return match ? decodeJsonString(match[1]) : "";
}

function extractJsonArrayValues(rawContent, fieldName) {
  const keyIndex = rawContent.indexOf(`"${fieldName}"`);
  if (keyIndex === -1) {
    return [];
  }

  const arrayStart = rawContent.indexOf("[", keyIndex);
  if (arrayStart === -1) {
    return [];
  }

  let depth = 0;
  let inString = false;
  let escaped = false;
  let arrayEnd = -1;

  for (let index = arrayStart; index < rawContent.length; index += 1) {
    const char = rawContent[index];

    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === "\"") {
        inString = false;
      }
      continue;
    }

    if (char === "\"") {
      inString = true;
      continue;
    }

    if (char === "[") {
      depth += 1;
    } else if (char === "]") {
      depth -= 1;
      if (depth === 0) {
        arrayEnd = index;
        break;
      }
    }
  }

  const arrayText = rawContent.slice(arrayStart, arrayEnd === -1 ? rawContent.length : arrayEnd + 1);
  const values = [];
  const stringPattern = /"((?:\\.|[^"\\])*)"/g;

  for (const match of arrayText.matchAll(stringPattern)) {
    const decoded = decodeJsonString(match[1]);
    if (decoded) {
      values.push(decoded);
    }
  }

  return values;
}

function decodeJsonString(value) {
  try {
    return JSON.parse(`"${value}"`).trim();
  } catch {
    return value
      .replace(/\\"/g, "\"")
      .replace(/\\n/g, "\n")
      .replace(/\\\\/g, "\\")
      .trim();
  }
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function buildPlanDetail(data) {
  const tools = Array.isArray(data.tool_names) && data.tool_names.length
    ? `Tools selected: ${data.tool_names.map(formatToolName).join(", ")}.`
    : "No tools selected.";
  const retrieval = data.retrieval_needed ? "Knowledge retrieval is enabled." : "Knowledge retrieval is not needed.";
  const mode = data.execution_mode ? `Mode: ${prettyCategory(data.execution_mode)}.` : "";
  return [mode, tools, retrieval].filter(Boolean).join(" ");
}

function buildRetrievalResultDetail(data) {
  const titles = Array.isArray(data.document_titles) ? data.document_titles.filter(Boolean) : [];
  if (!titles.length) {
    return "No grounded knowledge documents were returned.";
  }
  return `Retrieved ${titles.length} document(s): ${titles.join(", ")}.`;
}

function formatToolDetail(toolName, reasoning) {
  const name = toolName ? formatToolName(toolName) : "Backend tool";
  return reasoning ? `${name}. ${sentenceCase(reasoning)}` : `${name} started.`;
}

function formatToolName(value) {
  return String(value || "")
    .replace(/^get_/, "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function prettyCategory(value) {
  if (!value) {
    return "General";
  }
  return String(value)
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function sentenceCase(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function extractReadableText(value) {
  if (typeof value === "string") {
    return value.trim();
  }
  if (!value || typeof value !== "object") {
    return "";
  }

  const parts = [
    value.title,
    value.detail,
    value.action,
    value.text,
    value.message,
    value.citation,
  ]
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean);

  return parts.join(". ");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
