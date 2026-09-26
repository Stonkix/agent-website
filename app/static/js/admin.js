// Форма объекта в админке: метка на Яндекс.Карте вместо полей широты/долготы и drag-n-drop фото
(() => {
  "use strict";
  const cfg = window.ADMIN_CFG || {};

  // ---------- Яндекс.Карта: клик ставит метку, метку можно тащить ----------
  const lat = document.querySelector("input[name=lat]");
  const lon = document.querySelector("input[name=lon]");
  const address = document.getElementById("address");

  if (lat && lon && address) {
    const row = document.createElement("div");
    row.className = "mb-3 form-group row";
    row.innerHTML = `
      <label class="form-label col-sm-2 col-form-label">Метка на карте</label>
      <div class="col-sm-10">
        <div class="map-toolbar">
          <button type="button" class="btn" data-geocode>Найти по адресу</button>
          <button type="button" class="btn" data-clear>Убрать метку</button>
          <span class="text-muted" data-coords></span>
        </div>
        <div class="admin-map" id="admin-map"></div>
        <small class="text-muted">Кликните по карте или перетащите метку. Без метки карта на сайте не показывается.</small>
      </div>`;
    address.closest(".form-group").after(row);

    const coordsEl = row.querySelector("[data-coords]");
    const mapEl = row.querySelector("#admin-map");

    if (!window.ymaps) {
      mapEl.classList.add("admin-map-error");
      mapEl.textContent = "Не удалось загрузить Яндекс.Карты. Проверьте интернет и YANDEX_MAPS_API_KEY в .env";
    } else {
      ymaps.ready(() => {
        const has = lat.value && lon.value;
        const start = has ? [parseFloat(lat.value), parseFloat(lon.value)] : cfg.center;
        const map = new ymaps.Map(mapEl, {
          center: start,
          zoom: has ? 16 : 12,
          controls: ["zoomControl", "typeSelector", "fullscreenControl"],
        });
        map.behaviors.disable("scrollZoom"); // чтобы колесо мыши прокручивало форму, а не карту
        let mark = null;

        const setPoint = (coords, recenter = false) => {
          lat.value = coords[0].toFixed(6);
          lon.value = coords[1].toFixed(6);
          coordsEl.textContent = `${lat.value}, ${lon.value}`;
          if (!mark) {
            mark = new ymaps.Placemark(coords, {}, { draggable: true, preset: "islands#darkGreenDotIcon" });
            mark.events.add("dragend", () => setPoint(mark.geometry.getCoordinates()));
            map.geoObjects.add(mark);
          } else {
            mark.geometry.setCoordinates(coords);
          }
          if (recenter) map.setCenter(coords, 16, { duration: 300 });
        };

        if (has) setPoint(start);
        map.events.add("click", (e) => setPoint(e.get("coords")));

        row.querySelector("[data-geocode]").addEventListener("click", async () => {
          const query = address.value.trim();
          if (!query) return address.focus();
          try {
            const res = await ymaps.geocode(`${cfg.city}, ${query}`, { results: 1 });
            const found = res.geoObjects.get(0);
            if (found) setPoint(found.geometry.getCoordinates(), true);
            else alert("Адрес не найден — поставьте метку кликом по карте");
          } catch {
            alert("Поиск по адресу недоступен (нужен ключ YANDEX_MAPS_API_KEY). Поставьте метку кликом по карте");
          }
        });

        row.querySelector("[data-clear]").addEventListener("click", () => {
          if (mark) map.geoObjects.remove(mark);
          mark = null;
          lat.value = lon.value = "";
          coordsEl.textContent = "";
        });
      });
    }
  }

  // ---------- Drag-n-drop фото ----------
  const input = document.getElementById("photos_upload");
  if (input) {
    const ACCEPT = ["image/jpeg", "image/png", "image/webp"];
    const picked = new DataTransfer(); // накапливаем файлы из нескольких перетаскиваний
    const existing = document.getElementById("existing-photos");

    const zone = document.createElement("div");
    zone.className = "dropzone";
    zone.tabIndex = 0;
    zone.innerHTML = `
      ${existing ? `<div class="dz-existing"><div class="dz-caption">Загруженные фото: перетащите, чтобы поменять порядок (первое — главное), × — удалить. Изменения применятся после «Сохранить».</div><div class="dz-grid">${existing.innerHTML}</div></div>` : ""}
      <div class="dz-hint">
        <strong>Перетащите фото сюда</strong> или нажмите, чтобы выбрать
        <small>JPG, PNG, WebP · можно сразу несколько · сожмутся автоматически</small>
      </div>
      <div class="dz-grid dz-new"></div>`;
    input.hidden = true;
    input.after(zone);
    const grid = zone.querySelector(".dz-new");

    // --- уже загруженные фото: порядок перетаскиванием и удаление ---
    const savedGrid = zone.querySelector(".dz-existing .dz-grid");
    let dragged = null;
    if (savedGrid) {
      const hidden = (name) => {
        const el = Object.assign(document.createElement("input"), { type: "hidden", name });
        zone.append(el);
        return el;
      };
      const orderInput = hidden("photo_order");
      const deleteInput = hidden("photo_delete");
      const syncSaved = () => {
        const items = [...savedGrid.querySelectorAll("[data-id]")];
        orderInput.value = items.map((el) => el.dataset.id).join(",");
        deleteInput.value = items.filter((el) => el.classList.contains("is-deleted")).map((el) => el.dataset.id).join(",");
      };
      savedGrid.addEventListener("click", (e) => {
        const btn = e.target.closest(".dz-remove");
        if (!btn) return;
        e.stopPropagation();
        const item = btn.closest("[data-id]");
        const deleted = item.classList.toggle("is-deleted");
        btn.textContent = deleted ? "↺" : "×";
        btn.title = deleted ? "Вернуть" : "Удалить фото";
        syncSaved();
      });
      savedGrid.addEventListener("dragstart", (e) => {
        dragged = e.target.closest("[data-id]");
        if (!dragged) return;
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", dragged.dataset.id);
        dragged.classList.add("is-dragging");
      });
      savedGrid.addEventListener("dragover", (e) => {
        if (!dragged) return;
        e.preventDefault();
        e.stopPropagation();
        const over = e.target.closest("[data-id]");
        if (!over || over === dragged) return;
        const r = over.getBoundingClientRect();
        over[e.clientX > r.left + r.width / 2 ? "after" : "before"](dragged);
      });
      savedGrid.addEventListener("drop", (e) => {
        if (!dragged) return;
        e.preventDefault();
        e.stopPropagation();
      });
      savedGrid.addEventListener("dragend", () => {
        dragged?.classList.remove("is-dragging");
        dragged = null;
        syncSaved();
      });
      syncSaved();
    }

    const render = () => {
      grid.replaceChildren();
      [...picked.files].forEach((file, i) => {
        const item = document.createElement("div");
        item.className = "dz-item";
        const img = document.createElement("img");
        img.src = URL.createObjectURL(file);
        img.onload = () => URL.revokeObjectURL(img.src);
        img.alt = file.name;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "dz-remove";
        remove.title = "Убрать";
        remove.textContent = "×";
        remove.addEventListener("click", (e) => {
          e.stopPropagation();
          picked.items.remove(i);
          sync();
        });
        item.append(img, remove);
        grid.append(item);
      });
      zone.classList.toggle("has-files", picked.files.length > 0);
    };
    const sync = () => {
      input.files = picked.files;
      render();
    };
    const add = (files) => {
      const skipped = [];
      for (const f of files) {
        if (!ACCEPT.includes(f.type)) { skipped.push(f.name); continue; }
        const dup = [...picked.files].some((x) => x.name === f.name && x.size === f.size);
        if (!dup) picked.items.add(f);
      }
      if (skipped.length) alert(`Пропущены (формат не поддерживается): ${skipped.join(", ")}`);
      sync();
    };

    zone.addEventListener("click", (e) => {
      if (!e.target.closest(".dz-existing, .dz-remove")) input.click();
    });
    zone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
    });
    input.addEventListener("change", () => add(input.files));
    ["dragenter", "dragover"].forEach((ev) =>
      zone.addEventListener(ev, (e) => { e.preventDefault(); if (!dragged) zone.classList.add("is-over"); }));
    ["dragleave", "drop"].forEach((ev) =>
      zone.addEventListener(ev, () => zone.classList.remove("is-over")));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      if (dragged) return; // это была перестановка загруженных фото, а не новые файлы
      add(e.dataTransfer.files);
    });
    // файл, брошенный мимо зоны, не должен открываться во вкладке вместо формы
    window.addEventListener("dragover", (e) => e.preventDefault());
    window.addEventListener("drop", (e) => e.preventDefault());
  }
})();
