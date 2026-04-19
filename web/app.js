const projectRoot = "/home/harsh-suryawanshi/projects/BrainGain";

const state = {
  admins: [],
  subjects: [],
  chaptersBySubjectId: new Map(),
  topicsByChapterId: new Map(),
  approvedFiguresByTopicId: new Map(),
  questionTreeBySubjectId: new Map(),
  testsBySubjectId: new Map(),
  selectedAdminId: "",
  selectedSubjectId: "",
  selectedChapterId: "",
  selectedTopicId: "",
  currentQuestions: [],
  selectedTestQuestionIds: new Set(),
  isCreatingTest: false,
  latestCreatedTest: null,
  editingQuestionId: "",
  unsupportedQuestionCount: 0,
};

document.addEventListener("DOMContentLoaded", () => {
  const session = requireRole("admin");
  if (!session) {
    return;
  }
  renderSessionIdentity("session-identity", "Admin");
  bindLogoutButton();
  bindEvents();
  renderAdminOverview();
  renderQuestions([]);
  renderQuestionReviewSummary([]);
  renderTestBuilder();
  renderAdminTests();
  clearQuestionForm({ keepStatus: true });
  refreshAllData().catch(handleUnexpectedError);
});

function bindEvents() {
  document.getElementById("refresh-all-button").addEventListener("click", () => {
    refreshAllData().catch(handleUnexpectedError);
  });

  document.getElementById("admin-select").addEventListener("change", () => {
    state.selectedAdminId = document.getElementById("admin-select").value || "";
    renderQuestionEditorState();
  });

  document.getElementById("subject-select").addEventListener("change", () => {
    handleSubjectChange().catch(handleUnexpectedError);
  });
  document.getElementById("create-chapter-subject-select").addEventListener("change", () => {
    document.getElementById("subject-select").value = document.getElementById("create-chapter-subject-select").value;
    handleSubjectChange().catch(handleUnexpectedError);
  });

  document.getElementById("chapter-select").addEventListener("change", () => {
    handleChapterChange().catch(handleUnexpectedError);
  });
  document.getElementById("create-topic-chapter-select").addEventListener("change", () => {
    document.getElementById("chapter-select").value = document.getElementById("create-topic-chapter-select").value;
    handleChapterChange().catch(handleUnexpectedError);
  });

  document.getElementById("topic-select").addEventListener("change", () => {
    handleTopicChange().catch(handleUnexpectedError);
  });

  document.getElementById("create-subject-form").addEventListener("submit", (event) => {
    event.preventDefault();
    createSubject().catch(handleUnexpectedError);
  });
  document.getElementById("create-chapter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    createChapter().catch(handleUnexpectedError);
  });
  document.getElementById("create-topic-form").addEventListener("submit", (event) => {
    event.preventDefault();
    createTopic().catch(handleUnexpectedError);
  });
  document.getElementById("edit-subject-button").addEventListener("click", () => {
    editSelectedSubject().catch(handleUnexpectedError);
  });
  document.getElementById("delete-subject-button").addEventListener("click", () => {
    deleteSelectedSubject().catch(handleUnexpectedError);
  });
  document.getElementById("edit-chapter-button").addEventListener("click", () => {
    editSelectedChapter().catch(handleUnexpectedError);
  });
  document.getElementById("delete-chapter-button").addEventListener("click", () => {
    deleteSelectedChapter().catch(handleUnexpectedError);
  });
  document.getElementById("edit-topic-button").addEventListener("click", () => {
    editSelectedTopic().catch(handleUnexpectedError);
  });
  document.getElementById("delete-topic-button").addEventListener("click", () => {
    deleteSelectedTopic().catch(handleUnexpectedError);
  });

  document.getElementById("question-format-select").addEventListener("change", syncCorrectOptionBehavior);
  document.getElementById("question-image-select").addEventListener("change", renderQuestionImagePreview);
  document.getElementById("upload-question-image-button").addEventListener("click", () => {
    uploadQuestionImage().catch(handleUnexpectedError);
  });
  document.getElementById("clear-question-image-button").addEventListener("click", () => {
    document.getElementById("question-image-select").value = "";
    document.getElementById("question-image-file-input").value = "";
    renderQuestionImagePreview();
    setStatus("Question image cleared from the editor.");
  });
  for (const optionId of ["option-a-correct", "option-b-correct", "option-c-correct", "option-d-correct"]) {
    document.getElementById(optionId).addEventListener("change", () => {
      if (document.getElementById("question-format-select").value !== "mcq") {
        return;
      }
      if (!document.getElementById(optionId).checked) {
        return;
      }
      for (const candidateId of ["option-a-correct", "option-b-correct", "option-c-correct", "option-d-correct"]) {
        if (candidateId !== optionId) {
          document.getElementById(candidateId).checked = false;
        }
      }
    });
  }

  document.getElementById("question-form").addEventListener("submit", (event) => {
    event.preventDefault();
    saveQuestion().catch(handleUnexpectedError);
  });
  document.getElementById("reset-question-button").addEventListener("click", () => {
    clearQuestionForm();
  });
  document.getElementById("delete-question-button").addEventListener("click", () => {
    deleteSelectedQuestion().catch(handleUnexpectedError);
  });
  document.getElementById("load-questions-button").addEventListener("click", () => {
    loadQuestionsForSelectedTopic().catch(handleUnexpectedError);
  });
  document.getElementById("select-all-test-questions-button").addEventListener("click", () => {
    selectAllTestQuestionsInScope();
  });
  document.getElementById("clear-selected-test-questions-button").addEventListener("click", () => {
    clearSelectedTestQuestions();
  });
  document.getElementById("generate-test-button").addEventListener("click", () => {
    generateSelectedTest().catch(handleUnexpectedError);
  });
}

async function refreshAllData() {
  setStatus("Refreshing admin workspace.");
  await loadAdmins();
  await loadSubjects();
  await loadQuestionsForSelectedTopic();
  await loadAdminTestsForSelectedSubject();
  renderAdminOverview();
  renderQuestionEditorState();
  renderAdminTests();
  setStatus("Admin workspace refreshed.");
}

async function loadAdmins() {
  state.admins = await apiRequest("/admins");
  populateSelect(document.getElementById("admin-select"), state.admins, {
    valueKey: "id",
    labelBuilder: formatAdminLabel,
    selectedValue: state.selectedAdminId,
    placeholder: "Choose admin",
  });
  state.selectedAdminId = document.getElementById("admin-select").value || "";
}

async function loadSubjects() {
  state.subjects = await apiRequest("/subjects");
  populateSelect(document.getElementById("subject-select"), state.subjects, {
    valueKey: "id",
    labelBuilder: formatSubjectLabel,
    selectedValue: state.selectedSubjectId,
    placeholder: "Choose subject",
  });
  populateSelect(document.getElementById("create-chapter-subject-select"), state.subjects, {
    valueKey: "id",
    labelBuilder: formatSubjectLabel,
    selectedValue: state.selectedSubjectId,
    placeholder: "Choose subject",
  });
  state.selectedSubjectId = document.getElementById("subject-select").value || "";
  if (document.getElementById("create-chapter-subject-select").value !== state.selectedSubjectId) {
    document.getElementById("create-chapter-subject-select").value = state.selectedSubjectId;
  }
  await handleSubjectChange({ keepStatus: true });
}

async function handleSubjectChange({ keepStatus = false } = {}) {
  state.selectedSubjectId = document.getElementById("subject-select").value || "";
  if (document.getElementById("create-chapter-subject-select").value !== state.selectedSubjectId) {
    document.getElementById("create-chapter-subject-select").value = state.selectedSubjectId;
  }

  if (!state.selectedSubjectId) {
    clearSelect(document.getElementById("chapter-select"), "Choose chapter");
    clearSelect(document.getElementById("create-topic-chapter-select"), "Choose chapter");
    clearSelect(document.getElementById("topic-select"), "Choose topic");
    state.selectedChapterId = "";
    state.selectedTopicId = "";
    state.currentQuestions = [];
    state.selectedTestQuestionIds = new Set();
    state.editingQuestionId = "";
    state.unsupportedQuestionCount = 0;
    state.approvedFiguresByTopicId.clear();
    renderQuestions([]);
    renderQuestionReviewSummary([]);
    renderTestBuilder();
    renderAdminTests();
    clearQuestionForm({ keepStatus: true });
    renderAdminOverview();
    renderQuestionEditorState();
    if (!keepStatus) {
      setStatus("Select a subject to continue.");
    }
    return;
  }

  const chapters = await apiRequest(`/subjects/${state.selectedSubjectId}/chapters`);
  state.chaptersBySubjectId.set(state.selectedSubjectId, chapters);
  await loadSubjectQuestionTree(state.selectedSubjectId);
  await loadAdminTestsForSelectedSubject();
  populateSelect(document.getElementById("chapter-select"), chapters, {
    valueKey: "id",
    labelBuilder: formatChapterLabel,
    selectedValue: state.selectedChapterId,
    placeholder: "Choose chapter",
  });
  populateSelect(document.getElementById("create-topic-chapter-select"), chapters, {
    valueKey: "id",
    labelBuilder: formatChapterLabel,
    selectedValue: state.selectedChapterId,
    placeholder: "Choose chapter",
  });
  state.selectedChapterId = document.getElementById("chapter-select").value || "";
  if (document.getElementById("create-topic-chapter-select").value !== state.selectedChapterId) {
    document.getElementById("create-topic-chapter-select").value = state.selectedChapterId;
  }
  await handleChapterChange({ keepStatus: true });
  if (!keepStatus) {
    setStatus("Subject loaded.");
  }
}

async function handleChapterChange({ keepStatus = false } = {}) {
  state.selectedChapterId = document.getElementById("chapter-select").value || "";
  if (document.getElementById("create-topic-chapter-select").value !== state.selectedChapterId) {
    document.getElementById("create-topic-chapter-select").value = state.selectedChapterId;
  }

  if (!state.selectedChapterId) {
    clearSelect(document.getElementById("topic-select"), "Choose topic");
    state.topicsByChapterId.set("", []);
    state.selectedTopicId = "";
    state.currentQuestions = [];
    state.editingQuestionId = "";
    state.unsupportedQuestionCount = 0;
    state.approvedFiguresByTopicId.clear();
    renderQuestions([]);
    renderQuestionReviewSummary([]);
    renderTestBuilder();
    renderAdminTests();
    clearQuestionForm({ keepStatus: true });
    renderAdminOverview();
    renderQuestionEditorState();
    if (!keepStatus) {
      setStatus("Select a chapter to continue.");
    }
    return;
  }

  const topics = await apiRequest(`/chapters/${state.selectedChapterId}/topics`);
  state.topicsByChapterId.set(state.selectedChapterId, topics);
  populateSelect(document.getElementById("topic-select"), topics, {
    valueKey: "id",
    labelBuilder: (topic) => topic.name,
    selectedValue: state.selectedTopicId,
    placeholder: "Choose topic",
  });
  state.selectedTopicId = document.getElementById("topic-select").value || "";
  await handleTopicChange({ keepStatus: true });
  renderTestBuilder();
  renderAdminTests();
  if (!keepStatus) {
    setStatus("Chapter loaded.");
  }
}

async function handleTopicChange({ keepStatus = false } = {}) {
  state.selectedTopicId = document.getElementById("topic-select").value || "";
  await loadApprovedFiguresForSelectedTopic();
  await loadQuestionsForSelectedTopic({ keepStatus: true });
  renderAdminOverview();
  renderQuestionEditorState();
  renderTestBuilder();
  renderAdminTests();
  if (!keepStatus) {
    setStatus(state.selectedTopicId ? "Topic loaded." : "Select a topic to start authoring questions.");
  }
}

async function loadSubjectQuestionTree(subjectId) {
  if (!subjectId) {
    return;
  }
  const tree = await apiRequest(`/subjects/${subjectId}/question-tree`);
  state.questionTreeBySubjectId.set(subjectId, tree);
  pruneSelectedTestQuestions();
}

async function loadAdminTestsForSelectedSubject() {
  if (!state.selectedSubjectId) {
    return;
  }
  const tests = await apiRequest(`/admin/tests?subject_id=${encodeURIComponent(state.selectedSubjectId)}`);
  state.testsBySubjectId.set(state.selectedSubjectId, tests);
}

async function createSubject() {
  const payload = {
    name: document.getElementById("subject-name-input").value.trim(),
    grade: Number(document.getElementById("subject-grade-input").value),
    board: document.getElementById("subject-board-input").value.trim(),
  };
  const subject = await apiRequest("/subjects", "POST", payload);
  document.getElementById("create-subject-form").reset();
  state.selectedSubjectId = subject.id;
  await loadSubjects();
  setStatus(`Created subject: ${subject.name}.`);
}

async function createChapter() {
  const subjectId = document.getElementById("create-chapter-subject-select").value;
  if (!subjectId) {
    throw new Error("Choose a subject before creating a chapter.");
  }
  const payload = {
    subject_id: subjectId,
    chapter_number: Number(document.getElementById("chapter-number-input").value),
    name: document.getElementById("chapter-name-input").value.trim(),
  };
  const chapter = await apiRequest("/chapters", "POST", payload);
  document.getElementById("create-chapter-form").reset();
  state.selectedSubjectId = subjectId;
  state.selectedChapterId = chapter.id;
  await loadSubjects();
  setStatus(`Created chapter: ${formatChapterLabel(chapter)}.`);
}

async function createTopic() {
  const chapterId = document.getElementById("create-topic-chapter-select").value;
  if (!chapterId) {
    throw new Error("Choose a chapter before creating a topic.");
  }
  const payload = {
    chapter_id: chapterId,
    name: document.getElementById("topic-name-input").value.trim(),
    display_order: Number(document.getElementById("topic-order-input").value),
  };
  const topic = await apiRequest("/topics", "POST", payload);
  document.getElementById("create-topic-form").reset();
  state.selectedChapterId = chapterId;
  state.selectedTopicId = topic.id;
  document.getElementById("chapter-select").value = chapterId;
  await handleChapterChange({ keepStatus: true });
  document.getElementById("topic-select").value = topic.id;
  await handleTopicChange({ keepStatus: true });
  setStatus(`Created topic: ${topic.name}.`);
}

async function editSelectedSubject() {
  const subject = state.subjects.find((item) => item.id === state.selectedSubjectId);
  if (!subject) {
    throw new Error("Choose a subject first.");
  }
  const name = window.prompt("Subject name", subject.name || "");
  if (name === null) {
    return;
  }
  const gradeText = window.prompt("Grade", String(subject.grade ?? ""));
  if (gradeText === null) {
    return;
  }
  const board = window.prompt("Board", subject.board || "");
  if (board === null) {
    return;
  }
  await apiRequest(`/subjects/${subject.id}`, "PATCH", {
    name: name.trim(),
    grade: Number(gradeText),
    board: board.trim(),
  });
  await loadSubjects();
  setStatus("Subject updated.");
}

async function deleteSelectedSubject() {
  const subject = state.subjects.find((item) => item.id === state.selectedSubjectId);
  if (!subject) {
    throw new Error("Choose a subject first.");
  }
  if (!window.confirm(`Delete subject "${subject.name}" and all nested chapters, topics, concepts, and questions?`)) {
    return;
  }
  await apiRequest(`/subjects/${subject.id}`, "DELETE");
  state.selectedSubjectId = "";
  state.selectedChapterId = "";
  state.selectedTopicId = "";
  await loadSubjects();
  setStatus("Subject deleted.");
}

async function editSelectedChapter() {
  const chapters = state.chaptersBySubjectId.get(state.selectedSubjectId) || [];
  const chapter = chapters.find((item) => item.id === state.selectedChapterId);
  if (!chapter) {
    throw new Error("Choose a chapter first.");
  }
  const chapterNumberText = window.prompt("Chapter number", String(chapter.chapter_number ?? ""));
  if (chapterNumberText === null) {
    return;
  }
  const name = window.prompt("Chapter name", chapter.name || "");
  if (name === null) {
    return;
  }
  await apiRequest(`/chapters/${chapter.id}`, "PATCH", {
    chapter_number: Number(chapterNumberText),
    name: name.trim(),
  });
  await handleSubjectChange({ keepStatus: true });
  setStatus("Chapter updated.");
}

async function deleteSelectedChapter() {
  const chapters = state.chaptersBySubjectId.get(state.selectedSubjectId) || [];
  const chapter = chapters.find((item) => item.id === state.selectedChapterId);
  if (!chapter) {
    throw new Error("Choose a chapter first.");
  }
  if (!window.confirm(`Delete chapter "${chapter.name}" and all nested topics, concepts, and questions?`)) {
    return;
  }
  await apiRequest(`/chapters/${chapter.id}`, "DELETE");
  state.selectedChapterId = "";
  state.selectedTopicId = "";
  await handleSubjectChange({ keepStatus: true });
  setStatus("Chapter deleted.");
}

async function editSelectedTopic() {
  const topics = state.topicsByChapterId.get(state.selectedChapterId) || [];
  const topic = topics.find((item) => item.id === state.selectedTopicId);
  if (!topic) {
    throw new Error("Choose a topic first.");
  }
  const name = window.prompt("Topic name", topic.name || "");
  if (name === null) {
    return;
  }
  const displayOrderText = window.prompt("Display order", String(topic.display_order ?? ""));
  if (displayOrderText === null) {
    return;
  }
  await apiRequest(`/topics/${topic.id}`, "PATCH", {
    name: name.trim(),
    display_order: Number(displayOrderText),
  });
  await handleChapterChange({ keepStatus: true });
  setStatus("Topic updated.");
}

async function deleteSelectedTopic() {
  const topics = state.topicsByChapterId.get(state.selectedChapterId) || [];
  const topic = topics.find((item) => item.id === state.selectedTopicId);
  if (!topic) {
    throw new Error("Choose a topic first.");
  }
  if (!window.confirm(`Delete topic "${topic.name}" and all nested concepts and questions?`)) {
    return;
  }
  await apiRequest(`/topics/${topic.id}`, "DELETE");
  state.selectedTopicId = "";
  await handleChapterChange({ keepStatus: true });
  setStatus("Topic deleted.");
}

async function loadApprovedFiguresForSelectedTopic() {
  if (!state.selectedTopicId) {
    clearQuestionImageChoices();
    return;
  }
  const figures = await apiRequest(`/topics/${state.selectedTopicId}/approved-figures`);
  state.approvedFiguresByTopicId.set(state.selectedTopicId, figures);
  populateQuestionImageSelect(document.getElementById("question-image-select").value || "");
}

async function uploadQuestionImage() {
  if (!state.selectedTopicId) {
    throw new Error("Choose a topic before uploading a question image.");
  }
  if (!state.selectedAdminId) {
    throw new Error("Choose an admin before uploading a question image.");
  }
  const fileInput = document.getElementById("question-image-file-input");
  const imageFile = fileInput.files?.[0];
  if (!imageFile) {
    throw new Error("Choose an image file first.");
  }
  const formData = new FormData();
  formData.append("uploaded_by_admin_id", state.selectedAdminId);
  formData.append("image_file", imageFile);
  const uploadedImage = await apiRequest(`/topics/${state.selectedTopicId}/question-images`, "POST", formData, true);
  await loadApprovedFiguresForSelectedTopic();
  document.getElementById("question-image-select").value = uploadedImage.id;
  fileInput.value = "";
  renderQuestionImagePreview();
  setStatus(`Uploaded image: ${uploadedImage.name}.`);
}

async function loadQuestionsForSelectedTopic({ keepStatus = false, preserveQuestionId = "" } = {}) {
  if (!state.selectedTopicId) {
    state.currentQuestions = [];
    state.editingQuestionId = "";
    state.unsupportedQuestionCount = 0;
    clearQuestionImageChoices();
    renderQuestions([]);
    renderQuestionReviewSummary([]);
    renderTestBuilder();
    clearQuestionForm({ keepStatus: true });
    renderAdminOverview();
    renderQuestionEditorState();
    if (!keepStatus) {
      setStatus("Select a topic to load questions.");
    }
    return;
  }

  const questions = await apiRequest(`/topics/${state.selectedTopicId}/questions`);
  state.unsupportedQuestionCount = questions.filter((question) => !["mcq", "msq"].includes(question.question_format)).length;
  state.currentQuestions = questions.filter((question) => ["mcq", "msq"].includes(question.question_format));
  const candidateQuestionId = preserveQuestionId || state.editingQuestionId;
  state.editingQuestionId = state.currentQuestions.some((question) => question.id === candidateQuestionId) ? candidateQuestionId : "";
  renderQuestions(state.currentQuestions);
  renderQuestionReviewSummary(state.currentQuestions);
  pruneSelectedTestQuestions();
  renderTestBuilder();

  if (state.editingQuestionId) {
    const selectedQuestion = state.currentQuestions.find((question) => question.id === state.editingQuestionId);
    if (selectedQuestion) {
      populateQuestionForm(selectedQuestion);
    }
  } else {
    clearQuestionForm({ keepStatus: true });
  }

  renderAdminOverview();
  renderQuestionEditorState();
  if (!keepStatus) {
      setStatus(`Loaded ${state.currentQuestions.length} editable question(s) for the selected topic.`);
    }
}

function renderTestBuilder() {
  renderTestBuilderState();
  renderTestBuilderSummary();
  renderTestBuilderQuestionList();
}

function renderAdminTests() {
  renderAdminTestsSummary();
  renderAdminTestsList();
}

function renderTestBuilderState() {
  const banner = document.getElementById("test-builder-state");
  const generateButton = document.getElementById("generate-test-button");
  const availableQuestions = getAvailableTestQuestionsInScope();
  if (!state.selectedSubjectId) {
    banner.textContent = "Choose a subject to load active published questions.";
  } else if (!availableQuestions.length) {
    banner.textContent = "No active published questions are available in the current scope.";
  } else {
    banner.textContent = `Creating a test for ${buildScopeLabel()}.`;
  }
  generateButton.disabled = state.isCreatingTest || !state.selectedAdminId || !state.selectedSubjectId || state.selectedTestQuestionIds.size === 0;
  generateButton.textContent = state.isCreatingTest ? "Creating..." : "Create Test";
}

function renderTestBuilderSummary() {
  const container = document.getElementById("test-builder-summary");
  const availableQuestions = getAvailableTestQuestionsInScope();
  if (!state.selectedSubjectId) {
    container.innerHTML = "";
    return;
  }
  const selectedQuestions = availableQuestions.filter((question) => state.selectedTestQuestionIds.has(question.id));
  const hardSelectedCount = selectedQuestions.filter((question) => question.difficulty === "hard").length;
  const configuredTimeLimit = Number(document.getElementById("test-time-limit-input")?.value || 30);
  container.innerHTML = `
    <div class="summary-grid">
      <article class="summary-card">
        <span class="helper-text">Available In Scope</span>
        <strong>${escapeHtml(availableQuestions.length)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Selected</span>
        <strong>${escapeHtml(selectedQuestions.length)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Hard Selected</span>
        <strong>${escapeHtml(hardSelectedCount)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Scope</span>
        <strong>${escapeHtml(buildScopeLabel())}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Time Limit</span>
        <strong>${escapeHtml(configuredTimeLimit)} min</strong>
      </article>
    </div>
    ${state.latestCreatedTest ? `
      <article class="list-card">
        <strong>Latest Created Test</strong>
        <div>${escapeHtml(state.latestCreatedTest.title)}</div>
        <div class="helper-text">Questions: ${escapeHtml(state.latestCreatedTest.question_count)} | Status: ${escapeHtml(state.latestCreatedTest.status || "published")}</div>
      </article>
    ` : ""}
  `;
}

function renderTestBuilderQuestionList() {
  const container = document.getElementById("test-builder-question-list");
  const availableQuestions = getAvailableTestQuestionsInScope();
  if (!state.selectedSubjectId) {
    container.innerHTML = "<div class=\"list-card\">Select a subject to start building a test.</div>";
    return;
  }
  if (!availableQuestions.length) {
    container.innerHTML = "<div class=\"list-card\">No active published questions are available in the selected scope.</div>";
    return;
  }
  container.innerHTML = "";
  for (const question of availableQuestions) {
    const card = document.createElement("label");
    const isChecked = state.selectedTestQuestionIds.has(question.id);
    card.className = `list-card test-select-card${isChecked ? " is-selected" : ""}`;
    card.innerHTML = `
      <div class="checkbox-row">
        <input type="checkbox" data-test-question-id="${escapeHtml(question.id)}" ${isChecked ? "checked" : ""}>
        <span><strong>${escapeHtml(question.text || "(missing text)")}</strong></span>
      </div>
      <div>${escapeHtml(String(question.question_format || "").toUpperCase())} | ${escapeHtml(question.difficulty)} | ${escapeHtml(question.type)}</div>
      <div>Status: ${escapeHtml(question.status)} | ${escapeHtml(question.chapter_name)} | ${escapeHtml(question.topic_name)} | ${escapeHtml(question.concept_name)}</div>
    `;
    const checkbox = card.querySelector("input[type='checkbox']");
    checkbox.addEventListener("change", () => {
      toggleTestQuestionSelection(question.id, checkbox.checked);
    });
    container.appendChild(card);
  }
}

function getAvailableTestQuestionsInScope() {
  const tree = state.questionTreeBySubjectId.get(state.selectedSubjectId);
  if (!tree?.chapters?.length) {
    return [];
  }
  const questions = [];
  for (const chapter of tree.chapters) {
    if (state.selectedChapterId && chapter.id !== state.selectedChapterId) {
      continue;
    }
    for (const topic of chapter.topics || []) {
      if (state.selectedTopicId && topic.id !== state.selectedTopicId) {
        continue;
      }
      for (const concept of topic.concepts || []) {
        for (const question of concept.questions || []) {
          if (!question.can_use_in_test) {
            continue;
          }
          questions.push({
            ...question,
            chapter_id: chapter.id,
            chapter_name: `Chapter ${chapter.chapter_number}: ${chapter.name}`,
            topic_id: topic.id,
            topic_name: topic.name,
            concept_id: concept.id,
            concept_name: concept.name,
          });
        }
      }
    }
  }
  return questions;
}

function toggleTestQuestionSelection(questionId, isSelected) {
  if (isSelected) {
    state.selectedTestQuestionIds.add(questionId);
  } else {
    state.selectedTestQuestionIds.delete(questionId);
  }
  renderTestBuilder();
}

function selectAllTestQuestionsInScope() {
  for (const question of getAvailableTestQuestionsInScope()) {
    state.selectedTestQuestionIds.add(question.id);
  }
  renderTestBuilder();
  setStatus("Selected all active published questions in scope.");
}

function clearSelectedTestQuestions() {
  const allowedIds = new Set(getAvailableTestQuestionsInScope().map((question) => question.id));
  state.selectedTestQuestionIds = new Set([...state.selectedTestQuestionIds].filter((questionId) => !allowedIds.has(questionId)));
  renderTestBuilder();
  setStatus("Cleared test selection for the current scope.");
}

function pruneSelectedTestQuestions() {
  const allowedIds = new Set(getAvailableTestQuestionsInScope().map((question) => question.id));
  state.selectedTestQuestionIds = new Set([...state.selectedTestQuestionIds].filter((questionId) => allowedIds.has(questionId)));
}

async function generateSelectedTest() {
  if (state.isCreatingTest) {
    return;
  }
  if (!state.selectedAdminId) {
    throw new Error("Choose an admin first.");
  }
  if (!state.selectedSubjectId) {
    throw new Error("Choose a subject first.");
  }
  const selectedQuestionIds = getAvailableTestQuestionsInScope()
    .filter((question) => state.selectedTestQuestionIds.has(question.id))
    .map((question) => question.id);
  if (!selectedQuestionIds.length) {
    throw new Error("Select at least one active published question.");
  }
  const titleInput = document.getElementById("test-title-input");
  const timeLimitInput = document.getElementById("test-time-limit-input");
  const testTitle = titleInput.value.trim() || `Practice Test - ${buildScopeLabel()}`;
  const timeLimitMinutes = Number(timeLimitInput.value || 30);
  if (!Number.isFinite(timeLimitMinutes) || timeLimitMinutes < 1 || timeLimitMinutes > 300) {
    throw new Error("Time limit must be between 1 and 300 minutes.");
  }
  state.isCreatingTest = true;
  renderTestBuilder();
  try {
    const createdTest = await apiRequest("/tests/generate", "POST", {
      created_by_admin_id: state.selectedAdminId,
      title: testTitle,
      subject_id: state.selectedSubjectId,
      chapter_id: state.selectedChapterId || null,
      topic_id: state.selectedTopicId || null,
      selected_question_item_ids: selectedQuestionIds,
      question_count: selectedQuestionIds.length,
      hard_question_count: null,
      time_limit_minutes: timeLimitMinutes,
      is_custom_practice_template: false,
    });
    state.latestCreatedTest = {
      id: createdTest.id,
      title: createdTest.title,
      question_count: createdTest.questions.length,
      time_limit_minutes: createdTest.time_limit_minutes,
      status: createdTest.status || "published",
    };
    await loadAdminTestsForSelectedSubject();
    renderAdminTests();
    titleInput.value = createdTest.title || testTitle;
    setStatus(`Created published test: ${createdTest.title} with ${createdTest.questions.length} question(s) and ${createdTest.time_limit_minutes} minutes.`);
  } finally {
    state.isCreatingTest = false;
    renderTestBuilder();
  }
}

function renderAdminTestsSummary() {
  const container = document.getElementById("admin-tests-summary");
  if (!state.selectedSubjectId) {
    container.innerHTML = "<div class=\"list-card\">Choose a subject to manage tests.</div>";
    return;
  }
  const tests = state.testsBySubjectId.get(state.selectedSubjectId) || [];
  const publishedCount = tests.filter((test) => test.status === "published").length;
  const disabledCount = tests.filter((test) => test.status === "disabled").length;
  container.innerHTML = `
    <div class="summary-grid">
      <article class="summary-card">
        <span class="helper-text">Total Tests</span>
        <strong>${escapeHtml(tests.length)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Active</span>
        <strong>${escapeHtml(publishedCount)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Disabled</span>
        <strong>${escapeHtml(disabledCount)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Subject Scope</span>
        <strong>${escapeHtml(buildScopeLabel())}</strong>
      </article>
    </div>
  `;
}

function renderAdminTestsList() {
  const container = document.getElementById("admin-tests-list");
  if (!state.selectedSubjectId) {
    container.innerHTML = "";
    return;
  }
  const tests = state.testsBySubjectId.get(state.selectedSubjectId) || [];
  if (!tests.length) {
    container.innerHTML = "<div class=\"list-card\">No tests exist yet for this subject.</div>";
    return;
  }
  container.innerHTML = "";
  for (const test of tests) {
    const card = document.createElement("article");
    const nextStatus = test.status === "published" ? "disabled" : "published";
    const toggleLabel = test.status === "published" ? "Turn Off" : "Turn On";
    card.className = "list-card";
    card.innerHTML = `
      <strong>${escapeHtml(test.title)}</strong>
      <div>Status: ${escapeHtml(test.status)} | Time limit: ${escapeHtml(test.time_limit_minutes)} min</div>
      <div>Questions: ${escapeHtml(test.question_count)} | Attempts: ${escapeHtml(test.attempt_count || 0)}</div>
      <div class="helper-text">${escapeHtml(test.subject_name)} | Grade ${escapeHtml(test.subject_grade)} | ${escapeHtml(test.subject_board)}</div>
      <div class="button-row">
        <button class="secondary-button" type="button" data-test-toggle-id="${escapeHtml(test.id)}">${escapeHtml(toggleLabel)}</button>
        <button class="destructive-button" type="button" data-test-delete-id="${escapeHtml(test.id)}">Delete Test</button>
      </div>
    `;
    card.querySelector("[data-test-toggle-id]").addEventListener("click", () => {
      toggleTestStatus(test.id, nextStatus).catch(handleUnexpectedError);
    });
    card.querySelector("[data-test-delete-id]").addEventListener("click", () => {
      deleteManagedTest(test.id).catch(handleUnexpectedError);
    });
    container.appendChild(card);
  }
}

async function toggleTestStatus(testId, status) {
  if (!state.selectedAdminId) {
    throw new Error("Choose an admin first.");
  }
  await apiRequest(`/tests/${testId}/status`, "PATCH", {
    updated_by_admin_id: state.selectedAdminId,
    status,
  });
  await loadAdminTestsForSelectedSubject();
  renderAdminTests();
  setStatus(`Test status updated to ${status}.`);
}

async function deleteManagedTest(testId) {
  if (!state.selectedAdminId) {
    throw new Error("Choose an admin first.");
  }
  await apiRequest(`/tests/${testId}?deleted_by_admin_id=${encodeURIComponent(state.selectedAdminId)}`, "DELETE");
  await loadAdminTestsForSelectedSubject();
  renderAdminTests();
  setStatus("Test deleted.");
}

function renderQuestions(questions) {
  const container = document.getElementById("questions-list");
  if (!questions.length) {
    container.innerHTML = "<div class=\"list-card\">No questions stored for the selected topic yet.</div>";
    return;
  }

  container.innerHTML = "";
  for (const question of questions) {
    const card = document.createElement("article");
    const isSelected = question.id === state.editingQuestionId;
    const correctLabels = (question.options || []).filter((option) => option.is_correct).map((option) => option.label).join(", ");
    card.className = `list-card is-selectable${isSelected ? " is-selected" : ""}`;
    card.innerHTML = `
      <strong>${escapeHtml(question.text || "(missing text)")}</strong>
      <div>${escapeHtml(String(question.question_format || "").toUpperCase())} | ${escapeHtml(question.difficulty)} | ${escapeHtml(question.type)}</div>
      <div>Status: ${escapeHtml(question.status)} | Correct: ${escapeHtml(correctLabels || "-")}</div>
      <div class="helper-text">Version ${escapeHtml(question.version ?? "-")} | Image: ${escapeHtml(question.figures?.length ? "Attached" : "None")}</div>
    `;
    card.addEventListener("click", () => {
      state.editingQuestionId = question.id;
      populateQuestionForm(question);
      renderQuestions(state.currentQuestions);
      renderQuestionEditorState();
      setStatus("Loaded question into the editor.");
    });
    container.appendChild(card);
  }
}

function renderQuestionReviewSummary(questions) {
  const container = document.getElementById("question-review-summary");
  if (!questions.length) {
    container.innerHTML = "";
    return;
  }
  const mcqCount = questions.filter((question) => question.question_format === "mcq").length;
  const msqCount = questions.filter((question) => question.question_format === "msq").length;
  container.innerHTML = `
    <div class="summary-grid">
      <article class="summary-card">
        <span class="helper-text">Total Questions</span>
        <strong>${escapeHtml(questions.length)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">MCQ</span>
        <strong>${escapeHtml(mcqCount)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">MSQ</span>
        <strong>${escapeHtml(msqCount)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Selected For Edit</span>
        <strong>${escapeHtml(state.editingQuestionId ? "Yes" : "No")}</strong>
      </article>
    </div>
    ${state.unsupportedQuestionCount ? `
      <article class="list-card">
        <strong>Hidden From This Editor</strong>
        <div>${escapeHtml(state.unsupportedQuestionCount)} non-MCQ/MSQ question(s) are hidden to keep this admin screen simple.</div>
      </article>
    ` : ""}
  `;
}

async function saveQuestion() {
  if (!state.selectedAdminId) {
    throw new Error("Choose an admin first.");
  }
  if (!state.selectedTopicId) {
    throw new Error("Choose a topic before creating a question.");
  }

  const questionFormat = document.getElementById("question-format-select").value;
  const options = buildQuestionOptions();
  validateQuestionOptions(questionFormat, options);

  const basePayload = {
    text: document.getElementById("question-text-input").value.trim(),
    question_format: questionFormat,
    difficulty: document.getElementById("question-difficulty-select").value,
    type: document.getElementById("question-type-select").value,
    status: document.getElementById("question-status-select").value,
    minimum_selection_count: 1,
    maximum_selection_count: questionFormat === "mcq" ? 1 : 4,
    options,
    figure_ids: getSelectedImageId() ? [getSelectedImageId()] : [],
  };

  let savedQuestion;
  if (state.editingQuestionId) {
    savedQuestion = await apiRequest(`/questions/${state.editingQuestionId}`, "PATCH", {
      ...basePayload,
      last_edited_by_admin_id: state.selectedAdminId,
    });
    setStatus("Question updated.");
  } else {
    savedQuestion = await apiRequest("/questions", "POST", {
      ...basePayload,
      topic_id: state.selectedTopicId,
      created_by_admin_id: state.selectedAdminId,
    });
    setStatus("Question created.");
  }

  state.editingQuestionId = savedQuestion.id;
  await loadQuestionsForSelectedTopic({ keepStatus: true, preserveQuestionId: savedQuestion.id });
  renderQuestionEditorState();
}

async function deleteSelectedQuestion() {
  if (!state.editingQuestionId) {
    throw new Error("Select a question from the review list first.");
  }
  if (!state.selectedAdminId) {
    throw new Error("Choose an admin first.");
  }
  await apiRequest(`/questions/${state.editingQuestionId}?deleted_by_admin_id=${encodeURIComponent(state.selectedAdminId)}`, "DELETE");
  state.editingQuestionId = "";
  clearQuestionForm({ keepStatus: true });
  await loadQuestionsForSelectedTopic({ keepStatus: true });
  renderQuestionEditorState();
  setStatus("Question deleted.");
}

function buildQuestionOptions() {
  return ["A", "B", "C", "D"].map((label) => {
    const normalizedLabel = label.toLowerCase();
    return {
      label,
      text: document.getElementById(`option-${normalizedLabel}-text`).value.trim(),
      is_correct: document.getElementById(`option-${normalizedLabel}-correct`).checked,
    };
  });
}

function validateQuestionOptions(questionFormat, options) {
  const missingOption = options.find((option) => !option.text);
  if (missingOption) {
    throw new Error("Fill all four options before saving the question.");
  }
  const correctCount = options.filter((option) => option.is_correct).length;
  if (questionFormat === "mcq" && correctCount !== 1) {
    throw new Error("MCQ requires exactly one correct option.");
  }
  if (questionFormat === "msq" && correctCount < 2) {
    throw new Error("MSQ requires at least two correct options.");
  }
}

function populateQuestionForm(question) {
  document.getElementById("editing-question-id").value = question.id;
  document.getElementById("question-text-input").value = question.text || "";
  document.getElementById("question-format-select").value = question.question_format || "mcq";
  document.getElementById("question-difficulty-select").value = question.difficulty || "easy";
  document.getElementById("question-type-select").value = question.type || "definition";
  document.getElementById("question-status-select").value = question.status || "active";

  const optionByLabel = new Map((question.options || []).map((option) => [option.label, option]));
  for (const label of ["A", "B", "C", "D"]) {
    const normalizedLabel = label.toLowerCase();
    const option = optionByLabel.get(label);
    document.getElementById(`option-${normalizedLabel}-text`).value = option?.text || "";
    document.getElementById(`option-${normalizedLabel}-correct`).checked = Boolean(option?.is_correct);
  }

  populateQuestionImageSelect(question.figures?.[0]?.id || "");
  syncCorrectOptionBehavior();
  renderQuestionImagePreview();
  renderQuestionEditorState();
}

function clearQuestionForm({ keepStatus = false } = {}) {
  document.getElementById("question-form").reset();
  document.getElementById("editing-question-id").value = "";
  document.getElementById("question-format-select").value = "mcq";
  document.getElementById("question-difficulty-select").value = "easy";
  document.getElementById("question-type-select").value = "definition";
  document.getElementById("question-status-select").value = "active";
  document.getElementById("question-image-file-input").value = "";
  state.editingQuestionId = "";
  populateQuestionImageSelect("");
  syncCorrectOptionBehavior();
  renderQuestionImagePreview();
  renderQuestions(state.currentQuestions);
  renderQuestionEditorState();
  if (!keepStatus) {
    setStatus("Question form cleared.");
  }
}

function syncCorrectOptionBehavior() {
  if (document.getElementById("question-format-select").value !== "mcq") {
    return;
  }
  const checkedIds = ["option-a-correct", "option-b-correct", "option-c-correct", "option-d-correct"].filter((checkboxId) => {
    return document.getElementById(checkboxId).checked;
  });
  for (const checkboxId of checkedIds.slice(1)) {
    document.getElementById(checkboxId).checked = false;
  }
}

function populateQuestionImageSelect(selectedFigureId = "") {
  const figures = state.approvedFiguresByTopicId.get(state.selectedTopicId) || [];
  populateSelect(document.getElementById("question-image-select"), figures, {
    valueKey: "id",
    labelBuilder: (figure) => figure.name,
    selectedValue: selectedFigureId,
    placeholder: "No image attached",
  });
}

function clearQuestionImageChoices() {
  clearSelect(document.getElementById("question-image-select"), "No image attached");
  renderQuestionImagePreview();
}

function getSelectedImageId() {
  return document.getElementById("question-image-select").value || "";
}

function renderQuestionImagePreview() {
  const previewElement = document.getElementById("question-image-preview");
  const selectedImageId = getSelectedImageId();
  const figures = state.approvedFiguresByTopicId.get(state.selectedTopicId) || [];
  const figure = figures.find((item) => String(item.id) === String(selectedImageId));
  if (!figure) {
    previewElement.textContent = "No image attached.";
    return;
  }
  previewElement.innerHTML = `
    <article class="preview-card">
      <img class="preview-image" src="${escapeHtml(buildProjectFileUrl(figure.file_path))}" alt="${escapeHtml(figure.name)}">
      <div>
        <strong>${escapeHtml(figure.name)}</strong>
        <div class="helper-text">Attached to this question when you save.</div>
      </div>
    </article>
  `;
}

function renderAdminOverview() {
  const container = document.getElementById("admin-overview");
  const chapterCount = (state.chaptersBySubjectId.get(state.selectedSubjectId) || []).length;
  const topicCount = (state.topicsByChapterId.get(state.selectedChapterId) || []).length;
  const selectedSubject = state.subjects.find((subject) => subject.id === state.selectedSubjectId);
  const selectedChapter = (state.chaptersBySubjectId.get(state.selectedSubjectId) || []).find((chapter) => chapter.id === state.selectedChapterId);
  const selectedTopic = (state.topicsByChapterId.get(state.selectedChapterId) || []).find((topic) => topic.id === state.selectedTopicId);

  container.innerHTML = `
    <div class="summary-grid">
      <article class="summary-card">
        <span class="helper-text">Subjects</span>
        <strong>${escapeHtml(state.subjects.length)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Chapters In Scope</span>
        <strong>${escapeHtml(chapterCount)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Topics In Scope</span>
        <strong>${escapeHtml(topicCount)}</strong>
      </article>
      <article class="summary-card">
        <span class="helper-text">Questions In Topic</span>
        <strong>${escapeHtml(state.currentQuestions.length)}</strong>
      </article>
    </div>
    <article class="list-card">
      <strong>Current Focus</strong>
      <div>${escapeHtml([
        selectedSubject ? formatSubjectLabel(selectedSubject) : null,
        selectedChapter ? formatChapterLabel(selectedChapter) : null,
        selectedTopic ? selectedTopic.name : null,
      ].filter(Boolean).join(" | ") || "Choose a subject, chapter, and topic to start.")}</div>
    </article>
  `;
}

function buildScopeLabel() {
  const selectedSubject = state.subjects.find((subject) => subject.id === state.selectedSubjectId);
  const selectedChapter = (state.chaptersBySubjectId.get(state.selectedSubjectId) || []).find((chapter) => chapter.id === state.selectedChapterId);
  const selectedTopic = (state.topicsByChapterId.get(state.selectedChapterId) || []).find((topic) => topic.id === state.selectedTopicId);
  return [
    selectedSubject ? formatSubjectLabel(selectedSubject) : null,
    selectedChapter ? formatChapterLabel(selectedChapter) : null,
    selectedTopic ? selectedTopic.name : null,
  ].filter(Boolean).join(" | ") || "No scope selected";
}


function renderQuestionEditorState() {
  const banner = document.getElementById("question-editor-state");
  const saveButton = document.getElementById("save-question-button");
  const deleteButton = document.getElementById("delete-question-button");

  if (!state.selectedTopicId) {
    banner.textContent = "Select a topic to start creating questions.";
  } else if (state.editingQuestionId) {
    banner.textContent = "Editing the selected question. Save changes or delete it.";
  } else {
    banner.textContent = "Creating a new question for the selected topic.";
  }

  saveButton.textContent = state.editingQuestionId ? "Save Changes" : "Create Question";
  deleteButton.disabled = !state.editingQuestionId;
}

function populateSelect(selectElement, items, { valueKey, labelBuilder, selectedValue = "", placeholder = "Select" }) {
  if (!selectElement) {
    return;
  }
  const selected = items.some((item) => String(item[valueKey]) === String(selectedValue)) ? String(selectedValue) : "";
  selectElement.innerHTML = [`<option value="">${escapeHtml(placeholder)}</option>`]
    .concat(items.map((item) => `<option value="${escapeHtml(item[valueKey])}" ${String(item[valueKey]) === selected ? "selected" : ""}>${escapeHtml(labelBuilder(item))}</option>`))
    .join("");
}

function clearSelect(selectElement, placeholder = "Select") {
  if (!selectElement) {
    return;
  }
  selectElement.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>`;
}

async function apiRequest(url, method = "GET", body = undefined, isFormData = false) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    if (isFormData) {
      options.body = body;
    } else {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
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

function buildProjectFileUrl(filePath) {
  const relativePath = String(filePath).replace(`${projectRoot}/`, "").replace(/^\//, "");
  return `/project-files/${relativePath}`;
}

function setStatus(message, isError = false) {
  const banner = document.getElementById("status-banner");
  banner.textContent = message;
  banner.classList.toggle("is-error", isError);
}

function formatAdminLabel(admin) {
  return `${admin.full_name} | ${admin.email}`;
}

function formatSubjectLabel(subject) {
  return `${subject.name} | Grade ${subject.grade} | ${subject.board}`;
}

function formatChapterLabel(chapter) {
  return `Chapter ${chapter.chapter_number}: ${chapter.name}`;
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

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function handleUnexpectedError(error) {
  setStatus(error?.message ?? "Unexpected admin error.", true);
}
