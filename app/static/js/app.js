(() => {
  "use strict";
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const rub = (n) => Math.round(n).toLocaleString("ru-RU") + " ₽";

  // ---------- Мобильное меню ----------
  const burger = $(".burger");
  const nav = $("#main-nav");
  burger?.addEventListener("click", () => {
    const open = nav.classList.toggle("is-open");
    burger.setAttribute("aria-expanded", String(open));
  });

  // ---------- Модалка заявки: [data-lead="kind"] + data-title / data-sub / data-property ----------
  const dialog = $("#lead-dialog");
  const tpl = $("#lead-form-tpl");
  const defaultTitle = $("#lead-dialog-title")?.textContent;
  const defaultSub = $("#lead-dialog-sub")?.textContent;

  document.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-lead]");
    if (!trigger || !dialog) return;
    const body = $("#lead-dialog-body");
    body.replaceChildren(tpl.content.cloneNode(true));
    const form = $("form", body);
    form.elements.kind.value = trigger.dataset.lead;
    if (trigger.dataset.property) {
      form.insertAdjacentHTML("afterbegin", `<input type="hidden" name="property_id" value="${Number(trigger.dataset.property)}">`);
    }
    $("#lead-dialog-title").textContent = trigger.dataset.title || defaultTitle;
    $("#lead-dialog-sub").textContent = trigger.dataset.sub || defaultSub;
    window.htmx?.process(body);
    dialog.showModal();
    form.elements.name.focus();
  });

  // Закрытие диалогов: крестик и клик по подложке
  $$("dialog").forEach((d) => {
    d.addEventListener("click", (e) => {
      if (e.target === d || e.target.closest("[data-close]")) d.close();
    });
  });

  // ---------- Поля с деньгами: «8000000» → «8 000 000» ----------
  document.addEventListener("input", (e) => {
    const el = e.target;
    if (!el.classList?.contains("js-money")) return;
    const digits = el.value.replace(/\D/g, "").slice(0, 12);
    el.value = digits ? Number(digits).toLocaleString("ru-RU") : "";
  });

  // Чистый URL фильтров: без пустых параметров и пробелов в суммах
  document.addEventListener("htmx:configRequest", (e) => {
    const fd = e.detail.formData;
    if (!fd || e.detail.verb !== "get") return;
    for (const [key, value] of [...fd.entries()]) {
      if (value === "" || (key === "sort" && value === "new")) fd.delete(key);
      else if (key.startsWith("price_")) fd.set(key, String(value).replace(/\D/g, ""));
    }
  });

  // ---------- Фильтры каталога на мобильных ----------
  document.addEventListener("click", (e) => {
    if (!e.target.closest("[data-filters-toggle]")) return;
    $("#filters-panel")?.classList.toggle("is-open");
  });

  // ---------- Галерея + лайтбокс ----------
  const gallery = $("[data-gallery]");
  const lightbox = $("#lightbox");
  if (gallery && lightbox) {
    const srcs = $$("img", $("template[data-gallery-src]", gallery).content).map((img) => ({ src: img.src, alt: img.alt }));
    const lbImg = $(".lb-img", lightbox);
    const counter = $(".lb-counter", lightbox);
    let current = 0;

    const show = (i) => {
      current = (i + srcs.length) % srcs.length;
      lbImg.src = srcs[current].src;
      lbImg.alt = srcs[current].alt;
      counter.textContent = `${current + 1} / ${srcs.length}`;
      // подгружаем соседнее фото заранее
      new Image().src = srcs[(current + 1) % srcs.length].src;
    };

    gallery.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-index]");
      if (!btn) return;
      show(Number(btn.dataset.index));
      lightbox.showModal();
    });
    $(".lb-prev", lightbox).addEventListener("click", () => show(current - 1));
    $(".lb-next", lightbox).addEventListener("click", () => show(current + 1));
    lightbox.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft") show(current - 1);
      if (e.key === "ArrowRight") show(current + 1);
    });
    let touchX = null;
    lightbox.addEventListener("touchstart", (e) => { touchX = e.touches[0].clientX; }, { passive: true });
    lightbox.addEventListener("touchend", (e) => {
      if (touchX === null) return;
      const dx = e.changedTouches[0].clientX - touchX;
      if (Math.abs(dx) > 40) show(current + (dx < 0 ? 1 : -1));
      touchX = null;
    });
  }

  // ---------- Ипотечный калькулятор (аннуитет) ----------
  const calc = $("[data-calc]");
  if (calc) {
    const price = Number(calc.dataset.price);
    const out = (name) => $(`[data-out="${name}"]`, calc);
    const yearsWord = (n) => {
      const m10 = n % 10, m100 = n % 100;
      if (m100 >= 11 && m100 <= 19) return "лет";
      return m10 === 1 ? "год" : m10 >= 2 && m10 <= 4 ? "года" : "лет";
    };
    const update = () => {
      const downPct = Number(calc.querySelector("[name=down]").value);
      const years = Number(calc.querySelector("[name=years]").value);
      const rate = Number(calc.querySelector("[name=rate]").value) / 100 / 12;
      const loan = price * (1 - downPct / 100);
      const n = years * 12;
      const payment = rate > 0 ? (loan * rate) / (1 - Math.pow(1 + rate, -n)) : loan / n;
      out("down").textContent = `${downPct}% · ${rub(price * downPct / 100)}`;
      out("years").textContent = `${years} ${yearsWord(years)}`;
      out("loan").textContent = rub(loan);
      out("payment").textContent = Number.isFinite(payment) ? rub(payment) : "—";
    };
    calc.addEventListener("input", update);
    update();
  }

  // ---------- Карта (Leaflet + OpenStreetMap) ----------
  const mapEl = $("#map");
  if (mapEl) {
    window.addEventListener("load", () => {
      if (!window.L) return;
      const lat = Number(mapEl.dataset.lat), lon = Number(mapEl.dataset.lon);
      const map = L.map(mapEl, { scrollWheelZoom: false }).setView([lat, lon], 15);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(map);
      L.marker([lat, lon]).addTo(map).bindPopup(mapEl.dataset.title);
    });
  }

  // ---------- Поделиться / PDF ----------
  document.addEventListener("click", async (e) => {
    const share = e.target.closest("[data-share]");
    if (share) {
      const data = { title: share.dataset.title, url: location.href };
      if (navigator.share) {
        try { await navigator.share(data); } catch { /* пользователь закрыл окно */ }
      } else {
        await navigator.clipboard?.writeText(location.href);
        share.textContent = "Ссылка скопирована";
        setTimeout(() => { share.textContent = "Поделиться"; }, 2000);
      }
    }
    if (e.target.closest("[data-print]")) window.print();
  });
})();
