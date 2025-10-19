(function () {
  const DOWNLOAD_SELECTOR = "[data-download-url]";
  const VIEW_SELECTOR = "[data-view-url]";
  const TOGGLE_SELECTOR = ".view-toggle";
  const DELETE_SELECTOR =
    "form[data-action='delete-doc'], form[data-action='delete-category']";

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

  function initToggles(root = document) {
    root.querySelectorAll(TOGGLE_SELECTOR).forEach((toggle) => {
      const container = document.querySelector(".library-workspace");
      if (!container) return;

      toggle.querySelectorAll(".toggle-button").forEach((button) => {
        button.addEventListener("click", () => {
          const target = button.dataset.target;

          toggle.querySelectorAll(".toggle-button").forEach((btn) => {
            const isActive = btn === button;
            btn.classList.toggle("is-active", isActive);
            btn.setAttribute("aria-pressed", String(isActive));
          });

          container.querySelectorAll(".view-panel").forEach((panel) => {
            const isTarget = panel.dataset.panel === target;
            panel.toggleAttribute("hidden", !isTarget);
          });

          container.setAttribute("data-active", target);
        });
      });
    });
  }

  function initDeletes(root = document) {
    root.querySelectorAll(DELETE_SELECTOR).forEach((form) => {
      form.addEventListener("submit", (event) => {
        const isCategory = form.dataset.action === "delete-category";
        const itemName =
          form.dataset.name || form.dataset.filename || "este elemento";
        const message =
          form.dataset.confirm ||
          (isCategory
            ? `Eliminar la categoria "${itemName}" y todos sus documentos asociados?`
            : `Eliminar "${itemName}" de manera permanente?`);
        if (!window.confirm(message)) {
          event.preventDefault();
        }
      });
    });
  }

  const HTML_ESCAPE = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };

  function escapeHtml(value) {
    return value.replace(/[&<>"']/g, (char) => HTML_ESCAPE[char] || char);
  }

  function initChatbot() {
    const root = document.querySelector("[data-chatbot]");
    if (!root) return;

    const trigger = root.querySelector("[data-chatbot-trigger]");
    const panel = root.querySelector("[data-chatbot-panel]");
    const closeButton = root.querySelector("[data-chatbot-close]");
    const form = root.querySelector("[data-chatbot-form]");
    const input = root.querySelector("[data-chatbot-input]");
    const log = root.querySelector("[data-chatbot-log]");
    const status = root.querySelector("[data-chatbot-status]");
    let placeholder = log.querySelector(".chatbot__placeholder");

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
      bubble.innerHTML = escapeHtml(text).replace(/\n/g, "<br />");
      log.appendChild(bubble);
      log.scrollTop = log.scrollHeight;
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
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: raw }),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        const answer = typeof data.reply === "string" ? data.reply : "";
        appendBubble(answer || "No pude responder en este momento.", "bot");
        status.textContent = answer ? "Listo" : "Intenta nuevamente.";
      } catch (error) {
        console.error("Error al consultar el asistente:", error);
        appendBubble(
          "Lo siento, no pudimos contactar al asistente. Intenta de nuevo en unos segundos.",
          "bot"
        );
        status.textContent = "No se pudo completar la consulta.";
      } finally {
        root.classList.remove("chatbot--loading");
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

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && root.classList.contains("chatbot--open")) {
        ensurePanelClosed();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initDownloads();
    initViewers();
    initToggles();
    initDeletes();
    initChatbot();
  });
})();
