const BRAINGAIN_AUTH_STORAGE_KEY = "braingain_demo_auth";

function getAuthSession() {
  try {
    const rawValue = window.localStorage.getItem(BRAINGAIN_AUTH_STORAGE_KEY);
    return rawValue ? JSON.parse(rawValue) : null;
  } catch {
    return null;
  }
}

function setAuthSession(session) {
  window.localStorage.setItem(BRAINGAIN_AUTH_STORAGE_KEY, JSON.stringify(session));
}

function clearAuthSession() {
  window.localStorage.removeItem(BRAINGAIN_AUTH_STORAGE_KEY);
}

function requireRole(expectedRole) {
  const session = getAuthSession();
  if (!session || session.role !== expectedRole) {
    window.location.href = "/";
    return null;
  }
  return session;
}

function redirectAuthenticatedUser() {
  const session = getAuthSession();
  if (!session?.redirect_path) {
    return null;
  }
  window.location.href = session.redirect_path;
  return session;
}

function bindLogoutButton(buttonId = "logout-button") {
  const button = document.getElementById(buttonId);
  if (!button) {
    return;
  }
  button.addEventListener("click", () => {
    clearAuthSession();
    window.location.href = "/";
  });
}

function renderSessionIdentity(elementId, fallbackLabel) {
  const element = document.getElementById(elementId);
  if (!element) {
    return;
  }
  const session = getAuthSession();
  if (!session) {
    element.textContent = fallbackLabel;
    return;
  }
  const roleLabel = String(session.role || fallbackLabel || "").replace(/^./, (character) => character.toUpperCase());
  const displayName = session.display_name || roleLabel;
  element.textContent = `${displayName} | ${roleLabel}`;
}
