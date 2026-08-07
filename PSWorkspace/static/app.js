/* PS Workspace - SPA Frontend Logic */

(function () {
  "use strict";

  /* ─── Auth Helpers ──────────────────────────────────────── */

  function getToken() {
    return localStorage.getItem("psws_token");
  }

  function clearSession() {
    localStorage.removeItem("psws_token");
    localStorage.removeItem("psws_user");
    fetch("/api/auth/logout", { method: "POST" }).finally(function () {
      window.location.href = "/login";
    });
  }

  function authenticatedFetch(url, options) {
    var opts = options || {};
    opts.headers = opts.headers || {};
    opts.headers["Content-Type"] = "application/json";
    var token = getToken();
    if (token) {
      opts.headers["Authorization"] = "Bearer " + token;
    }

    return fetch(url, opts).then(function (resp) {
      if (resp.status === 401) {
        clearSession();
        throw new Error("Session expired");
      }
      return resp;
    });
  }

  /* ─── SPA Navigation ────────────────────────────────────── */

  var pageMap = {
    "home": "page-home",
    "edm-agent": "page-edm-agent",
    "edm-dashboard": "page-edm-dashboard",
    "tfs": "page-tfs",
    "icm": "page-icm",
    "calendar": "page-calendar",
    "settings": "page-settings",
    "quiz": "page-quiz",
  };

  function setActiveNav(page) {
    var items = document.querySelectorAll(".sidebar-item");
    for (var i = 0; i < items.length; i++) {
      items[i].classList.remove("active");
      var href = items[i].getAttribute("data-page");
      if (href && (page === href || page.startsWith(href))) {
        items[i].classList.add("active");
      }
    }
  }

  function navigate(page) {
    // Hide quiz overlay when navigating away from quiz
    if (page !== "quiz") {
      var quizOverlay = document.getElementById("quiz-overlay");
      if (quizOverlay) quizOverlay.remove();
    }

    // Hide all page sections
    var sections = document.querySelectorAll(".page-section");
    for (var i = 0; i < sections.length; i++) {
      sections[i].classList.remove("active");
    }

    // Show target section
    var sectionId = pageMap[page];
    if (sectionId) {
      var target = document.getElementById(sectionId);
      if (target) target.classList.add("active");
    }

    // Update sidebar active state
    setActiveNav(page);

    // Init section data on first visit (exposed for templates)
    if (window.initSection) {
      window.initSection(page);
    }
  }

  /* ─── Task Polling ──────────────────────────────────────── */

  function pollTask(taskId, callback, interval) {
    interval = interval || 2000;
    function check() {
      authenticatedFetch("/api/task/" + taskId)
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (callback) callback(data);
          if (data.status === "completed" || data.status === "failed") {
            return;
          }
          setTimeout(check, interval);
        })
        .catch(function (e) { console.error("Poll error:", e); });
    }
    check();
  }

  function startTask(taskId, logElementId) {
    var logEl = document.getElementById(logElementId);
    if (!logEl) return;
    pollTask(taskId, function (data) {
      var statusHtml = data.status === "completed"
        ? '<span class="status-badge done">Completed</span>'
        : data.status === "failed"
        ? '<span class="status-badge error">Failed</span>'
        : '<span class="status-badge running">Running...</span>';
      var log = data.stdout || "";
      if (data.stderr && data.stderr.trim()) {
        if (data.status === "failed") {
          log += "\n[Error] " + data.stderr;
        } else {
          log += "\n[Stderr] " + data.stderr;
        }
      }
      logEl.innerHTML = '<div class="log-output">' + log.replace(/\n/g, "<br>") + '</div>';
      var statusEl = document.getElementById("task-status-" + taskId);
      if (statusEl) statusEl.innerHTML = statusHtml;
    });
  }

  /* ─── Utility ───────────────────────────────────────────── */

  function formatDate(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    return d.toLocaleDateString() + " " + d.toLocaleTimeString();
  }

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  /* ─── Global Exports ────────────────────────────────────── */

  window.pswp = {
    authenticatedFetch: authenticatedFetch,
    navigate: navigate,
    pollTask: pollTask,
    startTask: startTask,
    formatDate: formatDate,
    formatSize: formatSize,
    clearSession: clearSession,
  };

  /* ─── Init ──────────────────────────────────────────────── */

  document.addEventListener("DOMContentLoaded", function () {
    // Restore user display from localStorage
    var savedUser = localStorage.getItem("psws_user");
    if (savedUser) {
      var avatar = document.getElementById("user-avatar");
      var display = document.getElementById("user-display");
      if (avatar) avatar.textContent = savedUser.charAt(0).toUpperCase();
      if (display) display.textContent = savedUser;
    }

    // Verify token on page load
    var token = getToken();
    if (token) {
      fetch("/api/auth/verify", {
        headers: { "Authorization": "Bearer " + token }
      })
      .then(function(r) {
        if (r.status === 401) {
          localStorage.removeItem("psws_token");
          localStorage.removeItem("psws_user");
          window.location.href = "/login";
        }
      });
    } else {
      window.location.href = "/login";
    }

    // Default to home page active
    setActiveNav("home");

    // Auto-hide alerts after 5 seconds
    var alerts = document.querySelectorAll(".alert-autohide");
    for (var i = 0; i < alerts.length; i++) {
      setTimeout(function (el) { el.style.display = "none"; }, 5000, alerts[i]);
    }
  });

})();
