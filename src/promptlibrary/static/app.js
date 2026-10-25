  function initializeHelpPage() {
    const content = document.querySelector("[data-help-content]");
    const navigation = document.querySelector("[data-help-nav]");
    if (!content || !navigation || navigation.dataset.ready) return;
    navigation.dataset.ready = "true";
    const headings = Array.from(content.querySelectorAll("h2"));
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    for (const [index, heading] of headings.entries()) {
      const slug = heading.textContent.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || `section-${index + 1}`;
      heading.id = slug;
      heading.tabIndex = -1;
      const link = document.createElement("a");
      link.href = `#${slug}`;
      link.textContent = heading.textContent;
      link.addEventListener("click", (event) => {
        event.preventDefault();
        heading.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
        history.replaceState({}, "", `#${slug}`);
        heading.focus({ preventScroll: true });
      });
      navigation.append(link);
    }
    if (!headings.length) navigation.hidden = true;
  }

  function initializeSettingsTabs() {
    for (const group of document.querySelectorAll("[data-settings-tabs]")) {
      const tabs = Array.from(group.querySelectorAll("[data-settings-tab]"));
      if (!tabs.length || group.dataset.ready) continue;
      group.dataset.ready = "true";
      const activate = (tab, focus = false) => {
        for (const candidate of tabs) {
          const selected = candidate === tab;
          candidate.setAttribute("aria-selected", String(selected));
          candidate.classList.toggle("is-active", selected);
          candidate.tabIndex = selected ? 0 : -1;
          const panel = group.querySelector(`#${CSS.escape(candidate.dataset.settingsTab || "")}`);
          if (panel) panel.hidden = !selected;
        }
        if (focus) tab.focus();
      };
      tabs.forEach((tab, index) => {
        tab.addEventListener("click", () => activate(tab));
        tab.addEventListener("keydown", (event) => {
          if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          const targetIndex = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
          activate(tabs[targetIndex], true);
        });
      });
      const selected = tabs.find((tab) => tab.getAttribute("aria-selected") === "true") || tabs[0];
      activate(selected);
    }
  }


"use strict";

(() => {
  let navigationController = null;
  let navigationSequence = 0;
  let mutationPending = false;
  let queuedSubmission = null;
  let currentPageUrl = window.location.href;
  let searchTimer = null;
  let previewTimer = null;
  let previewSequence = 0;
  let toastTimer = null;

  const root = document.documentElement;
  const dialog = document.getElementById("confirm-dialog");

  function readPreference(name, fallback) {
    try { return localStorage.getItem(name) || fallback; }
    catch { return fallback; }
  }

  function writePreference(name, value) {
    try { localStorage.setItem(name, value); }
    catch { /* Private browser modes may disable storage; the controls still work. */ }
  }

  function initializeTagEditors() {
    for (const editor of document.querySelectorAll("[data-tag-editor]")) {
      if (editor.dataset.ready) continue;
      editor.dataset.ready = "true";
      const input = editor.querySelector("input[name='tags']");
      if (!(input instanceof HTMLInputElement)) continue;
      const initial = input.value.split(",").map((tag) => tag.trim()).filter(Boolean);
      input.value = "";
      const tags = [];
      const render = () => {
        editor.querySelectorAll(".tag-chip").forEach((chip) => chip.remove());
        for (const tag of tags) {
          const chip = document.createElement("span");
          chip.className = "tag-chip";
          chip.textContent = tag;
          const remove = document.createElement("button");
          remove.type = "button";
          remove.textContent = "×";
          remove.setAttribute("aria-label", `Remove tag ${tag}`);
          remove.addEventListener("click", () => {
            tags.splice(tags.indexOf(tag), 1);
            render();
          });
          chip.append(remove);
          editor.insertBefore(chip, input);
        }
      };
      const add = (value) => {
        const tag = value.trim();
        if (tag && !tags.includes(tag) && tags.length < 100) tags.push(tag);
        input.value = "";
        render();
      };
      initial.forEach(add);
      input.addEventListener("keydown", (event) => {
        if (event.key === "," || event.key === "Enter") {
          event.preventDefault();
          add(input.value);
        } else if (event.key === "Backspace" && !input.value && tags.length) {
          tags.pop();
          render();
        }
      });
      input.form?.addEventListener("submit", () => { input.value = tags.join(", "); });
      render();
    }
  }

  function openModal(config) {
    const modal = document.getElementById("app-modal");
    const content = document.getElementById("app-modal-content");
    if (!(modal instanceof HTMLDialogElement) || !content || modal.open) return Promise.resolve(null);
    content.replaceChildren();
    const title = document.createElement("h2");
    title.id = "app-modal-title";
    title.textContent = config.title || "Dialog";
    content.append(title);
    if (config.body) {
      const body = document.createElement("p");
      body.textContent = config.body;
      content.append(body);
    }
    const actions = document.createElement("div");
    actions.className = "actions";
    for (const action of config.actions || [{ label: "Close", value: "close" }]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = action.label;
      button.className = action.primary ? "primary" : "";
      button.addEventListener("click", () => { modal.close(action.value); });
      actions.append(button);
    }
    content.append(actions);
    modal.showModal();
    return new Promise((resolve) => modal.addEventListener("close", () => resolve(modal.returnValue), { once: true }));
  }

  async function createInlineMetadata(kind, trigger) {
    const modal = document.getElementById("app-modal");
    const content = document.getElementById("app-modal-content");
    if (!(modal instanceof HTMLDialogElement) || !content || modal.open) return;
    const title = kind[0].toUpperCase() + kind.slice(1);
    content.innerHTML = `<h2 id="app-modal-title">Create ${title}</h2><form data-inline-form><label>Name<input name="name" required maxlength="200" autofocus></label><div class="actions"><button class="primary" type="submit">Create ${title}</button><button type="button" data-modal-cancel>Cancel</button></div></form>`;
    modal.showModal();
    const form = content.querySelector("form");
    const close = () => modal.close("cancel");
    content.querySelector("[data-modal-cancel]")?.addEventListener("click", close);
    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const name = new FormData(form).get("name");
      if (typeof name !== "string" || !name.trim()) return;
      const endpoint = { category: "/api/categories", project: "/api/projects", status: "/api/statuses" }[kind];
      if (!endpoint) { showMessage("Unsupported metadata type.", true); return; }
      const response = await fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: name.trim() }) });
      if (!response.ok) { showMessage(await errorMessage(response), true); return; }
      const created = await response.json();
      const select = trigger.closest("label")?.querySelector("select");
      if (select instanceof HTMLSelectElement) {
        const option = new Option(created.name, created.id || created.key, true, true);
        select.add(option);
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
      modal.close("created");
      showMessage(`${title} created.`);
    });
  }

  function initializeMarkdownEditors() {
    for (const editor of document.querySelectorAll("[data-markdown-editor]")) {
      if (editor.dataset.ready) continue;
      editor.dataset.ready = "true";
      const textarea = editor.querySelector("textarea");
      if (!(textarea instanceof HTMLTextAreaElement)) continue;
      editor.querySelectorAll("[data-md-action]").forEach((button) => button.addEventListener("click", () => {
        const action = button.dataset.mdAction;
        const wrappers = { bold: ["**", "**"], italic: ["*", "*"], code: ["`", "`"], heading: ["## ", ""], list: ["- ", ""], quote: ["> ", ""] };
        const wrapper = wrappers[action];
        if (!wrapper) return;
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const selected = textarea.value.slice(start, end) || "text";
        const replacement = `${wrapper[0]}${selected}${wrapper[1]}`;
        textarea.setRangeText(replacement, start, end, "select");
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
        textarea.focus();
      }));
    }
  }

  function prepareProjectDialogs() {
    for (const dialog of document.querySelectorAll(".project-dialog")) {
      if (dialog.dataset.ready) continue;
      dialog.dataset.ready = "true";
      dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
      dialog.querySelector("[data-project-close]")?.addEventListener("click", () => dialog.close());
    }
  }

  window.promptLibraryModal = openModal;

  const preferredTheme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  root.dataset.theme = readPreference("promptlibrary-theme", preferredTheme) === "dark" ? "dark" : "light";
  root.dataset.sidebar = readPreference("promptlibrary-sidebar", window.innerWidth < 760 ? "collapsed" : "expanded") === "collapsed" ? "collapsed" : "expanded";

  function showMessage(message, error = false) {
    const toast = document.getElementById("toast");
    const text = document.getElementById("toast-message");
    if (!toast || !text) return;
    clearTimeout(toastTimer);
    toast.classList.toggle("error", error);
    text.setAttribute("role", error ? "alert" : "status");
    text.textContent = message;
    toast.hidden = false;
    if (!error) toastTimer = setTimeout(() => { toast.hidden = true; }, 6000);
  }

  async function confirmAction(message, label = "Confirm") {
    if (!(dialog instanceof HTMLDialogElement) || dialog.open) return false;
    document.getElementById("confirm-message").textContent = message;
    document.getElementById("confirm-accept").textContent = label;
    dialog.returnValue = "cancel";
    return new Promise((resolve) => {
      dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), { once: true });
      dialog.showModal();
    });
  }

  async function canLeave(sourceForm = null) {
    const dirty = Array.from(document.querySelectorAll("form[data-dirty='true']"))
      .some((form) => form !== sourceForm);
    return !dirty || await confirmAction("Discard unsaved changes on this page?", "Discard changes");
  }

  function updateRemoteFields() {
    const selector = document.querySelector("[data-remote-provider]");
    if (!(selector instanceof HTMLSelectElement)) return;
    for (const fieldset of document.querySelectorAll("fieldset[data-provider]")) {
      const active = fieldset.dataset.provider === selector.value;
      fieldset.hidden = !active;
      fieldset.disabled = !active;
    }
  }

  function preparePage() {
    const collapsed = root.dataset.sidebar === "collapsed";
    const toggle = document.getElementById("sidebar-toggle");
    if (toggle) {
      toggle.setAttribute("aria-expanded", String(!collapsed));
      toggle.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
      toggle.title = collapsed ? "Expand sidebar" : "Collapse sidebar";
    }
    const themeToggle = document.getElementById("theme-toggle");
    if (themeToggle) themeToggle.setAttribute("aria-pressed", String(root.dataset.theme === "dark"));
    updateRemoteFields();
    initializeTagEditors();
    initializeMarkdownEditors();
    prepareProjectDialogs();
    initializeHelpPage();
    initializeSettingsTabs();
    for (const source of document.querySelectorAll("[data-prompt-source]")) {
      const form = source.closest("form");
      const body = form.querySelector("textarea[name='body']");
      const linked = form.querySelector("input[name='link_prompt']");
      const selected = source.selectedOptions[0];
      body.disabled = Boolean(source.value);
      linked.disabled = !source.value;
      if (source.value) linked.checked = true;
      if (source.value && selected?.dataset.body !== undefined) body.value = selected.dataset.body;
    }
  }

  async function errorMessage(response) {
    const type = response.headers.get("Content-Type") || "";
    if (type.includes("application/json")) {
      const body = await response.json();
      if (typeof body.error === "string") return body.error;
      if (typeof body.detail === "string") return body.detail;
      if (Array.isArray(body.detail)) return body.detail.map((item) => item.msg || "Invalid input").join("; ");
      return `Request failed (${response.status}). Your unsaved edits have been kept.`;
    }
    const text = await response.text();
    if (!text.startsWith("<!") && text.length < 1000) return text;
    return `Request failed (${response.status}). Your unsaved edits have been kept.`;
  }

  async function navigate(url, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    if (mutationPending) return false;
    if (options.guard !== false && !await canLeave(options.sourceForm || null)) return false;
    if (mutationPending) return false;
    const target = new URL(url, window.location.origin);
    if (target.origin !== window.location.origin) return false;

    if (navigationController) navigationController.abort();
    const controller = new AbortController();
    navigationController = controller;
    const sequence = ++navigationSequence;
    const changing = method !== "GET" && method !== "HEAD";
    mutationPending = changing;
    const oldApp = document.getElementById("app");
    const oldMain = document.getElementById("main");
    const oldDetail = document.getElementById("detail-panel");
    const oldList = document.getElementById("prompt-list");
    const mainScroll = oldMain?.scrollTop || 0;
    const detailScroll = oldDetail?.scrollTop || 0;
    const listScroll = oldList?.scrollTop || 0;
    const openDetails = Array.from(document.querySelectorAll("#app details[id][open]")).map((element) => element.id);
    const oldUrl = new URL(currentPageUrl);
    oldApp?.setAttribute("aria-busy", "true");
    if (changing && oldApp) oldApp.inert = true;

    let focusState = null;
    if (options.sourceForm?.hasAttribute("data-search")) {
      const focused = document.activeElement;
      if (focused instanceof HTMLInputElement && options.sourceForm.contains(focused)) {
        focusState = { name: focused.name, start: focused.selectionStart, end: focused.selectionEnd };
      }
    }

    try {
      const response = await fetch(target.href, {
        method, body: options.body || undefined, credentials: "same-origin", cache: "no-store",
        headers: { "X-Fragment": "1", "Accept": "text/html" }, signal: controller.signal,
      });
      if (!response.ok) throw new Error(await errorMessage(response));
      const text = await response.text();
      if (sequence !== navigationSequence) return false;
      const parsed = new DOMParser().parseFromString(text, "text/html");
      const nextApp = parsed.getElementById("app");
      if (!nextApp) throw new Error("The server returned an unexpected page. Your edits have been kept.");
      const canonical = new URL(response.headers.get("X-Page-URL") || target.href, window.location.origin);
      if (canonical.origin !== window.location.origin) throw new Error("The server returned an invalid navigation target.");
      oldApp.replaceWith(nextApp);
      document.title = nextApp.dataset.title || "PromptLibrary";
      if (options.replace) history.replaceState({}, "", canonical.href);
      else if (canonical.href !== currentPageUrl) history.pushState({}, "", canonical.href);
      currentPageUrl = canonical.href;
      preparePage();

      if (oldUrl.pathname === canonical.pathname) {
        for (const id of openDetails) {
          const detail = document.getElementById(id);
          if (detail instanceof HTMLDetailsElement) detail.open = true;
        }
        const main = document.getElementById("main");
        const detail = document.getElementById("detail-panel");
        if (main) main.scrollTop = mainScroll;
        if (detail) detail.scrollTop = detailScroll;
      }
      if (oldUrl.search === canonical.search) {
        const list = document.getElementById("prompt-list");
        if (list) list.scrollTop = listScroll;
      }
      if (focusState) {
        const input = document.querySelector(`form[data-search] input[name="${CSS.escape(focusState.name)}"]`);
        if (input instanceof HTMLInputElement) {
          input.focus({ preventScroll: true });
          if (focusState.start !== null) input.setSelectionRange(focusState.start, focusState.end);
        }
      } else {
        const focusTarget = nextApp.querySelector("[autofocus]") || nextApp.querySelector("#detail-panel h1") || nextApp.querySelector("#main h1");
        if (focusTarget instanceof HTMLElement) {
          if (!focusTarget.hasAttribute("tabindex") && !focusTarget.matches("input,textarea,select,button")) focusTarget.tabIndex = -1;
          focusTarget.focus({ preventScroll: true });
        }
      }
      const message = response.headers.get("X-Message");
      if (message) showMessage(message);
      return true;
    } catch (error) {
      if (error.name !== "AbortError") showMessage(error.message || "The request failed. Your edits have been kept.", true);
      return false;
    } finally {
      if (sequence === navigationSequence) {
        mutationPending = false;
        const currentApp = document.getElementById("app");
        currentApp?.removeAttribute("aria-busy");
        if (currentApp) currentApp.inert = false;
        if (!mutationPending && queuedSubmission) {
          const queued = queuedSubmission;
          queuedSubmission = null;
          queueMicrotask(() => { void replayQueuedSubmission(queued); });
        }
      }
    }
  }

  async function replayQueuedSubmission(queued) {
    const url = new URL(queued.action, window.location.origin);
    if (queued.method === "GET") {
      url.search = "";
      for (const [key, value] of queued.data) if (typeof value === "string" && value !== "") url.searchParams.append(key, value);
      await navigate(url.href, { guard: false });
    } else {
      await navigate(url.href, { method: queued.method, body: queued.data, guard: false });
    }
  }

  async function submitForm(form, submitter = null) {
    if (mutationPending) {
      if (!form.reportValidity()) return;
      const data = new FormData(form);
      if (submitter?.name) data.append(submitter.name, submitter.value);
      queuedSubmission = { action: form.action, method: (form.method || "GET").toUpperCase(), data };
      return;
    }
    if (!form.reportValidity()) return;
    if (!await canLeave(form)) {
      if (form.hasAttribute("data-search")) form.reset();
      return;
    }
    if (form.dataset.confirm && !await confirmAction(form.dataset.confirm, form.dataset.confirmLabel || "Confirm")) return;
    if (mutationPending) return;
    const method = (form.method || "GET").toUpperCase();
    const data = new FormData(form);
    if (submitter?.name) data.append(submitter.name, submitter.value);
    const url = new URL(form.action, window.location.origin);
    if (method === "GET") {
      url.search = "";
      for (const [key, value] of data) {
        if (typeof value === "string" && value !== "") url.searchParams.append(key, value);
      }
      await navigate(url.href, { sourceForm: form, guard: false });
    } else {
      await navigate(url.href, { method, body: data, sourceForm: form, guard: false });
    }
  }

  async function copyText(targetId) {
    const source = document.getElementById(targetId);
    if (!source) return;
    const text = source instanceof HTMLTextAreaElement || source instanceof HTMLInputElement ? source.value : source.textContent;
    try {
      if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text);
      else {
        const temporary = document.createElement("textarea");
        temporary.value = text;
        temporary.className = "clipboard-fallback";
        document.body.append(temporary);
        const previous = document.activeElement;
        temporary.select();
        const copied = document.execCommand("copy");
        temporary.remove();
        if (previous instanceof HTMLElement) previous.focus({ preventScroll: true });
        if (!copied) throw new Error("Clipboard unavailable");
      }
      showMessage("Copied to clipboard.");
    } catch {
      showMessage("Clipboard access failed. Open the plain text, select it and copy it manually.", true);
    }
  }

  async function renderPreview(form) {
    const body = form.querySelector("textarea[name='body']");
    const panel = form.querySelector(".preview-panel");
    if (!(body instanceof HTMLTextAreaElement) || !panel || panel.hidden) return;
    const sequence = ++previewSequence;
    try {
      const response = await fetch("/api/preview", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: body.value }),
      });
      if (!response.ok) throw new Error(await errorMessage(response));
      const result = await response.json();
      // Only the server's escaped Markdown renderer supplies preview HTML.
      if (sequence === previewSequence && form.isConnected) panel.innerHTML = result.html;
    } catch (error) { showMessage(error.message || "Preview failed.", true); }
  }

  document.addEventListener("click", async (event) => {
    const element = event.target instanceof Element ? event.target : null;
    if (!element) return;
    const theme = element.closest("[data-theme-toggle]");
    if (theme) {
      root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
      writePreference("promptlibrary-theme", root.dataset.theme);
      preparePage();
      return;
    }
    if (element.closest("[data-sidebar-toggle]")) {
      root.dataset.sidebar = root.dataset.sidebar === "collapsed" ? "expanded" : "collapsed";
      writePreference("promptlibrary-sidebar", root.dataset.sidebar);
      preparePage();
      return;
    }
    if (element.closest("[data-dismiss-toast]")) {
      document.getElementById("toast").hidden = true;
      return;
    }
    const projectEdit = element.closest("[data-project-edit]");
    if (projectEdit) {
      const dialog = document.getElementById(`project-edit-${projectEdit.dataset.projectEdit}`);
      if (dialog instanceof HTMLDialogElement) dialog.showModal();
      return;
    }
    const inlineCreate = element.closest("[data-inline-create]");
    if (inlineCreate) { await createInlineMetadata(inlineCreate.dataset.inlineCreate, inlineCreate); return; }
    const copy = element.closest("[data-copy-target]");
    if (copy) { await copyText(copy.dataset.copyTarget); return; }
    const preview = element.closest("[data-preview]");
    if (preview) {
      const form = preview.closest("form");
      const panel = form.querySelector(".preview-panel");
      panel.hidden = !panel.hidden;
      preview.setAttribute("aria-expanded", String(!panel.hidden));
      preview.textContent = panel.hidden ? "Show Markdown preview" : "Hide Markdown preview";
      await renderPreview(form);
      return;
    }
    const link = element.closest("a[data-nav]");
    if (link instanceof HTMLAnchorElement && event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
      event.preventDefault();
      await navigate(link.href);
    }
  });

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-submit")) return;
    event.preventDefault();
    void submitForm(form, event.submitter);
  });

  document.addEventListener("input", (event) => {
    const input = event.target;
    if (!(input instanceof HTMLElement)) return;
    const dirtyForm = input.closest("form[data-dirty-watch]");
    if (dirtyForm) dirtyForm.dataset.dirty = "true";
    const searchForm = input.closest("form[data-search]");
    if (searchForm && input.matches("input[type='search']")) {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => { if (searchForm.isConnected) void submitForm(searchForm); }, 300);
    }
    const helpSearch = input.closest("[data-help-search]");
    if (helpSearch) {
      const query = input.value.trim().toLowerCase();
      const content = document.querySelector("[data-help-content]");
      if (content) {
        for (const child of content.children) {
          const searchable = child.textContent.toLowerCase();
          child.hidden = Boolean(query) && !searchable.includes(query);
        }
      }
    }
    const editor = input.closest("form[data-editor]");
    if (editor && input.matches("textarea[name='body']")) {
      clearTimeout(previewTimer);
      previewTimer = setTimeout(() => { if (editor.isConnected) void renderPreview(editor); }, 300);
    }
  });

  document.addEventListener("change", (event) => {
    const input = event.target;
    if (!(input instanceof HTMLElement)) return;
    const dirtyForm = input.closest("form[data-dirty-watch]");
    if (dirtyForm) dirtyForm.dataset.dirty = "true";
    if (input.matches("[data-remote-provider]")) updateRemoteFields();
    if (input.matches("[data-detach-toggle]")) {
      const body = input.closest("form").querySelector("textarea[name='body']");
      if (body) body.disabled = !input.checked;
    }
    if (input.matches("[data-prompt-source]")) {
      const form = input.closest("form");
      const body = form.querySelector("textarea[name='body']");
      const title = form.querySelector("input[name='title']");
      const linked = form.querySelector("input[name='link_prompt']");
      const selected = input.selectedOptions[0];
      body.disabled = Boolean(input.value);
      linked.disabled = !input.value;
      linked.checked = Boolean(input.value);
      if (input.value) body.value = selected?.dataset.body || "";
      if (input.value && (!title.value || title.dataset.autoTitle === title.value)) {
        title.value = selected.textContent;
        title.dataset.autoTitle = title.value;
      }
    }
    const searchForm = input.closest("form[data-search]");
    if (searchForm && input.matches("select,input[type='checkbox']")) void submitForm(searchForm);
  });

  window.addEventListener("popstate", async () => {
    if (mutationPending || !await canLeave()) {
      history.pushState({}, "", currentPageUrl);
      return;
    }
    const loaded = await navigate(window.location.href, { replace: true, guard: false });
    if (!loaded) history.replaceState({}, "", currentPageUrl);
  });

  window.addEventListener("beforeunload", (event) => {
    if (mutationPending || document.querySelector("form[data-dirty='true']")) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      void navigator.serviceWorker.register("/static/sw.js").catch(() => {});
    });
  }

  preparePage();
})();
