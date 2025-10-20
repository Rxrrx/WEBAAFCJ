(function () {
  const DOWNLOAD_SELECTOR = "[data-download-url]";
  const VIEW_SELECTOR = "[data-view-url]";
  const TOGGLE_SELECTOR = ".view-toggle";
  const DELETE_SELECTOR =
    "form[data-action='delete-doc'], form[data-action='delete-category'], form[data-action='delete-subcategory']";

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
        const isSubcategory = form.dataset.action === "delete-subcategory";
        const itemName =
          form.dataset.name || form.dataset.filename || "este elemento";
        const message =
          form.dataset.confirm ||
          (isCategory
            ? `Eliminar la categoria "${itemName}" y todos sus documentos asociados?`
            : isSubcategory
            ? `Eliminar la subcategoria "${itemName}" y todos sus documentos?`
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

    const flushList = () => {
      if (!listType) return;
      rendered.push(listType === "ol" ? "</ol>" : "</ul>");
      listType = null;
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
        return;
      }

      if (orderedMatch) {
        flushParagraph();
        ensureList("ol");
        rendered.push(`<li>${formatInlineMarkdown(orderedMatch[1])}</li>`);
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
        bubble.scrollIntoView({ behavior: "smooth", block: "nearest" });
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

  document.addEventListener("DOMContentLoaded", () => {
    initDownloads();
    initViewers();
    initToggles();
    initDeletes();
    initChatbot();
    initCategorySubcategoryPicker();
    initLibraryNavigator();
    initLogoMark();
    initMap();
  });
})();
