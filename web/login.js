const loginState = {
  isDemoLoginEnabled: true,
};

document.addEventListener("DOMContentLoaded", () => {
  const existingSession = getAuthSession();
  if (existingSession?.redirect_path) {
    window.location.href = existingSession.redirect_path;
    return;
  }

  bindEvents();
  initializeLogin().catch(handleUnexpectedError);
});

async function initializeLogin() {
  const authConfig = await apiRequest("/auth/config");
  loginState.isDemoLoginEnabled = Boolean(authConfig?.demo_login_enabled);
  toggleDemoCredentialsPanel(loginState.isDemoLoginEnabled);
  applyCredentialHint();
}

function bindEvents() {
  document.getElementById("login-role-select").addEventListener("change", applyCredentialHint);
  document.getElementById("login-form").addEventListener("submit", (event) => {
    event.preventDefault();
    login().catch(handleUnexpectedError);
  });
}

function applyCredentialHint() {
  if (!loginState.isDemoLoginEnabled) {
    setStatus("Demo login is disabled on this deployment.");
    return;
  }
  const role = document.getElementById("login-role-select").value;
  if (role === "admin") {
    document.getElementById("login-username-input").value = "admin@braingain.local";
    document.getElementById("login-password-input").value = "admin123";
    setStatus("Admin demo credentials loaded.");
    return;
  }
  document.getElementById("login-username-input").value = "student@braingain.local";
  document.getElementById("login-password-input").value = "student123";
  setStatus("Student demo credentials loaded.");
}

async function login() {
  if (!loginState.isDemoLoginEnabled) {
    throw new Error("Demo login is disabled. Configure real authentication before using this deployment.");
  }
  const payload = {
    role: document.getElementById("login-role-select").value,
    username: document.getElementById("login-username-input").value.trim(),
    password: document.getElementById("login-password-input").value,
  };
  const response = await apiRequest("/demo-login", "POST", payload);
  setAuthSession(response);
  window.location.href = response.redirect_path;
}

function toggleDemoCredentialsPanel(isVisible) {
  const panel = document.getElementById("demo-credentials-panel");
  if (!panel) {
    return;
  }
  panel.style.display = isVisible ? "" : "none";
}

async function apiRequest(url, method = "GET", body = undefined) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  const response = await fetch(url, options);
  const responseText = await response.text();
  const responseData = responseText ? tryParseJson(responseText) : null;
  if (!response.ok) {
    const detail = typeof responseData === "object" && responseData?.detail ? responseData.detail : responseData;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail, null, 2));
  }
  return responseData;
}

function setStatus(message, isError = false) {
  const banner = document.getElementById("login-status-banner");
  banner.textContent = message;
  banner.classList.toggle("is-error", isError);
}

function tryParseJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function handleUnexpectedError(error) {
  setStatus(error?.message ?? "Unexpected frontend error.", true);
}
