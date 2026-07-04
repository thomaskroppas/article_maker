// ══════════ SITES PAGE ══════════
// JS-логика страницы «Сайты»: список сайтов, создание сайта,
// раскрывающаяся панель авторов в карточке, создание/деактивация автора.
// Подключается в main_window.py (содержимое подставляется в <script>).

// Состояние страницы: какой сайт сейчас раскрыт.
let _expandedSiteDomain = null;
// Кэш авторов по домену (чтобы не дёргать БД лишний раз при перерисовке).
let _authorsCache = {};

// Загружает список сайтов из Python и рендерит карточками.
function loadSitesPage() {
  if (!bridge || !bridge.getSitesWithCounts) {
    setTimeout(loadSitesPage, 100);
    return;
  }
  bridge.getSitesWithCounts(jsonStr => {
    let sites;
    try { sites = JSON.parse(jsonStr) || []; }
    catch(e) { sites = []; }
    const wrap = document.getElementById('sites-list');
    if (!wrap) return;
    if (!sites.length) {
      wrap.innerHTML = '<div style="color:#6c7086;padding:20px;text-align:center">Нет сайтов. Создайте первый.</div>';
      return;
    }
    const real = sites.filter(s => !s.is_test);
    const test = sites.filter(s => s.is_test);
    const ordered = [...real, ...test];
    wrap.innerHTML = ordered.map(renderSiteCard).join('');
    // Если был раскрыт какой-то сайт — раскрываем его снова и подгружаем авторов
    if (_expandedSiteDomain) {
      const sameSite = ordered.find(s => s.domain === _expandedSiteDomain);
      if (sameSite) {
        expandAuthorsPanel(_expandedSiteDomain);
      } else {
        _expandedSiteDomain = null;
      }
    }
  });
}

function renderSiteCard(s) {
  const testBadge = s.is_test
    ? '<span style="background:#45475a;color:#cdd6f4;font-size:11px;padding:2px 8px;border-radius:4px;margin-left:8px">тест</span>'
    : '';
  const nicheLabel = s.niche_name || '— ниша не задана —';
  const dom = escapeHtml(s.domain);
  return `
    <div style="background:#1e1e2e;border:1px solid #313244;border-radius:8px;padding:16px" data-site="${dom}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px">
        <div style="flex:1;min-width:0">
          <div style="font-size:16px;font-weight:600;display:flex;align-items:center">
            ${dom}${testBadge}
          </div>
          <div style="color:#a6adc8;margin-top:4px">${escapeHtml(s.name)}</div>
          <div style="color:#6c7086;font-size:13px;margin-top:8px">${escapeHtml(nicheLabel)}</div>
        </div>
        <div style="text-align:right;color:#6c7086;font-size:13px;white-space:nowrap">
          <div>Статей: <b style="color:#cdd6f4">${s.article_count}</b></div>
          <div style="margin-top:4px">Авторов: <b style="color:#cdd6f4">${s.author_count}</b></div>
        </div>
      </div>
      <div style="margin-top:12px;display:flex;gap:8px">
        <button class="btn btn-ghost btn-sm" onclick="toggleAuthorsPanel('${dom}')">
          <span id="auth-toggle-${dom}">▸</span> Авторы
        </button>
        <button class="btn btn-ghost btn-sm" onclick="openCreateAuthorModal('${dom}','${escapeAttr(s.niche_id || '')}')">
          + Добавить автора
        </button>
      </div>
      <div id="authors-panel-${dom}" style="display:none;margin-top:12px;padding-top:12px;border-top:1px solid #313244"></div>
    </div>
  `;
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function escapeAttr(s) {
  return escapeHtml(s);
}

// ── Панель авторов в карточке ──

function toggleAuthorsPanel(domain) {
  const panel = document.getElementById('authors-panel-' + domain);
  if (!panel) return;
  if (panel.style.display === 'none') {
    expandAuthorsPanel(domain);
  } else {
    collapseAuthorsPanel(domain);
  }
}

function expandAuthorsPanel(domain) {
  const panel = document.getElementById('authors-panel-' + domain);
  const arrow = document.getElementById('auth-toggle-' + domain);
  if (!panel) return;
  panel.style.display = 'block';
  if (arrow) arrow.textContent = '▾';
  _expandedSiteDomain = domain;
  loadAuthorsIntoPanel(domain);
}

function collapseAuthorsPanel(domain) {
  const panel = document.getElementById('authors-panel-' + domain);
  const arrow = document.getElementById('auth-toggle-' + domain);
  if (!panel) return;
  panel.style.display = 'none';
  if (arrow) arrow.textContent = '▸';
  if (_expandedSiteDomain === domain) _expandedSiteDomain = null;
}

function loadAuthorsIntoPanel(domain) {
  const panel = document.getElementById('authors-panel-' + domain);
  if (!panel) return;
  panel.innerHTML = '<div style="color:#6c7086;font-size:12px">Загрузка авторов…</div>';
  bridge.getAuthorsForSite(domain, jsonStr => {
    let authors;
    try { authors = JSON.parse(jsonStr) || []; }
    catch(e) { authors = []; }
    _authorsCache[domain] = authors;
    if (!authors.length) {
      panel.innerHTML = '<div style="color:#6c7086;font-size:13px;padding:8px 0">Авторов пока нет. Создайте первого.</div>';
      return;
    }
    panel.innerHTML = authors.map(a => renderAuthorRow(domain, a)).join('');
  });
}

function renderAuthorRow(domain, a) {
  const aid = escapeAttr(a.author_id);
  const dim = a.is_active ? '' : 'opacity:0.5';
  const checked = a.is_active ? 'checked' : '';
  return `
    <div style="display:flex;gap:12px;padding:10px 0;border-bottom:1px dashed #313244;${dim}">
      <div style="flex:1;min-width:0">
        <div style="font-weight:600">${escapeHtml(a.name)}
          <span style="color:#6c7086;font-weight:400;font-size:12px;margin-left:8px">${escapeHtml(a.age_image || '')}</span>
        </div>
        ${a.tone ? `<div style="color:#a6adc8;font-size:12px;margin-top:2px"><b style="color:#6c7086">Тон:</b> ${escapeHtml(a.tone)}</div>` : ''}
        ${a.character ? `<div style="color:#a6adc8;font-size:12px;margin-top:4px;line-height:1.4">${escapeHtml(a.character)}</div>` : ''}
      </div>
      <div style="white-space:nowrap">
        <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:#6c7086;cursor:pointer">
          <input type="checkbox" ${checked} onchange="onToggleAuthorActive('${aid}','${escapeAttr(domain)}',this.checked)" style="width:auto">
          активен
        </label>
      </div>
    </div>
  `;
}

function onToggleAuthorActive(authorId, domain, isActive) {
  bridge.setAuthorActive(authorId, isActive, respStr => {
    let resp;
    try { resp = JSON.parse(respStr) || {}; }
    catch(e) { resp = {ok: false}; }
    if (resp.ok) {
      // Перерисовываем панель и карточку (счётчики обновятся)
      loadSitesPage();
    } else {
      alert('Не удалось изменить статус автора: ' + (resp.error || ''));
    }
  });
}

// ── Создание сайта ──

function openCreateSiteModal() {
  document.getElementById('cs-domain').value = '';
  document.getElementById('cs-name').value = '';
  document.getElementById('cs-istest').checked = false;
  document.getElementById('cs-error').style.display = 'none';
  loadNichesIntoSelect('cs-niche');
  document.getElementById('modal-create-site').style.display = 'flex';
}

function closeCreateSiteModal() {
  document.getElementById('modal-create-site').style.display = 'none';
}

function loadNichesIntoSelect(selectId) {
  if (!bridge || !bridge.getNiches) {
    setTimeout(() => loadNichesIntoSelect(selectId), 100);
    return;
  }
  bridge.getNiches(jsonStr => {
    let niches;
    try { niches = JSON.parse(jsonStr) || []; }
    catch(e) { niches = []; }
    const sel = document.getElementById(selectId);
    if (!sel) return;
    sel.innerHTML = '<option value="">— не выбрана —</option>' +
      niches.map(n => `<option value="${n.niche_id}">${escapeHtml(n.name_ru)}</option>`).join('');
  });
}

function submitCreateSite() {
  const domain = document.getElementById('cs-domain').value.trim();
  const name = document.getElementById('cs-name').value.trim();
  const niche_id = document.getElementById('cs-niche').value || null;
  const is_test = document.getElementById('cs-istest').checked;
  const errBox = document.getElementById('cs-error');
  errBox.style.display = 'none';

  if (!domain) { errBox.textContent = 'Укажите домен'; errBox.style.display = 'block'; return; }
  if (!name)   { errBox.textContent = 'Укажите имя';   errBox.style.display = 'block'; return; }
  if (!/^[a-z0-9.-]+\.[a-z]{2,}$/i.test(domain)) {
    errBox.textContent = 'Неверный формат домена';
    errBox.style.display = 'block';
    return;
  }

  const payload = JSON.stringify({domain, name, niche_id, is_test});
  bridge.createSite(payload, respStr => {
    let resp;
    try { resp = JSON.parse(respStr) || {}; }
    catch(e) { resp = {ok: false, error: 'Не удалось распарсить ответ'}; }
    if (resp.ok) {
      closeCreateSiteModal();
      loadSitesPage();
      if (typeof loadSites === 'function') loadSites();
    } else {
      errBox.textContent = resp.error || 'Ошибка при создании';
      errBox.style.display = 'block';
    }
  });
}

// ── Создание автора ──

// Хранит контекст текущей открытой модалки автора
let _newAuthorContext = { site_domain: null, niche_id: null };

function openCreateAuthorModal(site_domain, niche_id) {
  _newAuthorContext = { site_domain, niche_id: niche_id || null, reference_id: null };
  document.getElementById('ca-name').value = '';
  document.getElementById('ca-age').value = '';
  document.getElementById('ca-tone').value = '';
  document.getElementById('ca-character').value = '';
  document.getElementById('ca-error').style.display = 'none';
  document.getElementById('ca-reference-status').textContent = '';
  document.getElementById('ca-site-label').textContent =
    'Сайт: ' + site_domain + (niche_id ? ' · ниша: ' + niche_id : ' · ниша не задана');

  // Шаблоны из других сайтов той же ниши
  const tplSel = document.getElementById('ca-template');
  if (niche_id) {
    bridge.getAuthorsInNiche(niche_id, jsonStr => {
      let templates;
      try { templates = JSON.parse(jsonStr) || []; }
      catch(e) { templates = []; }
      templates = templates.filter(t => t.site_domain !== site_domain);
      tplSel.innerHTML = '<option value="">— создать с нуля —</option>' +
        templates.map(t => `<option value="${t.author_id}">${escapeHtml(t.name)} (${escapeHtml(t.site_domain)})</option>`).join('');
      tplSel.onchange = () => applyAuthorTemplate(templates);
    });
  } else {
    tplSel.innerHTML = '<option value="">— ниша не задана, шаблоны недоступны —</option>';
    tplSel.onchange = null;
  }

  // Список писателей-референсов под нишу сайта
  const refSel = document.getElementById('ca-reference');
  bridge.getStyleReferences(niche_id || '', jsonStr => {
    let refs;
    try { refs = JSON.parse(jsonStr) || []; }
    catch(e) { refs = []; }
    refSel.innerHTML = '<option value="">— без референса —</option>' +
      refs.map(r => {
        const mark = r.has_extracted ? '✓ ' : '';
        return `<option value="${r.reference_id}">${mark}${escapeHtml(r.name)}</option>`;
      }).join('');
    refSel.onchange = () => applyReferenceStyle(refSel.value);
  });

  document.getElementById('modal-create-author').style.display = 'flex';
}

function applyReferenceStyle(reference_id) {
  const status = document.getElementById('ca-reference-status');
  _newAuthorContext.reference_id = reference_id || null;

  if (!reference_id) {
    status.textContent = '';
    return;
  }

  status.textContent = 'Извлекаю стилистику…';
  bridge.extractStyleForReference(reference_id, respStr => {
    let resp;
    try { resp = JSON.parse(respStr) || {}; }
    catch(e) { resp = {ok: false, error: 'Не удалось распарсить ответ'}; }
    if (!resp.ok) {
      status.textContent = '⚠ ' + (resp.error || 'не удалось извлечь стиль');
      return;
    }
    // Автозаполняем поля. Юзер при желании отредактирует.
    document.getElementById('ca-character').value = resp.character || '';
    if (resp.tone)      document.getElementById('ca-tone').value = resp.tone;
    if (resp.age_image) document.getElementById('ca-age').value  = resp.age_image;
    status.textContent = '✓ Стилистика подставлена. При желании отредактируй.';
  });
}

function applyAuthorTemplate(templates) {
  const id = document.getElementById('ca-template').value;
  if (!id) return;
  const t = templates.find(x => x.author_id === id);
  if (!t) return;
  // Заполняем поля по образцу. Имя оставляем пустым — оно должно быть уникальным.
  document.getElementById('ca-age').value = t.age_image || '';
  document.getElementById('ca-tone').value = t.tone || '';
  document.getElementById('ca-character').value = t.character || '';
}

function closeCreateAuthorModal() {
  document.getElementById('modal-create-author').style.display = 'none';
}

function submitCreateAuthor() {
  const name = document.getElementById('ca-name').value.trim();
  const age_image = document.getElementById('ca-age').value.trim();
  const tone = document.getElementById('ca-tone').value.trim();
  const character = document.getElementById('ca-character').value.trim();
  const errBox = document.getElementById('ca-error');
  errBox.style.display = 'none';

  if (!name) { errBox.textContent = 'Укажите имя'; errBox.style.display = 'block'; return; }
  if (!_newAuthorContext.site_domain) {
    errBox.textContent = 'Сайт не задан'; errBox.style.display = 'block'; return;
  }

  const payload = JSON.stringify({
    site_domain:  _newAuthorContext.site_domain,
    reference_id: _newAuthorContext.reference_id || null,
    name, age_image, tone, character
  });
  bridge.createAuthor(payload, respStr => {
    let resp;
    try { resp = JSON.parse(respStr) || {}; }
    catch(e) { resp = {ok: false, error: 'Не удалось распарсить ответ'}; }
    if (resp.ok) {
      closeCreateAuthorModal();
      loadSitesPage();
    } else {
      errBox.textContent = resp.error || 'Ошибка при создании';
      errBox.style.display = 'block';
    }
  });
}
