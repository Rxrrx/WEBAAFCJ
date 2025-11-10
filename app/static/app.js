(function () {
  const DOWNLOAD_SELECTOR = "[data-download-url]";
  const VIEW_SELECTOR = "[data-view-url]";
  const LIBRARY_VIEW_SELECTOR = "[data-library-view-toggle]";
  const DELETE_SELECTOR =
    "form[data-action='delete-doc'], form[data-action='delete-category'], form[data-action='delete-subcategory'], form[data-action='delete-post']";
  const STORAGE_KEYS = {
    libraryView: "library:view",
  };

  let modal;
  let iframe;
  let modalTitle;

  function ensureModal() {
    if (modal) return modal;
    modal = document.createElement("div");
    modal.className = "viewer-modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.innerHTML = [
      '<div class="viewer-modal__backdrop" data-modal-close></div>',
      '<div class="viewer-modal__dialog">',
      '  <header class="viewer-modal__header">',
      '    <h3 class="viewer-modal__title"></h3>',
      '    <button class="viewer-modal__close" type="button" aria-label="Cerrar visor" data-modal-close>&times;</button>',
      "  </header>",
      '  <div class="viewer-modal__body">',
      '    <iframe title="Visor de documento" src="about:blank"></iframe>',
      "  </div>",
      "</div>",
    ].join("");

    document.body.appendChild(modal);
    iframe = modal.querySelector("iframe");
    modalTitle = modal.querySelector(".viewer-modal__title");

    modal.addEventListener("click", (event) => {
      if (event.target.matches("[data-modal-close]")) {
        closeModal();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && modal.classList.contains("is-open")) {
        closeModal();
      }
    });

    return modal;
  }

  function openModal(url, title) {
    ensureModal();
    modal.classList.add("is-open");
    document.body.classList.add("viewer-modal-open");
    modalTitle.textContent = title || "Documento";
    iframe.src = url;
    iframe.focus({ preventScroll: true });
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.remove("is-open");
    document.body.classList.remove("viewer-modal-open");
    iframe.src = "about:blank";
  }

  async function handleDownload(trigger) {
    const url = trigger.dataset.downloadUrl || trigger.getAttribute("href");
    if (!url) {
      return;
    }

    const filename = trigger.dataset.filename || "documento";
    trigger.setAttribute("aria-disabled", "true");
    trigger.classList.add("is-loading");

    try {
      const response = await fetch(url, { credentials: "same-origin" });
      if (!response.ok) {
        throw new Error("Error HTTP " + response.status);
      }
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 0);
    } catch (error) {
      console.error("No se pudo descargar el archivo:", error);
      window.alert("No se pudo descargar el archivo. Intenta mas tarde.");
    } finally {
      trigger.removeAttribute("aria-disabled");
      trigger.classList.remove("is-loading");
    }
  }

  function initDownloads(root = document) {
    const shouldIntercept = document.body?.dataset.directUpload !== "true";
    if (!shouldIntercept) {
      return;
    }

    root.querySelectorAll(DOWNLOAD_SELECTOR).forEach((element) => {
      element.addEventListener("click", (event) => {
        event.preventDefault();
        handleDownload(element);
      });
    });
  }

  function initViewers(root = document) {
    root.querySelectorAll(VIEW_SELECTOR).forEach((element) => {
      element.addEventListener("click", (event) => {
        event.preventDefault();
        const url = element.dataset.viewUrl || element.getAttribute("href");
        if (!url) return;
        openModal(url, element.dataset.filename || element.textContent.trim());
      });
    });
  }

  function initLibraryViewToggle(root = document) {
    const stage = root.querySelector("[data-library-stage]");
    const toggle = root.querySelector(LIBRARY_VIEW_SELECTOR);
    if (!stage || !toggle) return;

    const buttons = Array.from(toggle.querySelectorAll("[data-view]"));
    if (!buttons.length) return;

    const applyView = (view, persist = false) => {
      stage.dataset.view = view;
      buttons.forEach((button) => {
        const isActive = button.dataset.view === view;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
      if (persist) {
        try {
          window.localStorage.setItem(STORAGE_KEYS.libraryView, view);
        } catch (error) {
          console.warn("No se pudo guardar la vista preferida", error);
        }
      }
    };

    const storedView = (() => {
      try {
        return window.localStorage.getItem(STORAGE_KEYS.libraryView);
      } catch {
        return null;
      }
    })();
    if (storedView && storedView !== stage.dataset.view) {
      applyView(storedView);
    }

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        const view = button.dataset.view || "list";
        if (view === stage.dataset.view) {
          return;
        }
        applyView(view, true);
      });
    });
  }

  function initLibrarySorter(root = document) {
    const stage = root.querySelector("[data-library-stage]");
    const control = root.querySelector("[data-library-sort]");
    if (!stage || !control) return;

    const collections = Array.from(
      stage.querySelectorAll("[data-doc-collection]")
    );
    if (!collections.length) return;

    const getItems = (node) =>
      Array.from(node.querySelectorAll("[data-doc-card]"));

    const snapshots = collections.map((node) => ({
      node,
      adminOrder: getItems(node),
    }));

    const getTimestamp = (element) => {
      if (!element) return 0;
      if (element.dataset.uploadedTs) {
        return Number(element.dataset.uploadedTs) || 0;
      }
      const raw = element.dataset.uploadedAt;
      const value = raw ? Date.parse(raw) : NaN;
      const normalized = Number.isNaN(value) ? 0 : value;
      element.dataset.uploadedTs = String(normalized);
      return normalized;
    };

    const reorder = (mode) => {
      const normalized = mode || "admin";
      stage.dataset.sort = normalized;
      if (normalized === "admin") {
        snapshots.forEach(({ node, adminOrder }) => {
          adminOrder.forEach((item) => node.appendChild(item));
        });
        return;
      }
      const factor = normalized === "newest" ? -1 : 1;
      snapshots.forEach(({ node }) => {
        const items = getItems(node);
        items
          .sort((a, b) => {
            const diff = getTimestamp(a) - getTimestamp(b);
            if (diff === 0) return 0;
            return diff * factor;
          })
          .forEach((item) => node.appendChild(item));
      });
    };

    control.addEventListener("change", () => {
      reorder(control.value);
    });

    reorder(control.value);
  }

  function initDeletes(root = document) {
    root.querySelectorAll(DELETE_SELECTOR).forEach((form) => {
      form.addEventListener("submit", (event) => {
        const isCategory = form.dataset.action === "delete-category";
        const isSubcategory = form.dataset.action === "delete-subcategory";
        const isPost = form.dataset.action === "delete-post";
        const itemName =
          form.dataset.name || form.dataset.filename || "este elemento";
        const message =
          form.dataset.confirm ||
          (isCategory
            ? `Eliminar la categoria "${itemName}" y todos sus documentos asociados?`
            : isSubcategory
            ? `Eliminar la subcategoria "${itemName}" y todos sus documentos?`
            : isPost
            ? `Eliminar la publicacion de manera permanente?`
            : `Eliminar "${itemName}" de manera permanente?`);
        if (!window.confirm(message)) {
          event.preventDefault();
        }
      });
    });
  }

  function initWallReplies(root = document) {
    root.querySelectorAll("[data-toggle-replies]").forEach((button) => {
      const card = button.closest("[data-post]");
      if (!card) return;
      const block = card.querySelector("[data-replies]");
      if (!block) {
        button.hidden = true;
        return;
      }
      const extraReplies = block.querySelectorAll(".reply").length;
      const total = 1 + extraReplies; // first reply is always visible
      const updateLabel = () => {
        const expanded = button.getAttribute("data-expanded") === "true";
        button.textContent = expanded
          ? "Ocultar respuestas"
          : `Ver todas las respuestas (${total})`;
      };
      updateLabel();
      button.addEventListener("click", () => {
        const expanded = button.getAttribute("data-expanded") === "true";
        block.hidden = expanded;
        button.setAttribute("data-expanded", String(!expanded));
        updateLabel();
      });
    });
  }

  class ReorderBlock {
    constructor(container) {
      this.container = container;
      this.list = container.querySelector("[data-reorder-list]");
      this.toggle = container.querySelector("[data-reorder-toggle]");
      this.actions = container.querySelector("[data-reorder-actions]");
      this.saveButton = container.querySelector("[data-reorder-save]");
      this.cancelButton = container.querySelector("[data-reorder-cancel]");
      this.statusNode = container.querySelector("[data-reorder-status]");
      this.hint = container.querySelector("[data-reorder-hint]");
      this.endpoint =
        container.dataset.reorderEndpoint || container.dataset.reorderUrl || "";
      this.fieldKey = container.dataset.reorderField || "items";
      this.message =
        container.dataset.reorderMessage || "Orden actualizado correctamente.";
      this.active = false;
      this.initialOrder = [];
      this.draggedItem = null;
      this.container.dataset.reorderState = "idle";
      this.container.dataset.reorderDirty = "false";

      this.toggle?.addEventListener("click", () => {
        if (this.active) {
          this.deactivate();
        } else {
          this.activate();
        }
      });
      this.saveButton?.addEventListener("click", () => this.persist());
      this.cancelButton?.addEventListener("click", () => this.cancel());
      this.container.addEventListener("reorder:refresh", () =>
        this.refreshAfterContentChange()
      );

      this.refresh();
      this.container.__reorderInstance = this;
    }

    getItems() {
      if (!this.list) return [];
      return Array.from(this.list.querySelectorAll("[data-reorder-item]"));
    }

    activate() {
      if (this.active || !this.list || !this.getItems().length) return;
      this.active = true;
      this.initialOrder = this.snapshot();
      this.container.dataset.reorderState = "active";
      this.toggle?.setAttribute("aria-expanded", "true");
      this.toggle?.classList.add("is-active");
      this.actions?.removeAttribute("hidden");
      this.hint?.removeAttribute("hidden");
      this.getItems().forEach((item) => {
        item.setAttribute("draggable", "true");
        item.classList.add("is-reorderable");
      });
      this.bindDrag();
      this.setDirty(false);
    }

    deactivate(silent = false) {
      if (!this.active && !silent) return;
      this.active = false;
      this.container.dataset.reorderState = "idle";
      this.toggle?.setAttribute("aria-expanded", "false");
      this.toggle?.classList.remove("is-active");
      this.actions?.setAttribute("hidden", "hidden");
      this.hint?.setAttribute("hidden", "hidden");
      this.unbindDrag();
      this.getItems().forEach((item) => {
        item.removeAttribute("draggable");
        item.classList.remove("is-reorderable", "is-dragging");
      });
      if (!silent) {
        this.initialOrder = [];
      }
      this.setDirty(false);
    }

    cancel() {
      if (!this.initialOrder.length || !this.list) {
        this.deactivate();
        return;
      }
      const lookup = new Map(
        this.getItems().map((item) => [parseInt(item.dataset.id, 10), item])
      );
      this.initialOrder.forEach((id) => {
        const node = lookup.get(id);
        if (node) {
          this.list.appendChild(node);
        }
      });
      this.deactivate();
    }

    snapshot() {
      return this.getItems()
        .map((item) => parseInt(item.dataset.id, 10))
        .filter((id) => Number.isInteger(id));
    }

    setDirty(isDirty) {
      this.container.dataset.reorderDirty = String(isDirty);
      if (isDirty) {
        this.saveButton?.removeAttribute("disabled");
      } else {
        this.saveButton?.setAttribute("disabled", "disabled");
      }
    }

    markDirty() {
      const current = JSON.stringify(this.snapshot());
      const initial = JSON.stringify(this.initialOrder);
      this.setDirty(current !== initial);
    }

    bindDrag() {
      if (!this.list) return;
      this.onDragStart = (event) => {
        if (!this.active) return;
        const item = event.target.closest("[data-reorder-item]");
        if (!item) return;
        this.draggedItem = item;
        item.classList.add("is-dragging");
        if (event.dataTransfer) {
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", item.dataset.id || "");
        }
      };
      this.onDragOver = (event) => {
        if (!this.active || !this.draggedItem) return;
        event.preventDefault();
        const target = event.target.closest("[data-reorder-item]");
        if (!target || target === this.draggedItem) return;
        const rect = target.getBoundingClientRect();
        const shouldInsertAfter = event.clientY > rect.top + rect.height / 2;
        if (shouldInsertAfter) {
          target.after(this.draggedItem);
        } else {
          target.before(this.draggedItem);
        }
        this.markDirty();
      };
      this.onDragEnd = () => {
        if (this.draggedItem) {
          this.draggedItem.classList.remove("is-dragging");
        }
        this.draggedItem = null;
      };
      this.list.addEventListener("dragstart", this.onDragStart);
      this.list.addEventListener("dragover", this.onDragOver);
      this.list.addEventListener("dragend", this.onDragEnd);
      this.list.addEventListener("drop", (event) => event.preventDefault());
    }

    unbindDrag() {
      if (!this.list) return;
      if (this.onDragStart) {
        this.list.removeEventListener("dragstart", this.onDragStart);
      }
      if (this.onDragOver) {
        this.list.removeEventListener("dragover", this.onDragOver);
      }
      if (this.onDragEnd) {
        this.list.removeEventListener("dragend", this.onDragEnd);
      }
      this.onDragStart = null;
      this.onDragOver = null;
      this.onDragEnd = null;
      this.draggedItem = null;
    }

    async persist() {
      if (!this.endpoint || this.container.dataset.reorderDirty !== "true") {
        return;
      }
      const payload = this.buildPayload();
      this.showStatus("Guardando cambios...", "info");
      this.setBusy(true);
      try {
        const response = await fetch(this.endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        this.initialOrder = this.snapshot();
        this.setDirty(false);
        this.showStatus(this.message, "success");
        window.setTimeout(() => this.showStatus("", "idle"), 1800);
      } catch (error) {
        console.error("No se pudo guardar el orden", error);
        this.showStatus(
          error?.message || "No se pudo guardar el nuevo orden.",
          "error"
        );
      } finally {
        this.setBusy(false);
      }
    }

    showStatus(message, state = "info") {
      if (!this.statusNode) return;
      if (!message) {
        this.statusNode.hidden = true;
        this.statusNode.textContent = "";
        this.statusNode.removeAttribute("data-state");
        return;
      }
      this.statusNode.hidden = false;
      this.statusNode.dataset.state = state;
      this.statusNode.textContent = message;
    }

    setBusy(isBusy) {
      if (isBusy) {
        this.container.setAttribute("aria-busy", "true");
      } else {
        this.container.removeAttribute("aria-busy");
      }
    }

    buildPayload() {
      const ids = this.snapshot();
      const payload = { [this.fieldKey]: ids };
      Object.entries(this.container.dataset).forEach(([key, value]) => {
        if (!key.startsWith("scope") || value === "") return;
        const normalized = key.replace(/^scope/, "");
        if (!normalized) return;
        const finalKey =
          normalized.charAt(0).toLowerCase() + normalized.slice(1);
        const numeric = Number(value);
        payload[finalKey] = Number.isNaN(numeric) ? value : numeric;
      });
      return payload;
    }

    refresh() {
      const hasItems = this.getItems().length > 0;
      if (!hasItems) {
        this.toggle?.setAttribute("disabled", "disabled");
        this.deactivate(true);
      } else {
        this.toggle?.removeAttribute("disabled");
      }
      this.setDirty(false);
    }

    refreshAfterContentChange() {
      this.initialOrder = this.snapshot();
      this.deactivate(true);
      this.refresh();
      this.showStatus("", "idle");
    }
  }

  function initReorderBlocks(root = document) {
    root.querySelectorAll("[data-reorder]").forEach((container) => {
      if (container.__reorderInstance) {
        container.__reorderInstance.refresh();
        return;
      }
      new ReorderBlock(container);
    });
  }

  function initDocumentOrganizer(root = document) {
    const card = root.querySelector("[data-document-organizer]");
    if (!card) return;

    const config = (() => {
      try {
        return JSON.parse(card.dataset.organizerConfig || "{}");
      } catch {
        return {};
      }
    })();
    const categoryMap = (() => {
      try {
        return JSON.parse(card.dataset.organizerCategories || "[]");
      } catch {
        return [];
      }
    })();

    const categorySelect = card.querySelector("[data-organizer-category]");
    const subcategorySelect = card.querySelector("[data-organizer-subcategory]");
    const emptyState = card.querySelector("[data-organizer-empty]");
    const loader = card.querySelector("[data-organizer-loader]");
    const meta = card.querySelector("[data-organizer-meta]");
    const list = card.querySelector("[data-reorder-list]");
    const reorderContainer = card.querySelector("[data-reorder]");
    if (
      !categorySelect ||
      !subcategorySelect ||
      !emptyState ||
      !loader ||
      !list ||
      !reorderContainer
    ) {
      return;
    }

    const subcategoryLookup = new Map(
      categoryMap.map((category) => [
        String(category.id),
        category.subcategories || [],
      ])
    );
    const state = {
      categoryId: null,
      subcategoryId: null,
    };

    const setLoader = (isLoading) => {
      if (!loader) return;
      loader.hidden = !isLoading;
      loader.classList.toggle("is-visible", isLoading);
      loader.style.display = isLoading ? "flex" : "none";
      loader.setAttribute("aria-hidden", String(!isLoading));
      if (isLoading) {
        emptyState.hidden = true;
        list.innerHTML = "";
        meta.textContent = "";
        list.setAttribute("aria-busy", "true");
      } else {
        list.removeAttribute("aria-busy");
      }
    };

    const showEmptyState = (message) => {
      emptyState.textContent =
        message || "Selecciona una categoría para ver sus documentos.";
      emptyState.hidden = false;
      list.innerHTML = "";
    };

    const renderSubcategories = (categoryId) => {
      const options = categoryId
        ? subcategoryLookup.get(String(categoryId)) || []
        : [];
      subcategorySelect.innerHTML = "";
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = options.length
        ? "Documentos generales de la categoría"
        : "Sin subcategorías disponibles";
      placeholder.selected = true;
      subcategorySelect.appendChild(placeholder);
      if (!categoryId || !options.length) {
        subcategorySelect.disabled = true;
        return;
      }
      subcategorySelect.disabled = false;
      options.forEach((option) => {
        const node = document.createElement("option");
        node.value = option.id;
        node.textContent = option.name;
        subcategorySelect.appendChild(node);
      });
    };

    const applyScopeDataset = (scope = {}) => {
      if (scope.categoryId != null) {
        reorderContainer.dataset.scopeCategoryId = scope.categoryId;
      } else {
        delete reorderContainer.dataset.scopeCategoryId;
      }
      if (scope.subcategoryId != null) {
        reorderContainer.dataset.scopeSubcategoryId = scope.subcategoryId;
      } else {
        delete reorderContainer.dataset.scopeSubcategoryId;
      }
    };

    const renderDocuments = (documents) => {
      list.innerHTML = "";
      if (!documents.length) {
        showEmptyState("No hay documentos en este contenedor todavía.");
        return;
      }
      emptyState.hidden = true;
      const fragment = document.createDocumentFragment();
      documents.forEach((doc) => {
        const item = document.createElement("li");
        item.className = "organizer-item";
        item.dataset.id = doc.id;
        item.setAttribute("data-reorder-item", "true");

        const title = escapeHtml(doc.filename || "Documento sin título");
        const timestamp = doc.uploadedAt
          ? formatDateTime(doc.uploadedAt)
          : "";
        const metaParts = [];
        if (timestamp) {
          metaParts.push(`Publicado ${timestamp}`);
        }
        const badges = [];
        if (doc.categoryName) {
          badges.push(
            `<span class="badge">${escapeHtml(doc.categoryName)}</span>`
          );
        }
        if (doc.subcategoryName) {
          badges.push(
            `<span class="badge badge--soft">${escapeHtml(doc.subcategoryName)}</span>`
          );
        }

        item.innerHTML = `
          <div class="organizer-item__body">
            <p class="organizer-item__title">${title}</p>
            <p class="organizer-item__meta">${metaParts.join(" · ")}</p>
          </div>
          <div class="organizer-item__badges">${badges.join("")}</div>
          <span class="organizer-item__handle" aria-hidden="true"></span>
        `;
        fragment.appendChild(item);
      });
      list.appendChild(fragment);
      emptyState.hidden = true;
    };

    const fetchDocuments = async () => {
      if (!config.listUrl) return;
      setLoader(true);
      const url = new URL(config.listUrl, window.location.origin);
      if (state.subcategoryId) {
        url.searchParams.set("subcategory_id", state.subcategoryId);
      } else if (state.categoryId) {
        url.searchParams.set("category_id", state.categoryId);
      }
      try {
        const response = await fetch(url.toString(), {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        if (!response.ok) {
          throw new Error(`Error al obtener documentos (${response.status})`);
        }
        const payload = await response.json();
        applyScopeDataset(payload.scope);
        renderDocuments(payload.documents || []);
        if (payload.scope) {
          const total = payload.scope.count || 0;
          meta.textContent = `${payload.scope.label} · ${total} documento${
            total === 1 ? "" : "s"
          }`;
        }
      } catch (error) {
        console.error("No se pudieron cargar los documentos", error);
        showEmptyState(
          error?.message || "No se pudieron cargar los documentos."
        );
      } finally {
        setLoader(false);
        const instance = reorderContainer.__reorderInstance;
        instance?.refreshAfterContentChange();
      }
    };

    categorySelect.addEventListener("change", () => {
      const raw = categorySelect.value;
      state.categoryId = raw ? parseInt(raw, 10) : null;
      state.subcategoryId = null;
      renderSubcategories(state.categoryId);
      fetchDocuments();
    });

    subcategorySelect.addEventListener("change", () => {
      const raw = subcategorySelect.value;
      state.subcategoryId = raw ? parseInt(raw, 10) : null;
      fetchDocuments();
    });

    showEmptyState("Selecciona una categoría o subcategoría para ver sus documentos.");
    renderSubcategories(null);
    fetchDocuments();
  }

  const HTML_ESCAPE = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };
  const DATE_FORMAT =
    typeof Intl !== "undefined"
      ? new Intl.DateTimeFormat("es-CL", {
          day: "2-digit",
          month: "short",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })
      : null;

  function escapeHtml(value) {
    return value.replace(/[&<>"']/g, (char) => HTML_ESCAPE[char] || char);
  }

  function formatDateTime(value) {
    if (!value) return "";
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "";
    }
    if (DATE_FORMAT) {
      return DATE_FORMAT.format(date);
    }
    return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  }

  function formatInlineMarkdown(value) {
    let html = value;
    html = html.replace(/!\[([^\]]*?)\]\((.*?)\)/g, "$1"); // Ignora imágenes.
    html = html.replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener">$1</a>'
    );
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/__(.+?)__/g, "<strong>$1</strong>");
    html = html.replace(
      /(^|[^*])\*(?!\*)([^*]+?)\*(?!\*)([^*]|$)/g,
      (match, before, content, after) => `${before}<em>${content}</em>${after}`
    );
    html = html.replace(
      /(^|[^_])_(?!_)([^_]+?)_(?!_)([^_]|$)/g,
      (match, before, content, after) => `${before}<em>${content}</em>${after}`
    );
    return html;
  }

  function renderMarkdownSafe(text) {
    const escaped = escapeHtml(text);
    const lines = escaped.split(/\r?\n/);
    const rendered = [];
    let listType = null;
    let paragraphBuffer = [];
    let lastListItemIndex = -1;

    const flushList = () => {
      if (!listType) return;
      rendered.push(listType === "ol" ? "</ol>" : "</ul>");
      listType = null;
      lastListItemIndex = -1;
    };

    const ensureList = (type) => {
      if (listType === type) {
        return;
      }
      flushList();
      const tag =
        type === "ol"
          ? '<ol class="chatbot__list chatbot__list--ordered">'
          : '<ul class="chatbot__list">';
      rendered.push(tag);
      listType = type;
      lastListItemIndex = -1;
    };

    const flushParagraph = () => {
      if (!paragraphBuffer.length) return;
      rendered.push(
        `<p class="chatbot__paragraph">${formatInlineMarkdown(
          paragraphBuffer.join(" ")
        )}</p>`
      );
      paragraphBuffer = [];
    };

    lines.forEach((line) => {
      const trimmed = line.trim();
      const bulletMatch = trimmed.match(/^[-*]\s+(.*)$/);
      const orderedMatch = trimmed.match(/^\d+\.\s+(.*)$/);

      if (bulletMatch) {
        flushParagraph();
        ensureList("ul");
        rendered.push(`<li>${formatInlineMarkdown(bulletMatch[1])}</li>`);
        lastListItemIndex = rendered.length - 1;
        return;
      }

      if (orderedMatch) {
        flushParagraph();
        ensureList("ol");
        rendered.push(`<li>${formatInlineMarkdown(orderedMatch[1])}</li>`);
        lastListItemIndex = rendered.length - 1;
        return;
      }

      if (listType && trimmed) {
        if (lastListItemIndex >= 0) {
          const continuation = formatInlineMarkdown(trimmed);
          rendered[lastListItemIndex] = rendered[lastListItemIndex].replace(
            /<\/li>$/,
            ` ${continuation}</li>`
          );
        }
        return;
      }

      flushList();

      if (!trimmed) {
        flushParagraph();
        return;
      }

      paragraphBuffer.push(trimmed);
    });

    flushParagraph();
    flushList();

    const html = rendered.join("").trim();
    if (html) {
      return html;
    }
    return '<p class="chatbot__paragraph"></p>';
  }

  function initChatbot() {
    const root = document.querySelector("[data-chatbot]");
    if (!root) return;

    const trigger = root.querySelector("[data-chatbot-trigger]");
    const panel = root.querySelector("[data-chatbot-panel]");
    const closeButton = root.querySelector("[data-chatbot-close]");
    const expandButton = root.querySelector("[data-chatbot-expand]");
    const form = root.querySelector("[data-chatbot-form]");
    const input = root.querySelector("[data-chatbot-input]");
    const log = root.querySelector("[data-chatbot-log]");
    const status = root.querySelector("[data-chatbot-status]");
    let placeholder = log.querySelector(".chatbot__placeholder");
    const MAX_HISTORY_ITEMS = 12;
    const history = [];

    function ensurePanelOpen() {
      if (!panel) return;
      panel.hidden = false;
      root.classList.add("chatbot--open");
      trigger.setAttribute("aria-expanded", "true");
      window.setTimeout(() => input?.focus(), 80);
    }

    function ensurePanelClosed() {
      if (!panel) return;
      panel.hidden = true;
      root.classList.remove("chatbot--open");
      trigger.setAttribute("aria-expanded", "false");
      status.textContent = "";
    }

    function appendBubble(text, variant) {
      if (placeholder) {
        placeholder.remove();
        placeholder = null;
      }
      const bubble = document.createElement("div");
      bubble.className = `chatbot__bubble chatbot__bubble--${variant}`;
      bubble.innerHTML = renderMarkdownSafe(text);
      log.appendChild(bubble);
      window.requestAnimationFrame(() => {
        bubble.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      return bubble;
    }

    async function submitMessage(event) {
      event.preventDefault();
      const raw = input.value.trim();
      if (!raw) {
        input.focus();
        return;
      }

      appendBubble(raw, "user");
      input.value = "";
      status.textContent = "Consultando...";
      root.classList.add("chatbot--loading");

      try {
        const sanitizedHistory = history
          .slice(-MAX_HISTORY_ITEMS)
          .map((turn) => ({
            role: turn.role,
            content: (turn.content || "").trim(),
          }))
          .filter((turn) => turn.content.length > 0);

        const payload = {
          message: raw,
          history: sanitizedHistory,
        };

        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        const answer = typeof data.reply === "string" ? data.reply : "";
        const bubble = appendBubble(answer || "No pude responder en este momento.", "bot");
        status.textContent = answer ? "Listo" : "Intenta nuevamente.";

        history.push({ role: "user", content: raw });
        if (answer) {
          history.push({ role: "assistant", content: answer });
        }
        if (history.length > MAX_HISTORY_ITEMS) {
          history.splice(0, history.length - MAX_HISTORY_ITEMS);
        }
      } catch (error) {
        console.error("Error al consultar el asistente:", error);
        appendBubble(
          "Lo siento, no pudimos contactar al asistente. Intenta de nuevo en unos segundos.",
          "bot"
        );
        status.textContent = "No se pudo completar la consulta.";
      } finally {
        root.classList.remove("chatbot--loading");
        window.requestAnimationFrame(() => {
          const lastBubble = log.lastElementChild;
          if (lastBubble) {
            lastBubble.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        });
      }
    }

    function toggleExpand(force) {
      const expanded =
        typeof force === "boolean" ? force : !root.classList.contains("chatbot--expanded");
      root.classList.toggle("chatbot--expanded", expanded);
      if (expandButton) {
        expandButton.setAttribute(
          "aria-label",
          expanded ? "Reducir chat" : "Expandir chat"
        );
        expandButton.dataset.state = expanded ? "expanded" : "normal";
        expandButton.innerHTML = expanded ? "<span aria-hidden=\"true\">⤡</span>" : "<span aria-hidden=\"true\">⤢</span>";
      }
      if (expanded) {
        window.requestAnimationFrame(() => {
          log?.scrollTo({ top: log.scrollHeight, behavior: "smooth" });
        });
      }
    }

    trigger?.addEventListener("click", () => {
      if (root.classList.contains("chatbot--open")) {
        ensurePanelClosed();
      } else {
        ensurePanelOpen();
      }
    });

    closeButton?.addEventListener("click", ensurePanelClosed);
    form?.addEventListener("submit", submitMessage);

    expandButton?.addEventListener("click", () => toggleExpand());

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && root.classList.contains("chatbot--open")) {
        ensurePanelClosed();
      }
    });

    toggleExpand(root.classList.contains("chatbot--expanded"));
  }

  function initCategorySubcategoryPicker(root = document) {
    root.querySelectorAll("[data-category-select]").forEach((categorySelect) => {
      const container = categorySelect.closest("form") || root;
      const subcategorySelect = container.querySelector(
        "[data-subcategory-select]"
      );
      if (!subcategorySelect) {
        return;
      }

      let rawMap = [];
      try {
        rawMap = JSON.parse(categorySelect.dataset.categoryMap || "[]");
      } catch (error) {
        rawMap = [];
      }

      const lookup = new Map(
        rawMap.map((item) => [
          String(item.id),
          Array.isArray(item.subcategories) ? item.subcategories : [],
        ])
      );

      const setPlaceholder = (text) => {
        subcategorySelect.innerHTML = "";
        const option = document.createElement("option");
        option.value = "";
        option.textContent = text;
        option.selected = true;
        subcategorySelect.appendChild(option);
      };

      const resetSelect = () => {
        setPlaceholder("Selecciona una categoría primero");
        subcategorySelect.disabled = true;
      };

      const populateSubcategories = (categoryId) => {
        const items = lookup.get(String(categoryId)) || [];
        if (!items.length) {
          setPlaceholder("Sin subcategorías disponibles");
          subcategorySelect.disabled = true;
          return;
        }

        subcategorySelect.innerHTML = "";
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "Sin subcategoría (opcional)";
        placeholder.selected = true;
        subcategorySelect.appendChild(placeholder);

        items.forEach((item) => {
          const option = document.createElement("option");
          option.value = item.id;
          option.textContent = item.name;
          subcategorySelect.appendChild(option);
        });
        subcategorySelect.disabled = false;
      };

      categorySelect.addEventListener("change", () => {
        const value = categorySelect.value;
        if (!value) {
          resetSelect();
          return;
        }
        populateSubcategories(value);
      });

      if (categorySelect.value) {
        populateSubcategories(categorySelect.value);
      } else {
        resetSelect();
      }
    });
  }

  function initLibraryNavigator(root = document) {
    const shell = root.querySelector("[data-library-shell]");
    if (!shell) return;

    const tablist = shell.querySelector("[data-library-tabs]");
    const stage = shell.querySelector("[data-library-stage]");
    if (!tablist || !stage) return;

    const tabs = Array.from(tablist.querySelectorAll(".library-tab"));
    const panels = Array.from(stage.querySelectorAll("[data-library-panel]"));
    if (!tabs.length || !panels.length) return;

    const findPanel = (id) => panels.find((panel) => panel.id === id);

    const activate = (id, focusTab = false) => {
      const panel = findPanel(id);
      if (!panel) return;

      tabs.forEach((tab) => {
        const isActive = tab.dataset.target === id;
        tab.classList.toggle("is-active", isActive);
        tab.setAttribute("aria-selected", String(isActive));
        tab.setAttribute("tabindex", isActive ? "0" : "-1");
        if (isActive && focusTab) {
          tab.focus({ preventScroll: true });
        }
      });

      panels.forEach((item) => {
        const isActive = item === panel;
        item.classList.toggle("is-active", isActive);
        item.toggleAttribute("hidden", !isActive);
      });
    };

    const initialHash = window.location.hash ? window.location.hash.slice(1) : null;
    const preferredId = initialHash && findPanel(initialHash) ? initialHash : tabs[0].dataset.target;

    shell.setAttribute("data-enhanced", "true");
    panels.forEach((panel) => {
      if (!panel.classList.contains("is-active")) {
        panel.setAttribute("hidden", "hidden");
      }
    });
    activate(preferredId);

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.target;
        activate(target, true);
        if (target) {
          history.replaceState(null, "", `#${target}`);
        }
      });
    });

    window.addEventListener("hashchange", () => {
      const hashId = window.location.hash ? window.location.hash.slice(1) : null;
      if (!hashId) return;
      if (findPanel(hashId)) {
        activate(hashId);
      }
    });
  }


  function initMap(root = document) {
    const mapRoot = root.querySelector("[data-map-placeholder]");
    if (!mapRoot) return;

    const token = mapRoot.dataset.mapToken;
    if (!token || typeof mapboxgl === "undefined") {
      console.warn("Mapbox no está disponible o falta MAPBOX_TOKEN");
      return;
    }

    mapboxgl.accessToken = token;
    const map = new mapboxgl.Map({
      container: mapRoot,
      style: "mapbox://styles/mapbox/streets-v11",
      center: [ -70.6693, -33.4569 ],
      zoom: 13,
    });

    const geocoder = new mapboxgl.Geocoder || null;
    const address = mapRoot.dataset.address;
    if (address && mapboxgl.Geocoder) {
      const geocoder = new MapboxGeocoder({
        accessToken: token,
        mapboxgl,
        placeholder: address,
      });
      geocoder.on("result", (event) => {
        const [lng, lat] = event.result.center;
        new mapboxgl.Marker().setLngLat([lng, lat]).addTo(map);
        map.flyTo({ center: [lng, lat], zoom: 15 });
      });
      map.addControl(geocoder);
      geocoder.query(address);
    } else if (address) {
      fetch()
        .then((response) => response.json())
        .then((data) => {
          const [lng, lat] = data.features[0].center;
          map.setCenter([lng, lat]);
          new mapboxgl.Marker().setLngLat([lng, lat]).addTo(map);
        })
        .catch((error) => console.error("No se pudo geocodificar la dirección", error));
    }
  }
  function initMap(root = document) {
    const mapRoot = root.querySelector("[data-map-placeholder]");
    if (!mapRoot) return;

    const token = mapRoot.dataset.mapToken;
    if (!token || typeof mapboxgl === "undefined") {
      console.warn("Mapbox no está disponible o falta MAPBOX_TOKEN");
      return;
    }

    mapboxgl.accessToken = token;
    const map = new mapboxgl.Map({
      container: mapRoot,
      style: "mapbox://styles/mapbox/streets-v11",
      center: [-70.6693, -33.4569],
      zoom: 13,
    });

    const address = mapRoot.dataset.address;
    if (address) {
      fetch(
        "https://api.mapbox.com/geocoding/v5/mapbox.places/" +
          encodeURIComponent(address) +
          ".json?access_token=" +
          token
      )
        .then((response) => response.json())
        .then((data) => {
          const feature = data.features && data.features[0];
          if (!feature) return;
          const [lng, lat] = feature.center;
          map.setCenter([lng, lat]);
          map.setZoom(14);
          new mapboxgl.Marker().setLngLat([lng, lat]).addTo(map);
        })
        .catch((error) => {
          console.error("No se pudo geocodificar la dirección", error);
        });
    }

    map.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }));
  }

  function initLogoMark(root = document) {
    const mark = root.querySelector(".site-logo__mark");
    const image = mark?.querySelector(".site-logo__image");
    if (!mark || !image) return;

    const showIfLoaded = () => {
      if (image.complete && image.naturalWidth > 0) {
        mark.classList.add("has-image");
      }
    };

    image.addEventListener("load", showIfLoaded);
    image.addEventListener("error", () => {
      mark.classList.remove("has-image");
    });
    showIfLoaded();
  }

  function initDirectUpload(root = document) {
    const form = root.querySelector("form[data-direct-upload]");
    if (!form) return;

    let config;
    try {
      config = JSON.parse(form.dataset.directUpload || "{}");
    } catch (error) {
      console.warn("Configuración de subida directa inválida", error);
      return;
    }

    if (!config || !config.enabled) {
      return;
    }

    const statusNode = form.querySelector("[data-upload-status]");
    const submitButton = form.querySelector("button[type='submit']");
    const fileInput = form.querySelector("input[type='file'][name='file']");

    const showStatus = (message, type = "info") => {
      if (!statusNode) return;
      statusNode.hidden = false;
      statusNode.dataset.state = type;
      statusNode.textContent = message;
    };

    const resetStatus = () => {
      if (statusNode) {
        statusNode.hidden = true;
        statusNode.textContent = "";
      }
    };

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      resetStatus();

      const categoryField = form.querySelector("select[name='category_id']");
      if (!categoryField || !categoryField.value) {
        showStatus("Selecciona una categoría antes de continuar.", "error");
        categoryField?.focus();
        return;
      }

      const file = fileInput?.files?.[0];
      if (!file) {
        showStatus("Selecciona un archivo para subir.", "error");
        fileInput?.focus();
        return;
      }

      if (config.maxFileSize && file.size > config.maxFileSize * 1024 * 1024) {
        showStatus(
          `El archivo supera el límite de ${config.maxFileSize} MB configurado.`,
          "error",
        );
        return;
      }

      const subcategoryField = form.querySelector("select[name='subcategory_id']");
      const payload = {
        filename: file.name,
        contentType: file.type || "application/octet-stream",
        fileSize: file.size,
        categoryId: parseInt(categoryField.value, 10),
        subcategoryId: subcategoryField?.value ? parseInt(subcategoryField.value, 10) : null,
      };

      form.setAttribute("aria-busy", "true");
      submitButton?.setAttribute("disabled", "disabled");
      showStatus("Preparando carga segura...", "info");

      try {
        const initResponse = await fetch(config.initUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          credentials: "same-origin",
        });

        if (!initResponse.ok) {
          throw new Error(`Error al iniciar la carga (${initResponse.status})`);
        }

        const initData = await initResponse.json();
        showStatus("Subiendo al almacenamiento seguro...", "info");

        const uploadResponse = await fetch(initData.uploadUrl, {
          method: "PUT",
          headers: initData.headers || { "Content-Type": file.type },
          body: file,
        });

        if (!uploadResponse.ok) {
          throw new Error(`Error al subir al almacenamiento (${uploadResponse.status})`);
        }

        showStatus("Confirmando y guardando metadatos...", "info");

        const finalizeResponse = await fetch(config.finalizeUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ ...payload, storageKey: initData.storageKey }),
        });

        if (!finalizeResponse.ok) {
          throw new Error(`No se pudo finalizar la carga (${finalizeResponse.status})`);
        }

        showStatus("Documento guardado correctamente. Recargando...", "success");
        window.setTimeout(() => {
          window.location.reload();
        }, 600);
      } catch (error) {
        console.error("Carga directa falló", error);
        showStatus(
          error?.message || "No se pudo completar la carga. Intenta nuevamente.",
          "error",
        );
      } finally {
        form.removeAttribute("aria-busy");
        submitButton?.removeAttribute("disabled");
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initDownloads();
    initViewers();
    initLibraryViewToggle();
    initLibrarySorter();
    initDeletes();
    initReorderBlocks();
    initDocumentOrganizer();
    initChatbot();
    initDirectUpload();
    initCategorySubcategoryPicker();
    initLibraryNavigator();
    initLogoMark();
    initMap();
    initWallReplies();
  });
})();
