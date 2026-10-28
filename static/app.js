
const $ = (id) => document.getElementById(id);

let allRecords = [];
let currentPage = "home";

const PAGE_TITLES = {
  home: "Workspace",
  scan: "Scan Media",
  history: "History",
  records: "Records",
  profile: "Profile"
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

function formatBytes(bytes) {
  const size = Number(bytes) || 0;

  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 ** 3) {
    return `${(size / (1024 * 1024)).toFixed(2)} MB`;
  }

  return `${(size / 1024 ** 3).toFixed(2)} GB`;
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remaining = total % 60;

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
  }

  return `${minutes}:${String(remaining).padStart(2, "0")}`;
}

function formatDate(value) {
  if (!value) return "Unknown date";

  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? String(value)
    : date.toLocaleString();
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }

  return data;
}

/* LOGIN */

function showApp(email) {
  $("login-screen")?.classList.add("hidden");
  $("app-screen")?.classList.remove("hidden");

  if ($("profile-email")) {
    $("profile-email").textContent = email;
  }

  showPage("home");
}

function signOut() {
  sessionStorage.removeItem("deepguard-demo-email");
  sessionStorage.removeItem("deepguard_demo_email");

  $("app-screen")?.classList.add("hidden");
  $("login-screen")?.classList.remove("hidden");
  $("login-form")?.reset();
}

function setupLogin() {
  const form = $("login-form");
  if (!form) return;

  form.addEventListener("submit", (event) => {
    event.preventDefault();

    const email = $("email")?.value.trim() || "";
    const password = $("password")?.value || "";

    if (!email || !password) {
      alert("Please enter your email and password.");
      return;
    }

    if (password.length < 8) {
      alert("Your password must contain at least 8 characters.");
      return;
    }

    // Demo-only access. This is not real account registration.
    sessionStorage.setItem("deepguard-demo-email", email);
    showApp(email);
  });

  $("sign-out")?.addEventListener("click", signOut);
}

/* NAVIGATION */

function showPage(page) {
  if (!PAGE_TITLES[page]) return;

  currentPage = page;

  document.querySelectorAll(".page").forEach((section) => {
    section.classList.toggle("hidden", section.id !== `page-${page}`);
  });

  $("page-title").textContent = PAGE_TITLES[page];

  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.page === page);
  });

  if (page === "home" || page === "history" || page === "records") {
    refreshData();
  }
}

function setupNavigation() {
  document.querySelectorAll("[data-page]").forEach((button) => {
    button.addEventListener("click", () => showPage(button.dataset.page));
  });
}

/* VIDEO FRAME GALLERY */

function renderFrames(record) {
  const frames = Array.isArray(record.frames) ? record.frames : [];

  if (!frames.length) {
    return `<p class="muted">No extracted frames are available for this scan.</p>`;
  }

  return `
    <div class="frame-grid">
      ${frames.map((frame, index) => {
        const frameUrl = frame.url || "";
        const time = frame.timestamp_seconds;

        return `
          <figure class="frame-card">
            <a href="${escapeHtml(frameUrl)}" target="_blank" rel="noopener">
              <img
                src="${escapeHtml(frameUrl)}"
                alt="Extracted frame ${index + 1}"
                loading="lazy"
              >
            </a>
            <figcaption>
              Frame ${index + 1}
              ${time != null ? ` · ${escapeHtml(formatDuration(time))}` : ""}
            </figcaption>
          </figure>
        `;
      }).join("")}
    </div>
  `;
}

function renderVideoDetails(record) {
  const frames = Array.isArray(record.frames) ? record.frames : [];
  const frameCount = Number(record.frame_count) || frames.length;
  const resolution = record.width && record.height
    ? `${record.width} × ${record.height}`
    : "Unavailable";

  return `
    <div class="video-details-content">
      <h4>Video overview</h4>

      <div class="video-meta">
        <div>
          <small>FILENAME</small>
          <strong>${escapeHtml(record.filename)}</strong>
        </div>
        <div>
          <small>DURATION</small>
          <strong>${escapeHtml(formatDuration(record.duration_seconds))}</strong>
        </div>
        <div>
          <small>RESOLUTION</small>
          <strong>${escapeHtml(resolution)}</strong>
        </div>
        <div>
          <small>FILE SIZE</small>
          <strong>${escapeHtml(formatBytes(record.file_size))}</strong>
        </div>
        <div>
          <small>EXTRACTED FRAMES</small>
          <strong>${frameCount}</strong>
        </div>
        <div>
          <small>AI DETECTION</small>
          <strong>Not connected</strong>
        </div>
      </div>

      <h4>Extracted frames</h4>
      ${renderFrames(record)}

      <p class="video-note">
        These thumbnails are sampled frames, not an AI deepfake verdict.
      </p>
    </div>
  `;
}

/* RECORD CARDS */

function renderRecordCard(record, options = {}) {
  const showDetailsButton = record.media_type === "video";
  const showDelete = options.allowDelete === true;
  const frameCount = Number(record.frame_count) || 0;

  return `
    <article class="record-card">
      <div class="record-card-top">
        <div class="record-icon">
          ${record.media_type === "video" ? "▷" : "▧"}
        </div>

        <div class="record-file">
          <strong>${escapeHtml(record.filename)}</strong>
          <small>
            ${escapeHtml(String(record.media_type || "media").toUpperCase())}
            · ${escapeHtml(formatBytes(record.file_size))}
          </small>
          <small>${escapeHtml(formatDate(record.created_at))}</small>
        </div>
      </div>

      <div class="record-tags">
        ${showDetailsButton
          ? `<span>${frameCount} extracted frames</span>`
          : `<span>Image record</span>`}
        <span>AI model not connected</span>
      </div>

      <div class="record-actions">
        ${showDetailsButton
          ? `<button type="button" data-toggle-record="${escapeHtml(record.id)}">
               View video details
             </button>`
          : ""}

        ${record.report_url
          ? `<a href="${escapeHtml(record.report_url)}">PDF report</a>`
          : ""}

        ${showDelete
          ? `<button class="delete-record" type="button"
                      data-delete-record="${escapeHtml(record.id)}">
               Delete
             </button>`
          : ""}
      </div>

      ${showDetailsButton
        ? `<div class="record-details hidden"
                id="record-details-${escapeHtml(record.id)}">
             ${renderVideoDetails(record)}
           </div>`
        : ""}
    </article>
  `;
}

function renderRecordList(records, target, options = {}) {
  if (!target) return;

  if (!records.length) {
    target.innerHTML = `
      <div class="empty-card">
        <div class="empty-icon">▱</div>
        <strong>No records found</strong>
        <p class="muted">Try another filter or upload media to get started.</p>
      </div>
    `;
    return;
  }

  target.innerHTML = records.map((record) =>
    renderRecordCard(record, options)
  ).join("");

  target.querySelectorAll("[data-toggle-record]").forEach((button) => {
    button.addEventListener("click", () => {
      const details = document.getElementById(
        `record-details-${button.dataset.toggleRecord}`
      );

      if (!details) return;

      const willOpen = details.classList.contains("hidden");
      details.classList.toggle("hidden", !willOpen);
      button.textContent = willOpen ? "Hide video details" : "View video details";
    });
  });

  target.querySelectorAll("[data-delete-record]").forEach((button) => {
    button.addEventListener("click", async () => {
      const scanId = button.dataset.deleteRecord;

      if (!confirm("Delete this record and its stored media files?")) return;

      button.disabled = true;

      try {
        await api(`/api/screenings/${encodeURIComponent(scanId)}`, {
          method: "DELETE"
        });

        await refreshData();
      } catch (error) {
        alert(error.message);
        button.disabled = false;
      }
    });
  });
}

/* WORKSPACE, HISTORY, RECORDS */

function renderDedicatedRecords() {
  const search = ($("records-search")?.value || "").trim().toLowerCase();
  const filter = $("records-filter")?.value || "all";

  const filtered = allRecords.filter((record) => {
    const filename = String(record.filename || "").toLowerCase();
    const matchesSearch = filename.includes(search);
    const matchesFilter = filter === "all" || record.media_type === filter;

    return matchesSearch && matchesFilter;
  });

  if ($("records-total")) {
    $("records-total").textContent = allRecords.length;
  }

  if ($("records-videos")) {
    $("records-videos").textContent = allRecords.filter(
      (record) => record.media_type === "video"
    ).length;
  }

  if ($("records-images")) {
    $("records-images").textContent = allRecords.filter(
      (record) => record.media_type === "image"
    ).length;
  }

  renderRecordList(filtered, $("records-list"), { allowDelete: true });
}

async function refreshData() {
  try {
    const [status, records] = await Promise.all([
      api("/api/status"),
      api("/api/screenings")
    ]);

    allRecords = Array.isArray(records) ? records : [];

    if ($("total-count")) {
      $("total-count").textContent =
        status.total_screenings ?? allRecords.length;
    }

    renderRecordList(allRecords.slice(0, 3), $("recent-list"));
    renderRecordList(allRecords.slice(0, 10), $("history-list"), {
      allowDelete: true
    });

    renderDedicatedRecords();
  } catch (error) {
    const message = `<p class="muted">Unable to load records: ${escapeHtml(error.message)}</p>`;

    if ($("recent-list")) $("recent-list").innerHTML = message;
    if ($("history-list")) $("history-list").innerHTML = message;
    if ($("records-list")) $("records-list").innerHTML = message;
  }
}

/* SCAN MEDIA */

function showScanMessage(message, isError = false) {
  const box = $("scan-message");
  if (!box) return;

  box.textContent = message;
  box.classList.remove("hidden", "error");

  if (isError) box.classList.add("error");
}

function setupFilePicker() {
  $("media-file")?.addEventListener("change", () => {
    const file = $("media-file").files?.[0];

    if ($("file-label")) {
      $("file-label").textContent = file
        ? `${file.name} · ${formatBytes(file.size)}`
        : "Select media";
    }

    $("video-details")?.classList.add("hidden");
    if ($("video-details")) $("video-details").innerHTML = "";
    $("scan-message")?.classList.add("hidden");
  });
}

async function setupScanForm() {
  const form = $("scan-form");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const file = $("media-file")?.files?.[0];

    if (!file) {
      showScanMessage("Choose an image or video first.", true);
      return;
    }

    if (file.size > 200 * 1024 * 1024) {
      showScanMessage("The maximum upload size is 200 MB.", true);
      return;
    }

    const button = $("run-button");
    const details = $("video-details");

    button.disabled = true;
    button.textContent = "Processing…";
    showScanMessage("Uploading media and processing frames…");

    try {
      const body = new FormData();
      body.append("file", file);

      const result = await api("/api/screen", {
        method: "POST",
        body
      });

      if (details) {
        details.innerHTML = "";

        if (result.media_type === "video") {
          details.innerHTML = renderVideoDetails(result);
          details.classList.remove("hidden");
        } else {
          details.classList.add("hidden");
        }
      }

      const message = $("scan-message");
      message.textContent = result.notice || "Media processed.";
      message.classList.remove("hidden", "error");

      // DeepGuard AI screening result and confidence meter
      if (result.ai_result) {
        const ai = result.ai_result;
        const panel = document.createElement("section");
        panel.className = "confidence-panel";

        const title = document.createElement("h3");
        title.textContent = "DeepGuard Screening Result";

        const verdict = document.createElement("p");
        verdict.className = "confidence-verdict";
        verdict.textContent = "Prediction: " + (ai.prediction || "INCONCLUSIVE");

        const validScore =
          ai.status === "completed" &&
          Number.isFinite(Number(ai.confidence)) &&
          Number(ai.confidence) >= 0 &&
          Number(ai.confidence) <= 100;

        const meterLabel = document.createElement("p");
        meterLabel.className = "confidence-label";
        meterLabel.textContent = validScore
          ? "Model confidence: " + Number(ai.confidence).toFixed(2) + "%"
          : "Model confidence unavailable";

        const meter = document.createElement("div");
        meter.className = "confidence-track";
        meter.setAttribute("role", "progressbar");
        meter.setAttribute("aria-label", "Model confidence");
        meter.setAttribute("aria-valuemin", "0");
        meter.setAttribute("aria-valuemax", "100");

        const fill = document.createElement("div");
        fill.className = "confidence-fill";
        fill.style.width = validScore ? Number(ai.confidence) + "%" : "0%";
        if (validScore) {
          meter.setAttribute("aria-valuenow", String(Number(ai.confidence)));
        }

        meter.appendChild(fill);

        const scores = document.createElement("p");
        scores.className = "confidence-scores";
        scores.textContent = validScore
          ? "REAL score: " + (ai.real_score ?? "—") +
            "% · FAKE score: " + (ai.fake_score ?? "—") + "%"
          : "No reliable AI prediction was produced.";

        const warning = document.createElement("small");
        warning.className = "confidence-warning";
        warning.textContent =
          ai.warning ||
          "Experimental model estimate only. Confidence is not proof of authenticity.";

        panel.append(title, verdict, meterLabel, meter, scores, warning);
        message.appendChild(panel);
      }

      if (result.report_url) {
        const link = document.createElement("a");
        link.href = result.report_url;
        link.textContent = "Download PDF report";
        link.className = "scan-report-link";
        message.append(document.createElement("br"), link);
      }

      form.reset();
      if ($("file-label")) $("file-label").textContent = "Select media";

      await refreshData();
    } catch (error) {
      showScanMessage(error.message || "The scan failed.", true);
    } finally {
      button.disabled = false;
      button.textContent = "▷  Record screening";
    }
  });
}

/* RECORDS CONTROLS */

function setupRecordsControls() {
  $("refresh-records")?.addEventListener("click", refreshData);
  $("records-search")?.addEventListener("input", renderDedicatedRecords);
  $("records-filter")?.addEventListener("change", renderDedicatedRecords);
}

/* STARTUP */

document.addEventListener("DOMContentLoaded", () => {
  setupLogin();
  setupNavigation();
  setupFilePicker();
  setupScanForm();
  setupRecordsControls();

  const savedEmail =
    sessionStorage.getItem("deepguard-demo-email") ||
    sessionStorage.getItem("deepguard_demo_email");

  if (savedEmail) {
    showApp(savedEmail);
  } else {
    $("login-screen")?.classList.remove("hidden");
    $("app-screen")?.classList.add("hidden");
  }
});
