const UPLOAD_MAX_BYTES = 10 * 1024 * 1024;
const UPLOAD_ALLOWED_EXT = new Set([
  "jpg",
  "jpeg",
  "png",
  "gif",
  "webp",
  "bmp",
  "pdf",
  "doc",
  "docx",
  "txt",
  "rtf",
  "odt",
  "xls",
  "xlsx",
  "csv",
  "ppt",
  "pptx",
]);

function fileExt(name) {
  const parts = String(name || "").toLowerCase().split(".");
  return parts.length > 1 ? parts.pop() : "";
}

function validateUploadFile(file) {
  const ext = fileExt(file.name);
  if (!UPLOAD_ALLOWED_EXT.has(ext)) {
    return "«" + file.name + "»: только фото и документы (pdf, docx, txt, jpg…)";
  }
  if (file.size > UPLOAD_MAX_BYTES) {
    return "«" + file.name + "»: больше 10 МБ";
  }
  return "";
}

function filterUploadFiles(fileList) {
  const ok = [];
  const errors = [];
  Array.from(fileList || []).forEach((file) => {
    const err = validateUploadFile(file);
    if (err) errors.push(err);
    else ok.push(file);
  });
  return { ok, errors };
}

function fileKey(file) {
  return file.name + ":" + file.size + ":" + file.lastModified;
}

function dropzoneComponent() {
  return {
    dragging: false,
    files: [],
    error: "",
    applyFiles(list) {
      const { ok, errors } = filterUploadFiles(list);
      this.error = errors.length ? errors.join(" · ") : "";
      const map = new Map();
      ok.forEach((f) => map.set(fileKey(f), f));
      const dt = new DataTransfer();
      map.forEach((f) => dt.items.add(f));
      if (this.$refs.input) this.$refs.input.files = dt.files;
      this.files = Array.from(dt.files);
    },
    onSelect(event) {
      const incoming = Array.from(event.target.files || []);
      const previous = this.files.slice();
      this.applyFiles(previous.concat(incoming));
    },
    onDrop(event) {
      this.dragging = false;
      const incoming = Array.from(event.dataTransfer.files || []);
      this.applyFiles(this.files.concat(incoming));
    },
    removeAt(index) {
      const next = this.files.slice();
      next.splice(index, 1);
      this.applyFiles(next);
      this.error = "";
    },
  };
}

function creditExam(config) {
  return {
    endsAt: new Date(config.endsAt).getTime(),
    duration: Math.max(1, Number(config.duration) || 1),
    remaining: Math.max(0, Number(config.remaining) || 0),
    autosaveUrl: config.autosaveUrl,
    uploadUrl: config.uploadUrl,
    finishUrl: config.finishUrl,
    csrf: config.csrf,
    text: config.initialText || "",
    timerLabel: "--:--",
    timerClass: "",
    saveState: "",
    showFiveMinWarn: false,
    fiveMinWarned: false,
    dragging: false,
    uploaded: Array.isArray(config.initialFiles) ? config.initialFiles.slice() : [],
    autoSubmitting: false,
    tickTimer: null,

    init() {
      this.tick();
      this.tickTimer = setInterval(() => this.tick(), 250);
    },

    formatTime(sec) {
      const s = Math.max(0, Math.floor(sec));
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      const r = s % 60;
      if (h > 0) {
        return `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
      }
      return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
    },

    colorClass(rem) {
      const ratio = rem / this.duration;
      if (rem <= 60) return "is-critical";
      if (rem <= 300 || ratio <= 0.15) return "is-danger";
      if (ratio <= 0.4) return "is-warn";
      return "";
    },

    tick() {
      const rem = Math.max(0, Math.floor((this.endsAt - Date.now()) / 1000));
      this.remaining = rem;
      this.timerLabel = this.formatTime(rem);
      this.timerClass = this.colorClass(rem);

      if (rem <= 300 && rem > 0 && !this.fiveMinWarned) {
        this.fiveMinWarned = true;
        this.showFiveMinWarn = true;
      }

      if (rem <= 0 && !this.autoSubmitting) {
        if (this.tickTimer) clearInterval(this.tickTimer);
        this.autoFinish();
      }
    },

    async autosaveText() {
      this.saveState = "Сохранение…";
      try {
        const body = new FormData();
        body.append("text", this.text);
        body.append("csrfmiddlewaretoken", this.csrf);
        const res = await fetch(this.autosaveUrl, {
          method: "POST",
          body,
          credentials: "same-origin",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        const data = await res.json();
        if (data.expired && data.redirect) {
          window.location.href = data.redirect;
          return;
        }
        if (data.ok) {
          const t = new Date();
          this.saveState =
            "Сохранено · " +
            t.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
        } else {
          this.saveState = "Не удалось сохранить";
        }
      } catch (e) {
        this.saveState = "Ошибка сохранения";
      }
    },

    async uploadFiles(fileList) {
      const { ok, errors } = filterUploadFiles(fileList);
      if (errors.length) {
        this.saveState = errors.join(" · ");
      }
      if (!ok.length) return;
      this.saveState = "Загрузка файлов…";
      const body = new FormData();
      ok.forEach((f) => body.append("files", f));
      body.append("csrfmiddlewaretoken", this.csrf);
      try {
        const res = await fetch(this.uploadUrl, {
          method: "POST",
          body,
          credentials: "same-origin",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        const data = await res.json();
        if (data.expired && data.redirect) {
          window.location.href = data.redirect;
          return;
        }
        if (data.ok && data.files) {
          this.uploaded = this.uploaded.concat(data.files);
          this.saveState = data.errors && data.errors.length
            ? data.errors.join(" · ")
            : "Файлы загружены";
        } else {
          this.saveState =
            (data.errors && data.errors.join(" · ")) || "Не удалось загрузить файлы";
        }
      } catch (e) {
        this.saveState = "Ошибка загрузки";
      }
    },

    async removeFile(file) {
      if (!file || !file.deleteUrl) return;
      this.saveState = "Удаление файла…";
      const body = new FormData();
      body.append("csrfmiddlewaretoken", this.csrf);
      try {
        const res = await fetch(file.deleteUrl, {
          method: "POST",
          body,
          credentials: "same-origin",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        const data = await res.json();
        if (data.expired && data.redirect) {
          window.location.href = data.redirect;
          return;
        }
        if (data.ok) {
          this.uploaded = this.uploaded.filter((f) => f.id !== file.id);
          this.saveState = "Файл удалён";
        } else {
          this.saveState =
            (data.errors && data.errors.join(" · ")) || "Не удалось удалить файл";
        }
      } catch (e) {
        this.saveState = "Ошибка удаления";
      }
    },

    onSelect(event) {
      this.uploadFiles(event.target.files);
      event.target.value = "";
    },

    onDrop(event) {
      this.dragging = false;
      this.uploadFiles(event.dataTransfer.files);
    },

    beforeFinish(event) {
      // Confirm modal handles the gate; keep text synced.
      if (event && event.target) {
        const hidden = event.target.querySelector('input[name="text"]');
        if (hidden) hidden.value = this.text;
      }
    },

    async autoFinish() {
      if (this.autoSubmitting) return;
      this.autoSubmitting = true;
      this.saveState = "Время вышло — автоматическая сдача…";
      this.showFiveMinWarn = false;
      try {
        await this.autosaveText();
      } catch (e) {}
      const form = document.createElement("form");
      form.method = "POST";
      form.action = this.finishUrl;
      const csrf = document.createElement("input");
      csrf.type = "hidden";
      csrf.name = "csrfmiddlewaretoken";
      csrf.value = this.csrf;
      form.appendChild(csrf);
      const text = document.createElement("input");
      text.type = "hidden";
      text.name = "text";
      text.value = this.text;
      form.appendChild(text);
      document.body.appendChild(form);
      HTMLFormElement.prototype.submit.call(form);
    },
  };
}

function listFilter() {
  return {
    query: "",
    init() {
      this.$watch("query", () => this.applyFilter());
      this.$nextTick(() => this.applyFilter());
    },
    applyFilter() {
      const q = (this.query || "").trim().toLowerCase();
      this.$el.querySelectorAll("[data-filter-text]").forEach((el) => {
        const hay = (el.getAttribute("data-filter-text") || "").toLowerCase();
        const visible = !q || hay.includes(q);
        el.hidden = !visible;
        el.style.display = visible ? "" : "none";
      });
    },
    match(text) {
      const q = (this.query || "").trim().toLowerCase();
      if (!q) return true;
      return String(text || "")
        .toLowerCase()
        .includes(q);
    },
    hasVisible() {
      const nodes = this.$el.querySelectorAll("[data-filter-text]");
      if (!nodes.length) return true;
      return Array.from(nodes).some((el) => !el.hidden && el.style.display !== "none");
    },
  };
}

function bulkAssign() {
  return {
    query: "",
    init() {
      this.$watch("query", () => this.applyFilter());
      this.$nextTick(() => this.applyFilter());
    },
    applyFilter() {
      const q = (this.query || "").trim().toLowerCase();
      this.$el.querySelectorAll("[data-filter-text]").forEach((el) => {
        const hay = (el.getAttribute("data-filter-text") || "").toLowerCase();
        const visible = !q || hay.includes(q);
        el.hidden = !visible;
        el.style.display = visible ? "" : "none";
      });
    },
    match(text) {
      const q = (this.query || "").trim().toLowerCase();
      if (!q) return true;
      return String(text || "")
        .toLowerCase()
        .includes(q);
    },
  };
}

function appShell() {
  return {
    sidebarOpen: false,
    authLoading: false,
    authLoadingText: "Загрузка…",
    authSubmitting: false,
    confirmOpen: false,
    confirmTitle: "Подтверждение",
    confirmMessage: "",
    confirmActionLabel: "Подтвердить",
    confirmRequireLogin: "",
    confirmLoginInput: "",
    confirmForm: null,
    confirmUseSlider: false,
    sliderOffset: 0,
    sliderDragging: false,
    sliderAnimating: false,
    sliderStartX: 0,
    sliderStartOffset: 0,
    sliderMax: 0,
    sliderDone: false,
    get sliderFillWidth() {
      if (this.sliderOffset <= 0 && !this.sliderDone) return 0;
      // Fill reaches the right edge of the knob (inset 4 + knob 44 + offset)
      return Math.max(0, this.sliderOffset + 48);
    },
    pendingOpen: false,
    tasksOpen: false,
    notifToasts: [],
    notifLatestId: 0,
    notifPollUrl: "",
    notifTimer: null,
    init() {
      window.__neohub = this;
      try {
        this.tasksOpen = localStorage.getItem("neohub_tasks_open") === "1";
      } catch (e) {
        this.tasksOpen = false;
      }
      if (window.location.pathname.indexOf("/classroom/me/assignments") === 0) {
        this.tasksOpen = true;
      }
      this.bindHtmx();
      scheduleEnhanceDateTimeInputs();
      const poll = document.body.dataset.notifPoll;
      if (poll) {
        this.notifPollUrl = poll;
        const seed = parseInt(document.body.dataset.notifLatest || "0", 10);
        this.notifLatestId = Number.isFinite(seed) ? seed : 0;
        this.startNotifPoll();
      }
    },
    startNotifPoll() {
      if (!this.notifPollUrl || this.notifTimer) return;
      this.notifTimer = setInterval(() => this.pollNotifications(), 1000);
      setTimeout(() => this.pollNotifications(), 300);
    },
    async pollNotifications() {
      if (!this.notifPollUrl || document.hidden) return;
      try {
        const url =
          this.notifPollUrl +
          (this.notifPollUrl.indexOf("?") >= 0 ? "&" : "?") +
          "since=" +
          encodeURIComponent(this.notifLatestId || 0);
        const res = await fetch(url, {
          credentials: "same-origin",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        if (!res.ok) return;
        const data = await res.json();
        this.updateNotifBadge(data.unread || 0);
        if (data.latest_id && data.latest_id > this.notifLatestId) {
          (data.items || []).forEach((item) => this.pushNotifToast(item));
          this.notifLatestId = data.latest_id;
        } else if (data.latest_id && !this.notifLatestId) {
          this.notifLatestId = data.latest_id;
        }
      } catch (e) {}
    },
    updateNotifBadge(count) {
      const badge = document.getElementById("nav-notif-badge");
      if (!badge) return;
      if (count > 0) {
        badge.innerHTML = '<span class="badge">' + count + "</span>";
      } else {
        badge.innerHTML = "";
      }
    },
    pushNotifToast(item) {
      const id = item.id || Date.now();
      this.notifToasts.push({
        id,
        title: item.title || "Уведомление",
        message: item.message || "",
        link: item.link || "",
      });
      setTimeout(() => this.dismissNotifToast(id), 6500);
    },
    dismissNotifToast(id) {
      this.notifToasts = this.notifToasts.filter((t) => t.id !== id);
    },
    toggleTasks() {
      this.tasksOpen = !this.tasksOpen;
      try {
        localStorage.setItem("neohub_tasks_open", this.tasksOpen ? "1" : "0");
      } catch (e) {}
    },
    openPending() {
      this.pendingOpen = true;
    },
    closePending() {
      this.pendingOpen = false;
    },
    openConfirmFromForm(form) {
      this.confirmForm = form;
      this.confirmTitle = form.getAttribute("data-confirm-title") || "Подтверждение";
      this.confirmMessage = form.getAttribute("data-confirm-message") || "Подтвердите действие.";
      this.confirmActionLabel = form.getAttribute("data-confirm-action") || "Подтвердить";
      this.confirmRequireLogin = (form.getAttribute("data-confirm-login") || "").trim();
      this.confirmLoginInput = "";
      this.confirmUseSlider = form.hasAttribute("data-confirm-slider");
      this.sliderOffset = 0;
      this.sliderDragging = false;
      this.sliderAnimating = false;
      this.sliderDone = false;
      this.sliderMax = 0;
      this.confirmOpen = true;
      if (this.confirmUseSlider) {
        this.$nextTick(() => this.measureSlider());
      }
    },
    closeConfirm() {
      this.confirmOpen = false;
      this.confirmForm = null;
      this.confirmLoginInput = "";
      this.confirmUseSlider = false;
      this.sliderOffset = 0;
      this.sliderDragging = false;
      this.sliderAnimating = false;
      this.sliderDone = false;
    },
    canSubmitConfirm() {
      if (!this.confirmRequireLogin) return true;
      return this.confirmLoginInput === this.confirmRequireLogin;
    },
    measureSlider() {
      const track = document.querySelector(".confirm-slider-track");
      const knob = document.querySelector(".confirm-slider-knob");
      if (!track || !knob) return;
      const styles = window.getComputedStyle(track);
      const padL = parseFloat(styles.paddingLeft) || 4;
      const padR = parseFloat(styles.paddingRight) || 4;
      this.sliderMax = Math.max(0, track.clientWidth - knob.offsetWidth - padL - padR);
    },
    onSliderPointerDown(event) {
      if (!this.canSubmitConfirm() || this.sliderDone) return;
      const knob = event.target.closest(".confirm-slider-knob");
      if (!knob) return;
      this.measureSlider();
      this.sliderAnimating = false;
      this.sliderDragging = true;
      this.sliderStartX = event.clientX;
      this.sliderStartOffset = this.sliderOffset;
      try {
        event.currentTarget.setPointerCapture(event.pointerId);
      } catch (e) {}
      event.preventDefault();
    },
    onSliderPointerMove(event) {
      if (!this.sliderDragging) return;
      const delta = event.clientX - this.sliderStartX;
      let next = this.sliderStartOffset + delta;
      if (next < 0) next = 0;
      if (next > this.sliderMax) next = this.sliderMax;
      this.sliderOffset = next;
    },
    onSliderPointerUp(event) {
      if (!this.sliderDragging) return;
      this.sliderDragging = false;
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch (e) {}
      const threshold = this.sliderMax * 0.82;
      if (this.sliderMax > 0 && this.sliderOffset >= threshold) {
        this.sliderAnimating = true;
        this.sliderOffset = this.sliderMax;
        this.sliderDone = true;
        setTimeout(() => this.submitConfirm(), 220);
      } else {
        this.sliderAnimating = true;
        this.sliderOffset = 0;
        setTimeout(() => {
          this.sliderAnimating = false;
        }, 380);
      }
    },
    submitConfirm() {
      if (!this.canSubmitConfirm()) return;
      const form = this.confirmForm;
      if (!form) {
        this.closeConfirm();
        return;
      }
      if (this.confirmRequireLogin) {
        let input = form.querySelector('input[name="confirm_username"]');
        if (!input) {
          input = document.createElement("input");
          input.type = "hidden";
          input.name = "confirm_username";
          form.appendChild(input);
        }
        input.value = this.confirmLoginInput;
      }
      form.setAttribute("data-confirm-ok", "1");
      this.confirmOpen = false;
      this.confirmForm = null;
      this.confirmLoginInput = "";
      this.confirmUseSlider = false;
      this.sliderOffset = 0;
      this.sliderDragging = false;
      this.sliderAnimating = false;
      this.sliderDone = false;

      const authText = form.getAttribute("data-auth-loading");
      if (authText) {
        if (this.authSubmitting) return;
        this.authSubmitting = true;
        this.authLoading = true;
        this.authLoadingText = authText;
        setTimeout(() => {
          HTMLFormElement.prototype.submit.call(form);
        }, 850);
        return;
      }

      // HTMX forms confirmed via custom trigger (avoids fight with data-confirm)
      const hxPost = form.getAttribute("hx-post");
      if (hxPost && window.htmx) {
        const trigger = form.getAttribute("hx-trigger") || "";
        if (trigger.indexOf("confirmed") >= 0) {
          window.htmx.trigger(form, "confirmed");
        } else {
          window.htmx.ajax("POST", hxPost, {
            source: form,
            target: form.getAttribute("hx-target") || "body",
            swap: form.getAttribute("hx-swap") || "innerHTML",
            values: form,
          });
        }
        return;
      }

      // requestSubmit fires submit event so HTMX boost can soft-navigate
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
      } else {
        HTMLFormElement.prototype.submit.call(form);
      }
    },
    bindHtmx() {
      const sameSoftNavUrl = (href) => {
        if (!href) return false;
        try {
          // Use full current URL as base so "?tab=homework" keeps the path
          const next = new URL(href, window.location.href);
          return (
            next.pathname === window.location.pathname &&
            next.search === window.location.search
          );
        } catch (e) {
          return false;
        }
      };

      document.body.addEventListener("click", (event) => {
        const link = event.target.closest("a.soft-nav[hx-get], a.soft-nav[href]");
        if (!link) return;
        const href = link.getAttribute("hx-get") || link.getAttribute("href");
        if (!sameSoftNavUrl(href)) return;
        event.preventDefault();
        event.stopPropagation();
        if (typeof event.stopImmediatePropagation === "function") {
          event.stopImmediatePropagation();
        }
      }, true);

      document.body.addEventListener("htmx:beforeRequest", (event) => {
        const elt = event.detail && event.detail.elt;
        if (!elt || elt.tagName !== "A") return;
        const href = elt.getAttribute("hx-get") || elt.getAttribute("href");
        if (sameSoftNavUrl(href)) {
          event.preventDefault();
        }
      });

      document.body.addEventListener("htmx:afterSwap", (event) => {
        const target = event.detail && event.detail.target;
        if (window.Alpine && target && target.nodeType === 1) {
          try {
            window.Alpine.initTree(target);
          } catch (e) {}
        }
        scheduleEnhanceDateTimeInputs();
        this.pendingOpen = false;
        this.confirmOpen = false;
        this.sidebarOpen = false;
        this.syncNavActive();
        if (window.location.pathname.indexOf("/classroom/me/assignments") === 0) {
          this.tasksOpen = true;
          try {
            localStorage.setItem("neohub_tasks_open", "1");
          } catch (e) {}
        }
      });
    },
    syncNavActive() {
      const main = document.getElementById("page-content");
      const key = (main && main.dataset.activeNav) || "";
      const type = new URLSearchParams(window.location.search).get("type") || "all";
      document.querySelectorAll("[data-nav]").forEach((el) => {
        const nav = el.dataset.nav;
        const query = el.dataset.navQuery;
        let active = nav === key;
        if (query) {
          active = active && query === type;
        }
        el.classList.toggle("is-active", active);
      });
    },
  };
}

function studentCreateForm() {
  const LOWER = "abcdefghijklmnopqrstuvwxyz";
  const UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const DIGITS = "0123456789";

  function pick(alphabet, n) {
    let out = "";
    for (let i = 0; i < n; i += 1) {
      out += alphabet[Math.floor(Math.random() * alphabet.length)];
    }
    return out;
  }

  async function copyText(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (e) {}
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (e) {
      ok = false;
    }
    document.body.removeChild(ta);
    return ok;
  }

  return {
    copied: false,
    copyError: "",
    generateCredentials() {
      const login = pick(LOWER, 5) + pick(DIGITS, 2);
      const password = pick(UPPER, 1) + pick(LOWER, 5) + pick(DIGITS, 3);
      const username = document.getElementById("id_username");
      const passwordInput = document.getElementById("id_password");
      const confirmInput = document.getElementById("id_password_confirm");
      if (username) {
        username.value = login;
        username.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (passwordInput) {
        passwordInput.value = password;
        passwordInput.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (confirmInput) {
        confirmInput.value = password;
        confirmInput.dispatchEvent(new Event("input", { bubbles: true }));
      }
      this.copied = false;
      this.copyError = "";
    },
    async copyWelcome() {
      this.copyError = "";
      const name = (document.getElementById("id_display_name") || {}).value || "";
      const login = (document.getElementById("id_username") || {}).value || "";
      const password = (document.getElementById("id_password") || {}).value || "";
      if (!name.trim() || !login.trim() || !password) {
        this.copyError = "Заполните ФИО, логин и пароль перед копированием.";
        this.copied = false;
        return;
      }
      const text =
        name.trim() +
        ", добро пожаловать на платформу NeoHub.\n" +
        "Ваш логин: " +
        login.trim() +
        "\n" +
        "Ваш пароль: " +
        password;
      const ok = await copyText(text);
      this.copied = ok;
      if (!ok) {
        this.copyError = "Не удалось скопировать. Скопируйте вручную.";
      } else {
        setTimeout(() => {
          this.copied = false;
        }, 2500);
      }
    },
  };
}

function draftSubmit(config) {
  return {
    autosaveUrl: config.autosaveUrl,
    uploadUrl: config.uploadUrl,
    csrf: config.csrf,
    text: config.initialText || "",
    saveState: "",
    dragging: false,
    uploaded: Array.isArray(config.initialFiles) ? config.initialFiles.slice() : [],

    async autosaveText() {
      this.saveState = "Сохранение черновика…";
      try {
        const body = new FormData();
        body.append("text", this.text);
        body.append("csrfmiddlewaretoken", this.csrf);
        const res = await fetch(this.autosaveUrl, {
          method: "POST",
          body,
          credentials: "same-origin",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        const data = await res.json();
        if (data.ok) {
          const t = new Date();
          this.saveState =
            "Черновик сохранён · " +
            t.toLocaleTimeString("ru-RU", {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            });
        } else {
          this.saveState = "Не удалось сохранить";
        }
      } catch (e) {
        this.saveState = "Ошибка сохранения";
      }
    },

    async uploadFiles(fileList) {
      const { ok, errors } = filterUploadFiles(fileList);
      if (errors.length) {
        this.saveState = errors.join(" · ");
      }
      if (!ok.length) return;
      this.saveState = "Загрузка файлов…";
      const body = new FormData();
      ok.forEach((f) => body.append("files", f));
      body.append("csrfmiddlewaretoken", this.csrf);
      try {
        const res = await fetch(this.uploadUrl, {
          method: "POST",
          body,
          credentials: "same-origin",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        const data = await res.json();
        if (data.ok && data.files) {
          this.uploaded = this.uploaded.concat(data.files);
          this.saveState = data.errors && data.errors.length
            ? data.errors.join(" · ")
            : "Файлы загружены в черновик";
        } else {
          this.saveState =
            (data.errors && data.errors.join(" · ")) || "Не удалось загрузить файлы";
        }
      } catch (e) {
        this.saveState = "Ошибка загрузки";
      }
    },

    async removeFile(file) {
      if (!file || !file.deleteUrl) return;
      this.saveState = "Удаление файла…";
      const body = new FormData();
      body.append("csrfmiddlewaretoken", this.csrf);
      try {
        const res = await fetch(file.deleteUrl, {
          method: "POST",
          body,
          credentials: "same-origin",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        const data = await res.json();
        if (data.ok) {
          this.uploaded = this.uploaded.filter((f) => f.id !== file.id);
          this.saveState = "Файл удалён";
        } else {
          this.saveState =
            (data.errors && data.errors.join(" · ")) || "Не удалось удалить файл";
        }
      } catch (e) {
        this.saveState = "Ошибка удаления";
      }
    },

    onSelect(event) {
      this.uploadFiles(event.target.files);
      event.target.value = "";
    },

    onDrop(event) {
      this.dragging = false;
      this.uploadFiles(event.dataTransfer.files);
    },

    beforeSubmit(event) {
      if (event && event.target) {
        const hidden = event.target.querySelector('input[name="text"]');
        if (hidden) hidden.value = this.text;
      }
    },
  };
}

function assignmentsLive(config) {
  return {
    pollUrl: config.pollUrl,
    typeFilter: config.typeFilter || "all",
    version: config.version || "",
    countLabel: "",
    timer: null,
    busy: false,
    start() {
      const body = document.getElementById("assignments-live-body");
      if (body) {
        const n = body.querySelectorAll(".item-card").length;
        this.countLabel = n ? "· " + n : "";
        body.dataset.liveHtml = (body.innerHTML || "").trim();
      }
      this.stop();
      this.timer = setInterval(() => this.poll(), 7000);
      setTimeout(() => this.poll(), 2500);
      this.$el &&
        this.$el.addEventListener(
          "alpine:destroy",
          () => this.stop(),
          { once: true }
        );
    },
    stop() {
      if (this.timer) {
        clearInterval(this.timer);
        this.timer = null;
      }
    },
    async poll() {
      if (document.hidden || !this.pollUrl || this.busy) return;
      this.busy = true;
      try {
        const url =
          this.pollUrl +
          "?type=" +
          encodeURIComponent(this.typeFilter) +
          "&v=" +
          encodeURIComponent(this.version || "");
        const res = await fetch(url, {
          credentials: "same-origin",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        if (!res.ok) return;
        const data = await res.json();
        if (data.version) this.version = data.version;
        if (!data.changed) return;
        const body = document.getElementById("assignments-live-body");
        if (body && typeof data.html === "string") {
          const next = String(data.html).trim();
          // Skip identical markup — prevents cards flashing on every poll
          if (body.dataset.liveHtml === next) {
            const count = typeof data.count === "number" ? data.count : null;
            this.countLabel = count ? "· " + count : "";
            return;
          }
          const scrollParent =
            body.closest(".list-window-body-fill, .list-window-body") || body;
          const top = scrollParent.scrollTop;
          body.dataset.liveHtml = next;
          body.innerHTML = data.html;
          scrollParent.scrollTop = top;
          if (window.Alpine) {
            try {
              window.Alpine.initTree(body);
            } catch (e) {}
          }
          if (typeof window.scheduleEnhanceDateTimeInputs === "function") {
            window.scheduleEnhanceDateTimeInputs();
          }
        }
        const count = typeof data.count === "number" ? data.count : null;
        this.countLabel = count ? "· " + count : "";
      } catch (e) {
      } finally {
        this.busy = false;
      }
    },
  };
}

function pluralRu(n, one, few, many) {
  const abs = Math.abs(n) % 100;
  const n1 = abs % 10;
  if (abs > 10 && abs < 20) return many;
  if (n1 > 1 && n1 < 5) return few;
  if (n1 === 1) return one;
  return many;
}

function formatDeadlineRemaining(ms) {
  if (!Number.isFinite(ms) || ms <= 0) {
    return { text: "дедлайн истёк", expired: true };
  }
  const totalSec = Math.floor(ms / 1000);
  const days = Math.floor(totalSec / 86400);
  const hours = Math.floor((totalSec % 86400) / 3600);
  const mins = Math.floor((totalSec % 3600) / 60);
  const secs = totalSec % 60;

  if (days >= 1) {
    return {
      text:
        "осталось " +
        days +
        " " +
        pluralRu(days, "день", "дня", "дней") +
        " " +
        hours +
        " " +
        pluralRu(hours, "час", "часа", "часов"),
      expired: false,
    };
  }
  if (hours >= 1) {
    return {
      text:
        "осталось " +
        hours +
        " " +
        pluralRu(hours, "час", "часа", "часов") +
        " " +
        mins +
        " " +
        pluralRu(mins, "минута", "минуты", "минут"),
      expired: false,
    };
  }
  return {
    text:
      "осталось " +
      mins +
      " " +
      pluralRu(mins, "минута", "минуты", "минут") +
      " " +
      secs +
      " " +
      pluralRu(secs, "секунда", "секунды", "секунд"),
    expired: false,
  };
}

function deadlineCountdown(iso) {
  const endsAt = new Date(iso).getTime();
  const first = formatDeadlineRemaining(endsAt - Date.now());
  return {
    endsAt,
    label: first.text,
    expired: first.expired,
    timer: null,
    start() {
      this.stop();
      this.tick();
      this.timer = setInterval(() => this.tick(), 1000);
      if (this.$el) {
        this.$el.addEventListener(
          "alpine:destroy",
          () => this.stop(),
          { once: true }
        );
      }
    },
    stop() {
      if (this.timer) {
        clearInterval(this.timer);
        this.timer = null;
      }
    },
    tick() {
      const info = formatDeadlineRemaining(this.endsAt - Date.now());
      this.label = info.text;
      this.expired = info.expired;
      const card = this.$el && this.$el.closest(".item-card");
      if (card) {
        card.classList.toggle("is-overdue", Boolean(this.expired));
      }
      if (this.expired) this.stop();
    },
  };
}

/* NeoHub date-time picker (vanilla — no Alpine, modal lives on document.body) */
const NeoHubDTP = {
  MONTHS: [
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
  ],
  WEEKDAYS: ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
  overlay: null,
  input: null,
  trigger: null,
  viewYear: new Date().getFullYear(),
  viewMonth: new Date().getMonth(),
  selYear: null,
  selMonth: null,
  selDay: null,
  hour: 23,
  minute: 55,

  pad(n) {
    return String(n).padStart(2, "0");
  },

  parseValue(raw) {
    const m = String(raw || "").match(
      /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/
    );
    if (!m) return null;
    return {
      year: Number(m[1]),
      month: Number(m[2]) - 1,
      day: Number(m[3]),
      hour: Number(m[4]),
      minute: Number(m[5]),
    };
  },

  formatDisplay(raw) {
    const parsed = this.parseValue(raw);
    if (!parsed) return "";
    return (
      this.pad(parsed.day) +
      "." +
      this.pad(parsed.month + 1) +
      "." +
      parsed.year +
      " " +
      this.pad(parsed.hour) +
      ":" +
      this.pad(parsed.minute)
    );
  },

  defaultBaseDate() {
    const now = new Date();
    let base = new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate(),
      23,
      55,
      0,
      0
    );
    if (base.getTime() <= now.getTime()) {
      base = new Date(base.getTime() + 24 * 60 * 60 * 1000);
    }
    return base;
  },

  ensureOverlay() {
    if (this.overlay && document.body.contains(this.overlay)) return;
    // Drop leftovers from older picker versions
    document
      .querySelectorAll("body > .dtp-backdrop, body > .dtp-modal, body > .dtp-overlay")
      .forEach((el) => el.remove());

    const root = document.createElement("div");
    root.className = "dtp-overlay";
    root.hidden = true;
    root.innerHTML =
      '<div class="dtp-backdrop" data-dtp-action="close"></div>' +
      '<div class="dtp-modal" data-dtp-action="close-self">' +
      '<div class="dtp-panel" role="dialog" aria-modal="true">' +
      '<div class="dtp-month">' +
      '<button type="button" class="btn btn-ghost btn-sm" data-dtp-action="prev">‹</button>' +
      '<strong data-dtp-month-label></strong>' +
      '<button type="button" class="btn btn-ghost btn-sm" data-dtp-action="next">›</button>' +
      "</div>" +
      '<div class="dtp-weekdays">' +
      this.WEEKDAYS.map((w) => "<span>" + w + "</span>").join("") +
      "</div>" +
      '<div class="dtp-grid" data-dtp-grid></div>' +
      '<div class="dtp-time">' +
      '<div class="dtp-spin">' +
      '<button type="button" class="btn btn-ghost btn-sm" data-dtp-action="hour-up">▲</button>' +
      '<input type="text" class="input dtp-time-input" data-dtp-hour inputmode="numeric" maxlength="2">' +
      '<button type="button" class="btn btn-ghost btn-sm" data-dtp-action="hour-down">▼</button>' +
      '<span class="tiny muted">час</span></div>' +
      '<span class="dtp-colon">:</span>' +
      '<div class="dtp-spin">' +
      '<button type="button" class="btn btn-ghost btn-sm" data-dtp-action="minute-up">▲</button>' +
      '<input type="text" class="input dtp-time-input" data-dtp-minute inputmode="numeric" maxlength="2">' +
      '<button type="button" class="btn btn-ghost btn-sm" data-dtp-action="minute-down">▼</button>' +
      '<span class="tiny muted">мин</span></div></div>' +
      '<div class="dtp-actions">' +
      '<button type="button" class="btn btn-ghost btn-sm" data-dtp-action="clear">Очистить</button>' +
      '<button type="button" class="btn btn-primary btn-sm" data-dtp-action="apply">Готово</button>' +
      "</div></div></div>";

    root.addEventListener("click", (event) => {
      const actionEl = event.target.closest("[data-dtp-action]");
      if (!actionEl || !root.contains(actionEl)) return;
      const action = actionEl.getAttribute("data-dtp-action");
      if (action === "close") {
        event.preventDefault();
        this.close();
        return;
      }
      if (action === "close-self") {
        if (event.target === actionEl) {
          event.preventDefault();
          this.close();
        }
        return;
      }
      event.preventDefault();
      if (action === "prev") this.prevMonth();
      else if (action === "next") this.nextMonth();
      else if (action === "hour-up") this.bumpHour(1);
      else if (action === "hour-down") this.bumpHour(-1);
      else if (action === "minute-up") this.bumpMinute(1);
      else if (action === "minute-down") this.bumpMinute(-1);
      else if (action === "clear") this.clear();
      else if (action === "apply") this.apply();
      else if (action === "pick") {
        this.selYear = Number(actionEl.dataset.y);
        this.selMonth = Number(actionEl.dataset.m);
        this.selDay = Number(actionEl.dataset.day);
        this.viewYear = this.selYear;
        this.viewMonth = this.selMonth;
        this.render();
      }
    });

    root.addEventListener("change", (event) => {
      if (event.target.matches("[data-dtp-hour]")) this.readHourInput();
      if (event.target.matches("[data-dtp-minute]")) this.readMinuteInput();
    });
    root.addEventListener("blur", (event) => {
      if (event.target.matches("[data-dtp-hour]")) this.readHourInput();
      if (event.target.matches("[data-dtp-minute]")) this.readMinuteInput();
    }, true);

    document.body.appendChild(root);
    this.overlay = root;
  },

  isOpen() {
    return Boolean(this.overlay && !this.overlay.hidden);
  },

  open(input, trigger) {
    this.ensureOverlay();
    this.input = input;
    this.trigger = trigger;
    const parsed = this.parseValue(input ? input.value : "");
    if (parsed) {
      this.selYear = parsed.year;
      this.selMonth = parsed.month;
      this.selDay = parsed.day;
      this.viewYear = parsed.year;
      this.viewMonth = parsed.month;
      this.hour = parsed.hour;
      this.minute = parsed.minute;
    } else {
      const base = this.defaultBaseDate();
      this.viewYear = base.getFullYear();
      this.viewMonth = base.getMonth();
      this.selYear = null;
      this.selMonth = null;
      this.selDay = null;
      this.hour = 23;
      this.minute = 55;
    }
    this.overlay.hidden = false;
    this.render();
  },

  close() {
    if (this.overlay) this.overlay.hidden = true;
    this.input = null;
    this.trigger = null;
  },

  closeAll() {
    this.close();
  },

  updateTrigger() {
    if (!this.trigger || !this.input) return;
    const text = this.formatDisplay(this.input.value);
    const label = this.trigger.querySelector("[data-dtp-label]");
    if (label) label.textContent = text || "Выберите дату и время";
    this.trigger.classList.toggle("is-empty", !text);
  },

  writeValue(raw) {
    if (!this.input) return;
    this.input.value = raw || "";
    this.input.dispatchEvent(new Event("input", { bubbles: true }));
    this.input.dispatchEvent(new Event("change", { bubbles: true }));
    this.updateTrigger();
  },

  currentValue() {
    if (this.selDay == null) return "";
    return (
      this.selYear +
      "-" +
      this.pad(this.selMonth + 1) +
      "-" +
      this.pad(this.selDay) +
      "T" +
      this.pad(this.hour) +
      ":" +
      this.pad(this.minute)
    );
  },

  apply() {
    if (this.selDay == null) {
      const base = this.defaultBaseDate();
      this.selYear = base.getFullYear();
      this.selMonth = base.getMonth();
      this.selDay = base.getDate();
      this.viewYear = this.selYear;
      this.viewMonth = this.selMonth;
    }
    this.readHourInput();
    this.readMinuteInput();
    this.writeValue(this.currentValue());
    this.close();
  },

  clear() {
    this.selYear = null;
    this.selMonth = null;
    this.selDay = null;
    this.writeValue("");
    this.close();
  },

  bumpHour(delta) {
    this.hour = (this.hour + delta + 24) % 24;
    this.renderTimeInputs();
  },

  bumpMinute(delta) {
    let next = this.minute + delta;
    while (next < 0) next += 60;
    while (next >= 60) next -= 60;
    this.minute = next;
    this.renderTimeInputs();
  },

  readHourInput() {
    if (!this.overlay) return;
    const el = this.overlay.querySelector("[data-dtp-hour]");
    let n = parseInt(String(el && el.value).replace(/\D/g, ""), 10);
    if (!Number.isFinite(n)) n = this.hour;
    this.hour = Math.max(0, Math.min(23, n));
    this.renderTimeInputs();
  },

  readMinuteInput() {
    if (!this.overlay) return;
    const el = this.overlay.querySelector("[data-dtp-minute]");
    let n = parseInt(String(el && el.value).replace(/\D/g, ""), 10);
    if (!Number.isFinite(n)) n = this.minute;
    this.minute = Math.max(0, Math.min(59, n));
    this.renderTimeInputs();
  },

  prevMonth() {
    if (this.viewMonth === 0) {
      this.viewMonth = 11;
      this.viewYear -= 1;
    } else {
      this.viewMonth -= 1;
    }
    this.render();
  },

  nextMonth() {
    if (this.viewMonth === 11) {
      this.viewMonth = 0;
      this.viewYear += 1;
    } else {
      this.viewMonth += 1;
    }
    this.render();
  },

  renderTimeInputs() {
    if (!this.overlay) return;
    const hourEl = this.overlay.querySelector("[data-dtp-hour]");
    const minuteEl = this.overlay.querySelector("[data-dtp-minute]");
    if (hourEl) hourEl.value = this.pad(this.hour);
    if (minuteEl) minuteEl.value = this.pad(this.minute);
  },

  render() {
    if (!this.overlay) return;
    const label = this.overlay.querySelector("[data-dtp-month-label]");
    if (label) {
      label.textContent = this.MONTHS[this.viewMonth] + " " + this.viewYear;
    }
    this.renderTimeInputs();

    const grid = this.overlay.querySelector("[data-dtp-grid]");
    if (!grid) return;
    const first = new Date(this.viewYear, this.viewMonth, 1);
    const start = (first.getDay() + 6) % 7;
    const daysInMonth = new Date(this.viewYear, this.viewMonth + 1, 0).getDate();
    const prevDays = new Date(this.viewYear, this.viewMonth, 0).getDate();
    const today = new Date();
    let html = "";
    for (let i = 0; i < 42; i += 1) {
      let day;
      let inMonth = true;
      let y = this.viewYear;
      let m = this.viewMonth;
      if (i < start) {
        day = prevDays - start + i + 1;
        inMonth = false;
        m -= 1;
        if (m < 0) {
          m = 11;
          y -= 1;
        }
      } else if (i >= start + daysInMonth) {
        day = i - start - daysInMonth + 1;
        inMonth = false;
        m += 1;
        if (m > 11) {
          m = 0;
          y += 1;
        }
      } else {
        day = i - start + 1;
      }
      const selected =
        this.selDay === day && this.selMonth === m && this.selYear === y;
      const isToday =
        inMonth &&
        day === today.getDate() &&
        this.viewMonth === today.getMonth() &&
        this.viewYear === today.getFullYear();
      const cls =
        "dtp-day" +
        (!inMonth ? " is-muted" : "") +
        (selected ? " is-selected" : "") +
        (isToday ? " is-today" : "");
      html +=
        '<button type="button" class="' +
        cls +
        '" data-dtp-action="pick" data-y="' +
        y +
        '" data-m="' +
        m +
        '" data-day="' +
        day +
        '">' +
        day +
        "</button>";
    }
    grid.innerHTML = html;
  },
};

function dateTimePicker() {
  // Kept for compatibility; picker no longer uses Alpine components.
  return {};
}

function updateDateTimeTrigger(trigger, input) {
  if (!trigger || !input) return;
  const text = NeoHubDTP.formatDisplay(input.value);
  const label = trigger.querySelector("[data-dtp-label]");
  if (label) label.textContent = text || "Выберите дату и время";
  trigger.classList.toggle("is-empty", !text);
}

function enhanceDateTimeInputs() {
  // Remove stale portals from previous implementations
  if (!NeoHubDTP.isOpen()) {
    document
      .querySelectorAll("body > .dtp-backdrop, body > .dtp-modal")
      .forEach((el) => {
        if (!el.closest(".dtp-overlay")) el.remove();
      });
  }

  document.querySelectorAll("form").forEach((form) => {
    const byName = {};
    form
      .querySelectorAll(
        "input.neohub-datetime, input[name='deadline'], input[name='unlock_at']"
      )
      .forEach((input) => {
        if (
          !input.classList.contains("neohub-datetime") &&
          input.type !== "hidden"
        ) {
          if (input.name !== "deadline" && input.name !== "unlock_at") return;
        }
        const key = input.name || "";
        if (!key) return;
        if (!byName[key]) byName[key] = [];
        byName[key].push(input);
      });
    Object.keys(byName).forEach((name) => {
      const list = byName[name];
      if (list.length < 2) return;
      list.slice(0, -1).forEach((extra) => {
        const root = extra.closest("[data-dtp-root]");
        if (root) root.remove();
        else extra.remove();
      });
    });
  });

  document
    .querySelectorAll("input.neohub-datetime:not([data-dtp-ready])")
    .forEach((input) => {
      if (input.closest("[data-dtp-root]")) {
        input.dataset.dtpReady = "1";
        return;
      }
      mountDateTimePicker(input);
    });

  document.querySelectorAll("[data-dtp-root]").forEach((root) => {
    root.querySelectorAll(".dtp-trigger").forEach((el, i) => {
      if (i > 0) el.remove();
    });
    // Strip leftover Alpine modal markup if any
    root
      .querySelectorAll(".dtp-backdrop, .dtp-modal, [x-ref='backdrop'], [x-ref='modal']")
      .forEach((el) => el.remove());
  });
}

function mountDateTimePicker(input) {
  if (!input || input.dataset.dtpReady === "1") return;
  if (input.closest("[data-dtp-root]")) {
    input.dataset.dtpReady = "1";
    return;
  }
  input.dataset.dtpReady = "1";
  input.classList.add("neohub-datetime");
  input.setAttribute("autocomplete", "off");
  input.removeAttribute("readonly");
  input.type = "hidden";
  if (input.hasAttribute("required")) {
    input.dataset.dtpRequired = "1";
    input.removeAttribute("required");
  }

  const wrap = document.createElement("div");
  wrap.className = "dtp-root";
  wrap.setAttribute("data-dtp-root", "1");

  if (!input.parentNode) return;
  input.parentNode.insertBefore(wrap, input);
  wrap.appendChild(input);

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "input dtp-trigger";
  trigger.innerHTML = '<span data-dtp-label></span>';
  wrap.appendChild(trigger);
  updateDateTimeTrigger(trigger, input);

  trigger.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (NeoHubDTP.isOpen() && NeoHubDTP.input === input) {
      NeoHubDTP.close();
      return;
    }
    NeoHubDTP.open(input, trigger);
  });
}

let __dtpEnhanceTimer = null;
function scheduleEnhanceDateTimeInputs() {
  enhanceDateTimeInputs();
  if (__dtpEnhanceTimer) clearTimeout(__dtpEnhanceTimer);
  __dtpEnhanceTimer = setTimeout(() => enhanceDateTimeInputs(), 80);
}

function closeAllDateTimePickers() {
  NeoHubDTP.closeAll();
}

document.addEventListener("alpine:init", () => {
  window.Alpine.data("dropzone", dropzoneComponent);
  window.Alpine.data("appShell", appShell);
  window.Alpine.data("creditExam", creditExam);
  window.Alpine.data("studentCreateForm", studentCreateForm);
  window.Alpine.data("listFilter", listFilter);
  window.Alpine.data("bulkAssign", bulkAssign);
  window.Alpine.data("draftSubmit", draftSubmit);
  window.Alpine.data("assignmentsLive", assignmentsLive);
  window.Alpine.data("deadlineCountdown", deadlineCountdown);
  window.Alpine.data("dateTimePicker", dateTimePicker);
});

window.dropzone = dropzoneComponent;
window.appShell = appShell;
window.creditExam = creditExam;
window.studentCreateForm = studentCreateForm;
window.listFilter = listFilter;
window.bulkAssign = bulkAssign;
window.draftSubmit = draftSubmit;
window.assignmentsLive = assignmentsLive;
window.deadlineCountdown = deadlineCountdown;
window.dateTimePicker = dateTimePicker;
window.NeoHubDTP = NeoHubDTP;
window.enhanceDateTimeInputs = enhanceDateTimeInputs;
window.scheduleEnhanceDateTimeInputs = scheduleEnhanceDateTimeInputs;

document.addEventListener("htmx:afterSwap", () => scheduleEnhanceDateTimeInputs());
document.addEventListener("htmx:afterSettle", () => scheduleEnhanceDateTimeInputs());
document.addEventListener("alpine:initialized", () => scheduleEnhanceDateTimeInputs());

document.addEventListener(
  "submit",
  (event) => {
    const form = event.target;
    if (!form || form.tagName !== "FORM") return;
    const missing = form.querySelector(
      "input.neohub-datetime[data-dtp-required='1']"
    );
    if (missing && !(missing.value || "").trim()) {
      event.preventDefault();
      event.stopPropagation();
      const root = missing.closest("[data-dtp-root]");
      const trigger = root && root.querySelector(".dtp-trigger");
      if (trigger) NeoHubDTP.open(missing, trigger);
      window.alert("Выберите дату и время.");
    }
  },
  true
);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && NeoHubDTP.isOpen()) {
    NeoHubDTP.close();
  }
});

document.addEventListener(
  "click",
  (event) => {
    if (
      event.target.closest &&
      event.target.closest(".teacher-assignment-summary, .teacher-material-row")
    ) {
      scheduleEnhanceDateTimeInputs();
    }
  },
  true
);

if (typeof MutationObserver !== "undefined") {
  let obsTimer = null;
  const dtpObserver = new MutationObserver((mutations) => {
    let needed = false;
    for (const m of mutations) {
      if (!m.addedNodes || !m.addedNodes.length) continue;
      m.addedNodes.forEach((node) => {
        if (node.nodeType !== 1) return;
        if (node.closest && node.closest("[data-dtp-root], .dtp-overlay")) return;
        if (
          node.matches &&
          node.matches("[data-dtp-root], .dtp-trigger, .dtp-overlay")
        ) {
          return;
        }
        if (
          (node.matches &&
            node.matches("input.neohub-datetime:not([data-dtp-ready])")) ||
          (node.querySelector &&
            node.querySelector("input.neohub-datetime:not([data-dtp-ready])"))
        ) {
          needed = true;
        }
      });
    }
    if (!needed) return;
    if (obsTimer) clearTimeout(obsTimer);
    obsTimer = setTimeout(() => scheduleEnhanceDateTimeInputs(), 50);
  });
  const startObs = () => {
    if (!document.body) return;
    dtpObserver.observe(document.body, { childList: true, subtree: true });
  };
  if (document.body) startObs();
  else document.addEventListener("DOMContentLoaded", startObs);
}

(function bindConfirmFormsEarly() {
  if (window.__neohubConfirmBound) return;
  window.__neohubConfirmBound = true;

  document.addEventListener(
    "submit",
    (event) => {
      const form = event.target;
      if (!form || form.tagName !== "FORM") return;
      if (!form.hasAttribute("data-confirm")) return;
      if (form.getAttribute("data-confirm-ok") === "1") {
        form.removeAttribute("data-confirm-ok");
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      if (typeof event.stopImmediatePropagation === "function") {
        event.stopImmediatePropagation();
      }
      const shell = window.__neohub;
      if (shell && typeof shell.openConfirmFromForm === "function") {
        shell.openConfirmFromForm(form);
        return;
      }
      const message = form.getAttribute("data-confirm-message") || "Подтвердите действие.";
      const requireLogin = (form.getAttribute("data-confirm-login") || "").trim();
      if (requireLogin) {
        const typed = window.prompt(message + "\n\nВведите логин: " + requireLogin);
        if (typed !== requireLogin) return;
        let input = form.querySelector('input[name="confirm_username"]');
        if (!input) {
          input = document.createElement("input");
          input.type = "hidden";
          input.name = "confirm_username";
          form.appendChild(input);
        }
        input.value = typed;
      } else if (!window.confirm(message)) {
        return;
      }
      form.setAttribute("data-confirm-ok", "1");
      HTMLFormElement.prototype.submit.call(form);
    },
    true
  );

  // Backup click handlers for modal buttons (in case Alpine @click fails)
  document.addEventListener("click", (event) => {
    const ok = event.target.closest && event.target.closest("#neohub-confirm-ok");
    if (ok) {
      if (ok.disabled) return;
      event.preventDefault();
      event.stopPropagation();
      if (window.__neohub) window.__neohub.submitConfirm();
      return;
    }
    const cancel = event.target.closest && event.target.closest("#neohub-confirm-cancel");
    if (cancel) {
      event.preventDefault();
      event.stopPropagation();
      if (window.__neohub) window.__neohub.closeConfirm();
    }
  });
})();

(function bindActivationCodeSegments() {
  function onlyCodeChars(value) {
    return String(value || "")
      .toUpperCase()
      .replace(/[^A-Z0-9]/g);
  }

  function syncHidden(form) {
    const hidden = form.querySelector("#activation-code-value");
    if (!hidden) return;
    const parts = Array.from(form.querySelectorAll(".activation-seg")).map((el) =>
      onlyCodeChars(el.value).slice(0, 4)
    );
    while (parts.length < 4) parts.push("");
    const raw = parts.join("");
    if (!raw) {
      hidden.value = "";
      return;
    }
    const chunks = [];
    for (let i = 0; i < raw.length && i < 16; i += 4) {
      chunks.push(raw.slice(i, i + 4));
    }
    hidden.value = chunks.join("-");
  }

  function bindForm(form) {
    if (!form || form.dataset.activationReady === "1") return;
    const segs = Array.from(form.querySelectorAll(".activation-seg"));
    if (segs.length !== 4) return;
    form.dataset.activationReady = "1";

    segs.forEach((seg, index) => {
      seg.addEventListener("input", () => {
        const clean = onlyCodeChars(seg.value).slice(0, 4);
        seg.value = clean;
        if (clean.length >= 4 && index < segs.length - 1) {
          segs[index + 1].focus();
          segs[index + 1].select();
        }
        syncHidden(form);
      });

      seg.addEventListener("keydown", (event) => {
        if (event.key === "Backspace" && !seg.value && index > 0) {
          segs[index - 1].focus();
        }
      });

      seg.addEventListener("paste", (event) => {
        event.preventDefault();
        const clip =
          (event.clipboardData && event.clipboardData.getData("text")) || "";
        const text = onlyCodeChars(clip).slice(0, 16);
        for (let i = 0; i < 4; i += 1) {
          segs[i].value = text.slice(i * 4, i * 4 + 4);
        }
        const idx = Math.min(3, Math.max(0, Math.ceil(text.length / 4) - 1));
        segs[idx].focus();
        syncHidden(form);
      });
    });

    form.addEventListener("submit", () => {
      syncHidden(form);
    });
  }

  function scan() {
    document.querySelectorAll("#activation-form").forEach(bindForm);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scan);
  } else {
    scan();
  }
  document.addEventListener("htmx:afterSwap", scan);
})();

(function bindAuthScene() {
  function initScene(root) {
    if (!root || root.dataset.bound === "1") return;
    root.dataset.bound = "1";

    const floats = Array.from(root.querySelectorAll("[data-auth-float]"));
    const glow = root.querySelector("[data-auth-glow]");
    let targetX = 0;
    let targetY = 0;
    let curX = 0;
    let curY = 0;
    let raf = 0;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function tick() {
      curX += (targetX - curX) * 0.08;
      curY += (targetY - curY) * 0.08;
      floats.forEach((el) => {
        const depth = parseFloat(el.dataset.depth || "0.1");
        el.style.setProperty("--mx", `${curX * depth * 42}px`);
        el.style.setProperty("--my", `${curY * depth * 42}px`);
      });
      if (glow) {
        glow.style.setProperty("--gx", `${50 + curX * 18}%`);
        glow.style.setProperty("--gy", `${42 + curY * 18}%`);
      }
      raf = window.requestAnimationFrame(tick);
    }

    function onMove(event) {
      const w = window.innerWidth || 1;
      const h = window.innerHeight || 1;
      targetX = (event.clientX / w) * 2 - 1;
      targetY = (event.clientY / h) * 2 - 1;
    }

    function onLeave() {
      targetX = 0;
      targetY = 0;
    }

    if (!reduceMotion) {
      window.addEventListener("pointermove", onMove, { passive: true });
      window.addEventListener("pointerleave", onLeave);
      raf = window.requestAnimationFrame(tick);
    }
  }

  function scan() {
    document.querySelectorAll("[data-auth-scene]").forEach(initScene);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scan);
  } else {
    scan();
  }
})();
