const projectRoot = "/home/harsh-suryawanshi/projects/BrainGain";
const ACTIVE_ATTEMPT_STORAGE_KEY = "braingain_active_attempt_id";
const LATEST_RESULT_STORAGE_KEY = "braingain_latest_submitted_attempt";
const DEFAULT_ATTEMPT_DURATION_MINUTES = 30;
const SECONDS_PER_QUESTION = 120;
const RUNNER_WINDOW_NAME = "braingain_attempt_runner";

const state = {
  tests: [],
  selectedTestId: "",
  currentAttempt: null,
  activeQuestionIndex: 0,
  autosaveHandle: null,
  timerIntervalId: null,
  runnerWindow: null,
  studentResults: [],
};

document.addEventListener("DOMContentLoaded", () => {
  const session = requireRole("student");
  if (!session) {
    return;
  }
  hydrateStudentIdentity(session);
  renderSessionIdentity("student-session-identity", "Student");
  bindLogoutButton();
  bindEvents();
  renderTests([]);
  renderAttempt(null);
  renderResults(null);
  renderStudentOverview();
  applyPageMode();
  bindDashboardEvents();
  initializePage().catch(handleUnexpectedError);
});

async function initializePage() {
  await loadTests({ showStatus: false });
  await restoreAttemptFromStorage();
  await loadStudentResults({ showStatus: false });
  renderStudentOverview();
  if (!state.currentAttempt) {
    setStatus(state.tests.length ? "Choose a test to begin." : "No tests are available yet.");
  }
}

function bindDashboardEvents() {
  for (const elementId of ["student-name-input", "student-roll-number-input", "student-email-input"]) {
    document.getElementById(elementId).addEventListener("change", () => {
      loadStudentResults({ showStatus: false }).catch(handleUnexpectedError);
    });
  }
  window.addEventListener("focus", () => {
    loadStudentResults({ showStatus: false }).catch(() => {});
  });
  window.addEventListener("storage", (event) => {
    if (event.key === LATEST_RESULT_STORAGE_KEY) {
      loadStudentResults({ showStatus: false }).catch(() => {});
    }
  });
}

function bindEvents() {
  document.getElementById("refresh-tests-button").addEventListener("click", () => {
    loadTests().catch(handleUnexpectedError);
  });
  document.getElementById("load-public-tests-button").addEventListener("click", () => {
    loadTests().catch(handleUnexpectedError);
  });
  document.getElementById("take-another-test-button").addEventListener("click", () => {
    document.getElementById("public-tests-list").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  document.getElementById("start-attempt-button").addEventListener("click", () => {
    startAttempt().catch(handleUnexpectedError);
  });
  document.getElementById("previous-question-button").addEventListener("click", () => {
    goToQuestion(state.activeQuestionIndex - 1).catch(handleUnexpectedError);
  });
  document.getElementById("save-next-button").addEventListener("click", () => {
    saveAndAdvance().catch(handleUnexpectedError);
  });
  document.getElementById("mark-review-button").addEventListener("click", () => {
    toggleCurrentQuestionReview().catch(handleUnexpectedError);
  });
  document.getElementById("clear-response-button").addEventListener("click", () => {
    clearCurrentQuestionResponse().catch(handleUnexpectedError);
  });
  document.getElementById("submit-attempt-button").addEventListener("click", () => {
    submitAttempt().catch(handleUnexpectedError);
  });

  const questionStage = document.getElementById("question-stage");
  questionStage.addEventListener("input", (event) => {
    if (!(event.target instanceof HTMLElement)) {
      return;
    }
    if (event.target.matches("input[type='number']")) {
      syncCurrentQuestionFromDom();
      renderAttemptSummary();
      renderQuestionPalette();
      renderStudentOverview();
    }
  });
  questionStage.addEventListener("change", () => {
    syncCurrentQuestionFromDom();
    renderAttemptSummary();
    renderQuestionPalette();
    renderStudentOverview();
    scheduleAutosave();
  });
}

async function loadTests({ showStatus = true } = {}) {
  const tests = await apiRequest("/tests");
  state.tests = tests;
  if (
    (!state.selectedTestId || !tests.some((test) => test.id === state.selectedTestId)) &&
    state.currentAttempt?.test_id &&
    tests.some((test) => test.id === state.currentAttempt.test_id)
  ) {
    state.selectedTestId = state.currentAttempt.test_id;
  } else if ((!state.selectedTestId || !tests.some((test) => test.id === state.selectedTestId)) && tests.length) {
    state.selectedTestId = tests[0].id;
  }
  const selectedTestInput = document.getElementById("selected-test-id");
  selectedTestInput.value = state.selectedTestId || "";
  renderTests(tests);
  renderStudentOverview();
  if (showStatus) {
    setStatus("Available tests refreshed.");
  }
}

function renderTests(tests) {
  const container = document.getElementById("public-tests-list");
  const startButton = document.getElementById("start-attempt-button");
  startButton.disabled = !tests.length || state.currentAttempt?.status === "in_progress";
  if (!tests.length) {
    container.innerHTML = "<div class=\"list-card\">No tests are available yet. Ask the admin to generate one first.</div>";
    return;
  }

  container.innerHTML = "";
  for (const test of tests) {
    const card = document.createElement("article");
    const isSelected = test.id === state.selectedTestId;
    const estimatedMinutes = calculateTimeLimitMinutes(test.question_count);
    card.className = `list-card is-selectable${isSelected ? " is-selected" : ""}`;
    card.innerHTML = `
      <strong>${escapeHtml(test.title)}</strong>
      <div>${escapeHtml(test.subject_name)}${test.chapter_name ? ` | Chapter ${escapeHtml(test.chapter_number)}: ${escapeHtml(test.chapter_name)}` : ""}</div>
      <div>Questions: ${escapeHtml(test.question_count)} | Hard: ${escapeHtml(test.hard_question_count)} | Attempts: ${escapeHtml(test.attempt_count)}</div>
      <div class="helper-text">Estimated time: ${escapeHtml(estimatedMinutes)} minutes</div>
    `;
    card.addEventListener("click", () => {
      if (state.currentAttempt?.status === "in_progress") {
        setStatus("Finish or submit the active attempt before starting another test.", true);
        return;
      }
      state.selectedTestId = test.id;
      document.getElementById("selected-test-id").value = test.id;
      renderTests(state.tests);
      renderStudentOverview();
      setStatus(`Selected test: ${test.title}`);
    });
    container.appendChild(card);
  }
}

async function restoreAttemptFromStorage() {
  const attemptId = getStoredAttemptId();
  if (!attemptId) {
    return;
  }
  try {
    const attempt = await apiRequest(`/attempts/${attemptId}`);
    syncAttempt(attempt);
    if (attempt.status === "in_progress") {
      setStatus(`Resumed test: ${attempt.test.title}`);
      await ensureCurrentQuestionVisited();
    } else {
      setStatus(`Loaded submitted test: ${attempt.test.title}`);
    }
  } catch (error) {
    clearStoredAttemptId();
    if (error?.message) {
      setStatus("Saved attempt could not be restored. Start a fresh test.", true);
    }
  }
}

async function startAttempt() {
  if (state.currentAttempt?.status === "in_progress") {
    throw new Error("Submit the active attempt before starting another test.");
  }
  if (!state.selectedTestId) {
    throw new Error("Select a test first.");
  }
  const fullName = document.getElementById("student-name-input").value.trim();
  if (!fullName) {
    throw new Error("Enter the student name before starting the test.");
  }
  const runnerWindow = openAttemptRunnerShell();

  const attempt = await apiRequest("/attempts/start", "POST", {
    test_id: state.selectedTestId,
    full_name: fullName,
    roll_number: document.getElementById("student-roll-number-input").value.trim() || null,
    email: document.getElementById("student-email-input").value.trim() || null,
  });
  syncAttempt(attempt);
  renderResults(null);
  setStatus(attempt.was_resumed ? `Resumed test: ${attempt.test.title}` : `Started test: ${attempt.test.title}`);
  openAttemptRunnerWindow(attempt.id, runnerWindow);
  await ensureCurrentQuestionVisited();
}

async function goToQuestion(index) {
  if (!state.currentAttempt?.test?.questions?.length) {
    return;
  }
  const clampedIndex = Math.max(0, Math.min(index, state.currentAttempt.test.questions.length - 1));
  await flushAutosave();
  state.activeQuestionIndex = clampedIndex;
  renderAttempt(state.currentAttempt);
  await ensureCurrentQuestionVisited();
}

async function saveAndAdvance() {
  const currentQuestion = getCurrentQuestion();
  if (!currentQuestion) {
    throw new Error("Start a test first.");
  }
  syncCurrentQuestionFromDom();
  await saveQuestionDraft(currentQuestion, { showStatus: true });
  if (state.currentAttempt?.status !== "in_progress") {
    return;
  }
  if (state.activeQuestionIndex >= state.currentAttempt.test.questions.length - 1) {
    setStatus("Last question saved. Submit the test when you are ready.");
    return;
  }
  state.activeQuestionIndex += 1;
  renderAttempt(state.currentAttempt);
  await ensureCurrentQuestionVisited();
}

async function toggleCurrentQuestionReview() {
  const currentQuestion = getCurrentQuestion();
  if (!currentQuestion) {
    throw new Error("Start a test first.");
  }
  syncCurrentQuestionFromDom();
  currentQuestion.answer_data.is_marked_for_review = !currentQuestion.answer_data.is_marked_for_review;
  currentQuestion.answer_data.has_visited = true;
  markQuestionState(currentQuestion);
  currentQuestion.is_dirty = true;
  renderAttempt(state.currentAttempt);
  await saveQuestionDraft(currentQuestion, {
    showStatus: true,
    statusMessage: currentQuestion.answer_data.is_marked_for_review ? "Marked for review." : "Removed review marker.",
  });
}

async function clearCurrentQuestionResponse() {
  const currentQuestion = getCurrentQuestion();
  if (!currentQuestion) {
    throw new Error("Start a test first.");
  }
  currentQuestion.answer_data.option_labels = [];
  currentQuestion.answer_data.numeric_value = null;
  currentQuestion.answer_data.pair_mapping = {};
  currentQuestion.answer_data.has_visited = true;
  markQuestionState(currentQuestion);
  currentQuestion.is_dirty = true;
  renderAttempt(state.currentAttempt);
  await saveQuestionDraft(currentQuestion, { showStatus: true, statusMessage: "Response cleared." });
}

async function submitAttempt({ isAuto = false } = {}) {
  if (!state.currentAttempt) {
    throw new Error("Start a test first.");
  }
  clearAutosaveHandle();
  syncCurrentQuestionFromDom();
  const answers = state.currentAttempt.test.questions.map((question) => {
    return buildSubmissionPayload(question);
  });
  const attempt = await apiRequest(`/attempts/${state.currentAttempt.id}/submit`, "POST", { answers });
  syncAttempt(attempt);
  storeLatestSubmittedAttempt(attempt);
  await loadStudentResults({ showStatus: false });
  renderResults(attempt);
  setStatus(isAuto ? `Time finished. Test auto-submitted with score ${attempt.score}%.` : `Submitted test. Score: ${attempt.score}%`);
}

async function ensureCurrentQuestionVisited() {
  const currentQuestion = getCurrentQuestion();
  if (!currentQuestion || state.currentAttempt?.status !== "in_progress" || currentQuestion.has_visited) {
    return;
  }
  currentQuestion.answer_data.has_visited = true;
  markQuestionState(currentQuestion);
  currentQuestion.is_dirty = true;
  renderAttemptSummary();
  renderQuestionPalette();
  renderStudentOverview();
  await saveQuestionDraft(currentQuestion, { showStatus: false });
}

function scheduleAutosave() {
  if (state.currentAttempt?.status !== "in_progress") {
    return;
  }
  clearAutosaveHandle();
  state.autosaveHandle = window.setTimeout(() => {
    const currentQuestion = getCurrentQuestion();
    if (!currentQuestion) {
      return;
    }
    saveQuestionDraft(currentQuestion, { showStatus: false }).catch(handleUnexpectedError);
  }, 500);
}

async function flushAutosave() {
  clearAutosaveHandle();
  const currentQuestion = getCurrentQuestion();
  if (!currentQuestion || !currentQuestion.is_dirty) {
    return;
  }
  syncCurrentQuestionFromDom();
  await saveQuestionDraft(currentQuestion, { showStatus: false });
}

async function saveQuestionDraft(question, { showStatus = false, statusMessage = "Progress saved." } = {}) {
  if (!question || state.currentAttempt?.status !== "in_progress" || !question.is_dirty) {
    return;
  }
  const preservedQuestionId = question.test_question_revision_id;
  const attempt = await apiRequest(
    `/attempts/${state.currentAttempt.id}/answers/${question.test_question_revision_id}`,
    "PUT",
    buildDraftPayload(question),
  );
  syncAttempt(attempt, preservedQuestionId);
  if (showStatus && attempt.status === "in_progress") {
    setStatus(statusMessage);
  }
}

function syncCurrentQuestionFromDom() {
  const currentQuestion = getCurrentQuestion();
  if (!currentQuestion || state.currentAttempt?.status !== "in_progress") {
    return;
  }
  const questionElement = document.querySelector("[data-question-id]");
  if (!questionElement) {
    return;
  }
  const nextAnswerData = readQuestionAnswerFromDom(currentQuestion, questionElement);
  currentQuestion.answer_data = nextAnswerData;
  markQuestionState(currentQuestion);
  currentQuestion.is_dirty = true;
}

function readQuestionAnswerFromDom(question, questionElement) {
  const questionFormat = question.question_format || question.format;
  const answerData = cloneAnswerData(question.answer_data);
  answerData.has_visited = true;
  if (questionFormat === "mcq" || questionFormat === "msq") {
    answerData.option_labels = Array.from(questionElement.querySelectorAll("input[type='radio']:checked, input[type='checkbox']:checked")).map((inputElement) => {
      return inputElement.value;
    });
    return answerData;
  }
  if (questionFormat === "nat") {
    const numericInput = questionElement.querySelector("input[type='number']");
    const rawValue = numericInput?.value.trim() || "";
    answerData.numeric_value = rawValue === "" ? null : Number(rawValue);
    return answerData;
  }
  answerData.pair_mapping = {};
  for (const selectElement of questionElement.querySelectorAll("select[data-left-label]")) {
    if (selectElement.value) {
      answerData.pair_mapping[selectElement.getAttribute("data-left-label")] = selectElement.value;
    }
  }
  return answerData;
}

function buildDraftPayload(question) {
  return {
    option_labels: question.answer_data.option_labels || [],
    numeric_value: question.answer_data.numeric_value ?? null,
    pair_mapping: question.answer_data.pair_mapping || {},
    is_marked_for_review: Boolean(question.answer_data.is_marked_for_review),
    has_visited: Boolean(question.answer_data.has_visited),
    spent_seconds: Number(question.answer_data.spent_seconds || 0),
  };
}

function buildSubmissionPayload(question) {
  return {
    test_question_revision_id: question.test_question_revision_id,
    ...buildDraftPayload(question),
  };
}

function syncAttempt(attempt, preservedQuestionId = null) {
  state.currentAttempt = attempt;
  if (!attempt) {
    clearStoredAttemptId();
    stopAttemptTimer();
    renderAttempt(null);
    renderResults(null);
    renderStudentOverview();
    return;
  }

  state.selectedTestId = attempt.test_id || attempt.test?.id || state.selectedTestId;
  document.getElementById("selected-test-id").value = state.selectedTestId || "";
  for (const question of attempt.test.questions) {
    question.is_dirty = false;
  }

  const currentQuestionId = preservedQuestionId || getCurrentQuestion()?.test_question_revision_id;
  if (currentQuestionId) {
    const nextIndex = attempt.test.questions.findIndex((question) => question.test_question_revision_id === currentQuestionId);
    state.activeQuestionIndex = nextIndex >= 0 ? nextIndex : 0;
  } else {
    state.activeQuestionIndex = findPreferredQuestionIndex(attempt);
  }

  if (attempt.status === "in_progress") {
    setStoredAttemptId(attempt.id);
    startAttemptTimer();
  } else {
    clearStoredAttemptId();
    stopAttemptTimer();
  }

  renderTests(state.tests);
  renderAttempt(attempt);
  renderResults(attempt.status === "in_progress" ? null : attempt);
  renderStudentOverview();
  if (attempt?.id && getIsRunnerMode()) {
    enforceAttemptProtection();
  }
}

function findPreferredQuestionIndex(attempt) {
  const unansweredIndex = attempt.test.questions.findIndex((question) => {
    return question.answer_state === "not_visited" || question.answer_state === "not_answered";
  });
  return unansweredIndex >= 0 ? unansweredIndex : 0;
}

function renderAttempt(attempt) {
  renderAttemptSummary();
  renderQuestionStateLegend();
  renderQuestionPalette();
  renderQuestionStage(attempt);
  renderAttemptButtons(attempt);
}

function renderAttemptSummary() {
  const container = document.getElementById("attempt-summary");
  const attempt = state.currentAttempt;
  if (!attempt) {
    container.innerHTML = "<div class=\"list-card\">No active attempt yet.</div>";
    return;
  }

  const timerClassName = buildTimerClassName(attempt.remaining_seconds);
  const answeredCount = attempt.answered_question_count ?? 0;
  const markedCount = attempt.marked_for_review_count ?? 0;
  container.innerHTML = `
    <div class="summary-grid">
      <article class="summary-card">
        <span class="helper-text">Student</span>
        <strong>${escapeHtml(attempt.student_name)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Test</span>
        <strong>${escapeHtml(attempt.test.title)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Timer</span>
        <strong class="${timerClassName}">${escapeHtml(formatRemainingSeconds(attempt.remaining_seconds))}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Progress</span>
        <strong>${escapeHtml(answeredCount)}/${escapeHtml(attempt.test.questions.length)}</strong>
      </article>
    </div>
    <article class="list-card">
      <strong>Attempt State</strong>
      <div>Status: ${escapeHtml(formatAttemptStatus(attempt.status))}</div>
      <div>Marked for review: ${escapeHtml(markedCount)}</div>
      <div>Auto-submit at: ${escapeHtml(formatTimestamp(attempt.expires_at))}</div>
    </article>
  `;
}

function renderQuestionStateLegend() {
  const container = document.getElementById("question-state-legend");
  const attempt = state.currentAttempt;
  if (!attempt) {
    container.innerHTML = "<div class=\"helper-text\">Question state counts appear here after the test starts.</div>";
    return;
  }
  const summary = attempt.question_state_summary || {};
  container.innerHTML = `
    <div class="legend-row"><span class="legend-swatch" data-state="not_visited"></span>Not visited: ${escapeHtml(summary.not_visited || 0)}</div>
    <div class="legend-row"><span class="legend-swatch" data-state="not_answered"></span>Visited, no answer: ${escapeHtml(summary.not_answered || 0)}</div>
    <div class="legend-row"><span class="legend-swatch" data-state="answered"></span>Answered: ${escapeHtml(summary.answered || 0)}</div>
    <div class="legend-row"><span class="legend-swatch" data-state="marked_for_review"></span>Marked: ${escapeHtml(summary.marked_for_review || 0)}</div>
    <div class="legend-row"><span class="legend-swatch" data-state="answered_and_marked_for_review"></span>Answered + marked: ${escapeHtml(summary.answered_and_marked_for_review || 0)}</div>
  `;
}

function renderQuestionPalette() {
  const container = document.getElementById("question-palette");
  const attempt = state.currentAttempt;
  if (!attempt?.test?.questions?.length) {
    container.innerHTML = "<div class=\"helper-text\">No questions loaded.</div>";
    return;
  }

  container.innerHTML = "";
  attempt.test.questions.forEach((question, index) => {
    const button = document.createElement("button");
    const answerState = question.answer_state || "not_visited";
    button.type = "button";
    button.className = `palette-button${index === state.activeQuestionIndex ? " is-active" : ""}`;
    button.setAttribute("data-state", answerState);
    button.innerHTML = `
      <strong>Q${escapeHtml(question.display_order)}</strong>
      <span>${escapeHtml(formatAnswerStateLabel(answerState))}</span>
    `;
    button.addEventListener("click", () => {
      goToQuestion(index).catch(handleUnexpectedError);
    });
    container.appendChild(button);
  });
}

function renderQuestionStage(attempt) {
  const emptyState = document.getElementById("attempt-empty-state");
  const stage = document.getElementById("question-stage");
  if (!attempt?.test?.questions?.length) {
    emptyState.style.display = "block";
    stage.innerHTML = "";
    return;
  }

  emptyState.style.display = "none";
  const question = getCurrentQuestion();
  if (!question) {
    stage.innerHTML = "<div class=\"attempt-empty-state\">No question selected.</div>";
    return;
  }
  const questionFormat = question.question_format || question.format;
  const figuresMarkup = (question.figures || [])
    .map((figure) => {
      return `<img class="attempt-figure" src="${escapeHtml(buildProjectFileUrl(figure.file_path))}" alt="${escapeHtml(figure.name)}">`;
    })
    .join("");

  stage.innerHTML = `
    <article class="runner-question-card quiz-card" data-question-id="${escapeHtml(question.test_question_revision_id)}" data-question-format="${escapeHtml(questionFormat)}">
      <div class="question-toolbar">
        <div>
          <div class="status-pill">Question ${escapeHtml(question.display_order)} of ${escapeHtml(attempt.test.questions.length)}</div>
          <h3>${escapeHtml(question.text)}</h3>
          <div class="helper-text">${escapeHtml(questionFormat.toUpperCase())} | ${escapeHtml(question.difficulty)} | ${escapeHtml(question.type)}</div>
        </div>
        <div class="question-progress-copy">
          <strong>${escapeHtml(formatAnswerStateLabel(question.answer_state || "not_visited"))}</strong>
          <span id="current-question-spent-seconds">${escapeHtml(formatSpentSeconds(question.answer_data?.spent_seconds || 0))}</span>
        </div>
      </div>
      ${figuresMarkup ? `<div class="card-grid">${figuresMarkup}</div>` : ""}
      ${buildQuestionInputMarkup(question, {
        isDisabled: attempt.status !== "in_progress",
      })}
    </article>
  `;
}

function renderAttemptButtons(attempt) {
  const hasAttempt = Boolean(attempt?.test?.questions?.length);
  const isInProgress = attempt?.status === "in_progress";
  const previousButton = document.getElementById("previous-question-button");
  const saveNextButton = document.getElementById("save-next-button");
  const markReviewButton = document.getElementById("mark-review-button");
  const clearResponseButton = document.getElementById("clear-response-button");
  const submitButton = document.getElementById("submit-attempt-button");

  previousButton.disabled = !hasAttempt || !isInProgress || state.activeQuestionIndex === 0;
  saveNextButton.disabled = !hasAttempt || !isInProgress;
  markReviewButton.disabled = !hasAttempt || !isInProgress;
  clearResponseButton.disabled = !hasAttempt || !isInProgress;
  submitButton.disabled = !hasAttempt || !isInProgress;

  const currentQuestion = getCurrentQuestion();
  markReviewButton.textContent = currentQuestion?.answer_data?.is_marked_for_review ? "Unmark Review" : "Mark For Review";
  saveNextButton.textContent =
    hasAttempt && state.activeQuestionIndex >= (attempt?.test?.questions?.length || 0) - 1 ? "Save Response" : "Save And Next";
}

function renderResults(attempt) {
  const container = document.getElementById("attempt-results");
  if (!attempt || attempt.status === "in_progress") {
    container.innerHTML = "<div class=\"list-card\">Submit a test to see the score and per-question feedback.</div>";
    return;
  }

  container.innerHTML = `
    <div class="summary-grid">
      <article class="summary-card">
        <span class="helper-text">Score</span>
        <strong>${escapeHtml(attempt.score)}%</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Correct</span>
        <strong>${escapeHtml(attempt.correct_answer_count)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Wrong</span>
        <strong>${escapeHtml(attempt.wrong_answer_count)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Submitted</span>
        <strong>${escapeHtml(formatTimestamp(attempt.submitted_at))}</strong>
      </article>
    </div>
  `;

  for (const question of attempt.test.questions) {
    const questionFormat = question.question_format || question.format;
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <strong>${escapeHtml(question.text)}</strong>
      <div class="${question.is_correct ? "result-good" : "result-bad"}">${question.is_correct ? "Correct" : "Incorrect"}</div>
      <div>Saved state: ${escapeHtml(formatAnswerStateLabel(question.answer_state || "not_visited"))}</div>
      <div>Your answer: ${escapeHtml(formatSubmittedAnswer(question))}</div>
      <div>Correct answer: ${escapeHtml(formatCorrectAnswer(question, questionFormat))}</div>
      <div>Time on question: ${escapeHtml(formatSpentSeconds(question.answer_data?.spent_seconds || 0))}</div>
    `;
    container.appendChild(card);
  }
}

function renderStudentOverview() {
  const container = document.getElementById("student-overview");
  const selectedTest = state.tests.find((test) => test.id === state.selectedTestId);
  const attempt = state.currentAttempt;
  const latestResult = state.studentResults[0] || null;
  container.innerHTML = `
    <div class="summary-grid">
      <article class="summary-card">
        <span class="helper-text">Available Tests</span>
        <strong>${escapeHtml(state.tests.length)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Selected Test</span>
        <strong>${escapeHtml(selectedTest?.title || "None selected")}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Attempt Status</span>
        <strong>${escapeHtml(formatAttemptStatus(attempt?.status || "not_started"))}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Time Left</span>
        <strong>${escapeHtml(attempt?.status === "in_progress" ? formatRemainingSeconds(attempt.remaining_seconds) : "-")}</strong>
      </article>
    </div>
    <article class="list-card">
      <strong>Right Now</strong>
      <div>${escapeHtml(buildOverviewCopy(selectedTest, attempt))}</div>
    </article>
    <article class="list-card">
      <strong>Latest Result</strong>
      <div>${escapeHtml(latestResult ? `${latestResult.test.title} | Score ${latestResult.score}%` : "No submitted results yet.")}</div>
      ${latestResult ? `<div class="helper-text">Correct: ${escapeHtml(latestResult.correct_answer_count)} | Wrong: ${escapeHtml(latestResult.wrong_answer_count)} | Submitted: ${escapeHtml(formatTimestamp(latestResult.submitted_at))}</div>` : ""}
    </article>
  `;
}

function buildOverviewCopy(selectedTest, attempt) {
  if (attempt?.status === "in_progress") {
    return `You are taking ${attempt.test.title}. ${attempt.answered_question_count || 0} of ${attempt.test.questions.length} questions are answered.`;
  }
  if (attempt?.status === "submitted") {
    return `Latest submitted test: ${attempt.test.title}. Score: ${attempt.score}%.`;
  }
  if (selectedTest) {
    return `You can start ${selectedTest.title} when ready.`;
  }
  return "Wait for the admin to publish a test.";
}

function buildQuestionInputMarkup(question, { isDisabled }) {
  const answerData = question.answer_data || buildBlankAnswerData();
  const questionFormat = question.question_format || question.format;
  if (questionFormat === "nat") {
    return `
      <div class="form-stack">
        <label class="field">
          <span>Numeric Answer${question.numeric_answer?.unit ? ` (${escapeHtml(question.numeric_answer.unit)})` : ""}</span>
          <input type="number" step="any" value="${answerData.numeric_value ?? ""}" ${isDisabled ? "disabled" : ""}>
        </label>
      </div>
    `;
  }
  if (questionFormat === "match") {
    const rows = (question.columns?.items_a || [])
      .map((item) => {
        const selected = answerData.pair_mapping?.[item.label] || "";
        return `
          <label class="field">
            <span>${escapeHtml(item.label)}. ${escapeHtml(item.text)}</span>
            <select data-left-label="${escapeHtml(item.label)}" ${isDisabled ? "disabled" : ""}>
              <option value="">Choose match</option>
              ${(question.columns?.items_b || [])
                .map((rightItem) => {
                  const isSelected = selected === rightItem.label ? "selected" : "";
                  return `<option value="${escapeHtml(rightItem.label)}" ${isSelected}>${escapeHtml(rightItem.label)}. ${escapeHtml(rightItem.text)}</option>`;
                })
                .join("")}
            </select>
          </label>
        `;
      })
      .join("");
    return `
      <div class="helper-text">${escapeHtml(question.columns?.a_heading || "Column A")} -> ${escapeHtml(question.columns?.b_heading || "Column B")}</div>
      <div class="form-stack">${rows}</div>
    `;
  }
  const inputType = questionFormat === "mcq" ? "radio" : "checkbox";
  return `
    <div class="form-stack">
      ${question.options
        .map((option) => {
          const isChecked = (answerData.option_labels || []).includes(option.label) ? "checked" : "";
          return `
            <label class="option-choice">
              <input type="${inputType}" name="question-${escapeHtml(question.test_question_revision_id)}" value="${escapeHtml(option.label)}" ${isChecked} ${isDisabled ? "disabled" : ""}>
              <span><strong>${escapeHtml(option.label)}.</strong> ${escapeHtml(option.text)}</span>
            </label>
          `;
        })
        .join("")}
    </div>
  `;
}

function markQuestionState(question) {
  question.is_answered = hasAnswerContent(question.answer_data);
  question.is_marked_for_review = Boolean(question.answer_data.is_marked_for_review);
  question.has_visited = Boolean(question.answer_data.has_visited);
  question.answer_state = deriveAnswerState(question.answer_data);
  if (state.currentAttempt?.question_state_summary) {
    state.currentAttempt.question_state_summary = buildQuestionStateSummary(state.currentAttempt.test.questions);
    state.currentAttempt.answered_question_count =
      state.currentAttempt.question_state_summary.answered + state.currentAttempt.question_state_summary.answered_and_marked_for_review;
    state.currentAttempt.marked_for_review_count =
      state.currentAttempt.question_state_summary.marked_for_review +
      state.currentAttempt.question_state_summary.answered_and_marked_for_review;
  }
}

function buildQuestionStateSummary(questions) {
  const summary = {
    total: questions.length,
    not_visited: 0,
    not_answered: 0,
    answered: 0,
    marked_for_review: 0,
    answered_and_marked_for_review: 0,
  };
  for (const question of questions) {
    const answerState = question.answer_state || deriveAnswerState(question.answer_data || buildBlankAnswerData());
    summary[answerState] += 1;
  }
  return summary;
}

function hasAnswerContent(answerData) {
  if (!answerData) {
    return false;
  }
  if (answerData.numeric_value !== null && answerData.numeric_value !== undefined && answerData.numeric_value !== "") {
    return true;
  }
  if ((answerData.option_labels || []).length) {
    return true;
  }
  return Object.keys(answerData.pair_mapping || {}).length > 0;
}

function deriveAnswerState(answerData) {
  const isAnswered = hasAnswerContent(answerData);
  const isMarked = Boolean(answerData?.is_marked_for_review);
  if (isMarked && isAnswered) {
    return "answered_and_marked_for_review";
  }
  if (isMarked) {
    return "marked_for_review";
  }
  if (isAnswered) {
    return "answered";
  }
  if (answerData?.has_visited) {
    return "not_answered";
  }
  return "not_visited";
}

function buildBlankAnswerData() {
  return {
    option_labels: [],
    numeric_value: null,
    pair_mapping: {},
    is_marked_for_review: false,
    has_visited: false,
    spent_seconds: 0,
    last_saved_at: null,
  };
}

function cloneAnswerData(answerData) {
  return {
    option_labels: [...(answerData?.option_labels || [])],
    numeric_value: answerData?.numeric_value ?? null,
    pair_mapping: { ...(answerData?.pair_mapping || {}) },
    is_marked_for_review: Boolean(answerData?.is_marked_for_review),
    has_visited: Boolean(answerData?.has_visited),
    spent_seconds: Number(answerData?.spent_seconds || 0),
    last_saved_at: answerData?.last_saved_at || null,
  };
}

function getCurrentQuestion() {
  const questions = state.currentAttempt?.test?.questions || [];
  if (!questions.length) {
    return null;
  }
  return questions[state.activeQuestionIndex] || questions[0];
}

function startAttemptTimer() {
  stopAttemptTimer();
  if (state.currentAttempt?.status !== "in_progress") {
    return;
  }
  state.timerIntervalId = window.setInterval(() => {
    if (state.currentAttempt?.status !== "in_progress") {
      stopAttemptTimer();
      return;
    }
    if (typeof state.currentAttempt.remaining_seconds === "number") {
      state.currentAttempt.remaining_seconds = Math.max(0, state.currentAttempt.remaining_seconds - 1);
    }
    const currentQuestion = getCurrentQuestion();
    if (currentQuestion) {
      currentQuestion.answer_data.spent_seconds = Number(currentQuestion.answer_data.spent_seconds || 0) + 1;
      currentQuestion.is_dirty = true;
    }
    renderAttemptSummary();
    updateLiveAttemptMetrics();
    renderStudentOverview();
    if (state.currentAttempt.remaining_seconds === 0) {
      stopAttemptTimer();
      submitAttempt({ isAuto: true }).catch(handleUnexpectedError);
    }
  }, 1000);
}

function stopAttemptTimer() {
  if (state.timerIntervalId) {
    window.clearInterval(state.timerIntervalId);
    state.timerIntervalId = null;
  }
}

function updateLiveAttemptMetrics() {
  const currentQuestion = getCurrentQuestion();
  const spentSecondsElement = document.getElementById("current-question-spent-seconds");
  if (currentQuestion && spentSecondsElement) {
    spentSecondsElement.textContent = formatSpentSeconds(currentQuestion.answer_data?.spent_seconds || 0);
  }
}

function clearAutosaveHandle() {
  if (state.autosaveHandle) {
    window.clearTimeout(state.autosaveHandle);
    state.autosaveHandle = null;
  }
}

function getStoredAttemptId() {
  try {
    return window.localStorage.getItem(ACTIVE_ATTEMPT_STORAGE_KEY);
  } catch {
    return null;
  }
}

function setStoredAttemptId(attemptId) {
  window.localStorage.setItem(ACTIVE_ATTEMPT_STORAGE_KEY, attemptId);
}

function clearStoredAttemptId() {
  window.localStorage.removeItem(ACTIVE_ATTEMPT_STORAGE_KEY);
}

function storeLatestSubmittedAttempt(attempt) {
  try {
    window.localStorage.setItem(
      LATEST_RESULT_STORAGE_KEY,
      JSON.stringify({
        id: attempt.id,
        score: attempt.score,
        submitted_at: attempt.submitted_at,
      }),
    );
  } catch {
    // Ignore localStorage write failures.
  }
}

async function loadStudentResults({ showStatus = false } = {}) {
  const email = document.getElementById("student-email-input").value.trim();
  const fullName = document.getElementById("student-name-input").value.trim();
  const rollNumber = document.getElementById("student-roll-number-input").value.trim();
  if (!email && !fullName) {
    state.studentResults = [];
    renderStudentOverview();
    return;
  }
  const searchParams = new URLSearchParams();
  if (email) {
    searchParams.set("email", email);
  } else {
    searchParams.set("full_name", fullName);
    if (rollNumber) {
      searchParams.set("roll_number", rollNumber);
    }
  }
  state.studentResults = await apiRequest(`/students/results?${searchParams.toString()}`);
  renderStudentOverview();
  if (showStatus) {
    setStatus("Student results refreshed.");
  }
}

function applyPageMode() {
  if (!getIsRunnerMode()) {
    return;
  }
  document.title = "BrainGain Attempt Runner";
  const selectorsToHide = [
    ".hero",
    ".content-grid > section:nth-of-type(1)",
    ".content-grid > section:nth-of-type(2)",
    ".content-grid > section:nth-of-type(3)",
  ];
  for (const selector of selectorsToHide) {
    const element = document.querySelector(selector);
    if (element instanceof HTMLElement) {
      element.style.display = "none";
    }
  }
  const takeAnotherButton = document.getElementById("take-another-test-button");
  if (takeAnotherButton) {
    takeAnotherButton.style.display = "none";
  }
  const refreshButton = document.getElementById("refresh-tests-button");
  if (refreshButton) {
    refreshButton.style.display = "none";
  }
  const mainContent = document.querySelector(".content-grid");
  if (mainContent instanceof HTMLElement) {
    mainContent.style.display = "grid";
  }
  const runnerPanels = document.querySelectorAll(".content-grid > section:nth-of-type(4), .content-grid > section:nth-of-type(5)");
  for (const panel of runnerPanels) {
    if (panel instanceof HTMLElement) {
      panel.style.gridColumn = "span 12";
    }
  }
  const attemptId = getRequestedAttemptId();
  if (attemptId) {
    setStoredAttemptId(attemptId);
  }
  enforceAttemptProtection();
}

function getRequestedAttemptId() {
  return new URLSearchParams(window.location.search).get("attempt_id");
}

function getIsRunnerMode() {
  return new URLSearchParams(window.location.search).get("runner") === "1";
}

function openAttemptRunnerShell() {
  if (getIsRunnerMode()) {
    return window;
  }
  const features = "popup=yes,width=1280,height=900,resizable=yes,scrollbars=yes";
  const runnerWindow = window.open("about:blank", RUNNER_WINDOW_NAME, features);
  if (runnerWindow) {
    runnerWindow.document.title = "BrainGain Attempt Runner";
    runnerWindow.document.body.innerHTML = "<p style=\"font-family:sans-serif;padding:24px;\">Loading attempt runner...</p>";
  }
  return runnerWindow;
}

function openAttemptRunnerWindow(attemptId, runnerWindow = null) {
  const targetWindow = runnerWindow || state.runnerWindow || window.open("", RUNNER_WINDOW_NAME);
  const targetUrl = `/student?attempt_id=${encodeURIComponent(attemptId)}&runner=1`;
  if (targetWindow) {
    targetWindow.location.href = targetUrl;
    state.runnerWindow = targetWindow;
    if (typeof targetWindow.focus === "function") {
      targetWindow.focus();
    }
    return;
  }
  window.location.href = targetUrl;
}

function enforceAttemptProtection() {
  if (document.body.dataset.attemptProtectionBound === "true") {
    return;
  }
  const blockAction = (event) => {
    event.preventDefault();
    setStatus("Copy, paste, and context menu are disabled in the attempt runner.", true);
  };
  document.addEventListener("copy", blockAction);
  document.addEventListener("cut", blockAction);
  document.addEventListener("paste", blockAction);
  document.addEventListener("contextmenu", blockAction);
  document.addEventListener("selectstart", blockAction);
  document.addEventListener("keydown", (event) => {
    const isMetaPressed = event.ctrlKey || event.metaKey;
    const key = String(event.key || "").toLowerCase();
    if (isMetaPressed && ["a", "c", "v", "x", "p", "s", "u"].includes(key)) {
      blockAction(event);
    }
    if (event.key === "F12") {
      blockAction(event);
    }
  });
  document.body.dataset.attemptProtectionBound = "true";
}

function hydrateStudentIdentity(session) {
  if (!session) {
    return;
  }
  const nameInput = document.getElementById("student-name-input");
  const emailInput = document.getElementById("student-email-input");
  if (nameInput && !nameInput.value.trim()) {
    nameInput.value = session.display_name || "Student";
  }
  if (emailInput && !emailInput.value.trim() && session.role === "student") {
    emailInput.value = "student@braingain.local";
  }
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
    throw new Error(formatApiError(detail));
  }
  return responseData;
}

function setStatus(message, isError = false) {
  const banner = document.getElementById("student-status-banner");
  banner.textContent = message;
  banner.classList.toggle("is-error", isError);
}

function buildProjectFileUrl(filePath) {
  const relativePath = String(filePath).replace(`${projectRoot}/`, "").replace(/^\//, "");
  return `/project-files/${relativePath}`;
}

function calculateTimeLimitMinutes(questionCount) {
  return Math.max(DEFAULT_ATTEMPT_DURATION_MINUTES, questionCount * (SECONDS_PER_QUESTION / 60));
}

function buildTimerClassName(remainingSeconds) {
  if (remainingSeconds === null || remainingSeconds === undefined) {
    return "timer-pill";
  }
  if (remainingSeconds <= 0) {
    return "timer-pill is-expired";
  }
  if (remainingSeconds <= 300) {
    return "timer-pill is-warning";
  }
  return "timer-pill";
}

function formatRemainingSeconds(remainingSeconds) {
  if (remainingSeconds === null || remainingSeconds === undefined) {
    return "-";
  }
  const safeSeconds = Math.max(0, Number(remainingSeconds));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;
  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatSpentSeconds(spentSeconds) {
  const safeSeconds = Math.max(0, Number(spentSeconds || 0));
  if (safeSeconds < 60) {
    return `${safeSeconds}s spent`;
  }
  const minutes = Math.floor(safeSeconds / 60);
  const seconds = safeSeconds % 60;
  return `${minutes}m ${seconds}s spent`;
}

function formatAttemptStatus(status) {
  if (!status || status === "not_started") {
    return "Not started";
  }
  return String(status).replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatAnswerStateLabel(answerState) {
  switch (answerState) {
    case "answered":
      return "Answered";
    case "marked_for_review":
      return "Marked";
    case "answered_and_marked_for_review":
      return "Answered + marked";
    case "not_answered":
      return "Visited";
    default:
      return "Not visited";
  }
}

function formatSubmittedAnswer(question) {
  const questionFormat = question.question_format || question.format;
  const answerData = question.answer_data || {};
  if (questionFormat === "nat") {
    return answerData.numeric_value ?? "No answer";
  }
  if (questionFormat === "match") {
    return formatPairMapping(answerData.pair_mapping || {});
  }
  return (answerData.option_labels || []).join(", ") || "No answer";
}

function formatCorrectAnswer(question, questionFormat) {
  if (questionFormat === "nat") {
    const numericAnswer = question.numeric_answer || {};
    if (numericAnswer.exact_value === undefined) {
      return "-";
    }
    return `${numericAnswer.exact_value}${numericAnswer.unit ? ` ${numericAnswer.unit}` : ""}`;
  }
  if (questionFormat === "match") {
    const mapping = {};
    for (const item of question.columns?.items_a || []) {
      if (item.matches) {
        mapping[item.label] = item.matches;
      }
    }
    return formatPairMapping(mapping);
  }
  return question.options.filter((option) => option.is_correct).map((option) => option.label).join(", ") || "-";
}

function formatPairMapping(pairMapping) {
  const entries = Object.entries(pairMapping || {});
  if (!entries.length) {
    return "No answer";
  }
  return entries.map(([left, right]) => `${left}-${right}`).join(", ");
}

function formatApiError(detail) {
  if (detail === null || detail === undefined) {
    return "Request failed.";
  }
  if (typeof detail === "string") {
    return detail;
  }
  return JSON.stringify(detail, null, 2);
}

function tryParseJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function formatTimestamp(timestampText) {
  if (!timestampText) {
    return "-";
  }
  const dateValue = new Date(timestampText);
  return Number.isNaN(dateValue.getTime()) ? timestampText : dateValue.toLocaleString();
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function handleUnexpectedError(error) {
  setStatus(error?.message ?? "Unexpected frontend error.", true);
}
