// ══════════ ANALYTICS PAGE ══════════
// JS-логика страницы «Аналитика»: сводка + три таблицы (сайты, ниши, архетипы).
// Подключается в main_window.py (содержимое подставляется в <script>).

function loadAnalyticsPage() {
  if (!bridge || !bridge.getAnalyticsData) {
    setTimeout(loadAnalyticsPage, 100);
    return;
  }
  const includeTest = document.getElementById('an-show-test').checked;
  bridge.getAnalyticsData(includeTest, jsonStr => {
    let data;
    try { data = JSON.parse(jsonStr) || {}; }
    catch(e) { data = {}; }
    if (data.error) {
      document.getElementById('an-summary').innerHTML =
        '<div style="color:#f38ba8">Ошибка: ' + escapeHtml(data.error) + '</div>';
      return;
    }
    renderAnalyticsSummary(data.summary || {});
    renderAnalyticsSites(data.sites || []);
    renderAnalyticsNiches(data.niches || []);
    renderAnalyticsArchetypes(data.archetypes || []);
  });
}

function _card(label, value) {
  return `
    <div style="background:#1e1e2e;border:1px solid #313244;border-radius:8px;padding:12px 16px">
      <div style="color:#6c7086;font-size:11px;text-transform:uppercase;letter-spacing:0.5px">${label}</div>
      <div style="font-size:22px;font-weight:600;margin-top:4px">${value}</div>
    </div>
  `;
}

function renderAnalyticsSummary(s) {
  const wrap = document.getElementById('an-summary');
  const totalCost = (s.total_cost || 0).toFixed(2);
  const avgCost   = (s.avg_cost   || 0).toFixed(3);
  wrap.innerHTML =
    _card('Всего статей', s.total_articles || 0) +
    _card('Средний QA', (s.avg_qa || 0)) +
    _card('Расход $', '$' + totalCost) +
    _card('Средняя цена', '$' + avgCost);
}

function _tableShell(rows) {
  if (!rows.length) {
    return '<div style="color:#6c7086;padding:12px 0;font-size:13px">Нет данных</div>';
  }
  return `
    <div style="background:#1e1e2e;border:1px solid #313244;border-radius:8px;overflow:hidden">
      <table style="width:100%;border-collapse:collapse">
        ${rows.join('')}
      </table>
    </div>
  `;
}

function _th(cols) {
  const cells = cols.map(c =>
    `<th style="text-align:left;padding:10px 16px;font-weight:600;color:#a6adc8;background:#181825;font-size:12px;text-transform:uppercase;letter-spacing:0.5px">${c}</th>`
  ).join('');
  return `<tr>${cells}</tr>`;
}

function _td(cells, dim = false) {
  const style = dim ? 'opacity:0.5;' : '';
  const tds = cells.map(c =>
    `<td style="padding:10px 16px;border-top:1px solid #313244;font-size:13px;${style}">${c}</td>`
  ).join('');
  return `<tr>${tds}</tr>`;
}

function renderAnalyticsSites(sites) {
  const rows = [_th(['Сайт', 'Статей', 'Средний QA', 'Расход $', 'Средняя цена'])];
  sites.forEach(s => {
    const label = escapeHtml(s.domain) +
      (s.is_test ? ' <span style="background:#45475a;color:#cdd6f4;font-size:10px;padding:1px 6px;border-radius:3px;margin-left:4px">тест</span>' : '');
    rows.push(_td([
      label,
      s.count,
      s.avg_qa || '—',
      '$' + (s.total_cost || 0).toFixed(2),
      '$' + (s.avg_cost || 0).toFixed(3),
    ], s.is_test));
  });
  document.getElementById('an-sites').innerHTML = _tableShell(rows);
}

function renderAnalyticsNiches(niches) {
  const rows = [_th(['Ниша', 'Статей', 'Средний QA', 'Средняя цена'])];
  niches.forEach(n => {
    rows.push(_td([
      escapeHtml(n.name),
      n.count,
      n.avg_qa || '—',
      '$' + (n.avg_cost || 0).toFixed(3),
    ]));
  });
  document.getElementById('an-niches').innerHTML = _tableShell(rows);
}

function renderAnalyticsArchetypes(archetypes) {
  const rows = [_th(['Архетип', 'Статей', 'Совпадение с предложением', 'Средний QA'])];
  archetypes.forEach(a => {
    const match = a.match_pct != null ? a.match_pct + '%' : '—';
    rows.push(_td([
      escapeHtml(a.name),
      a.count,
      match,
      a.avg_qa || '—',
    ]));
  });
  document.getElementById('an-archetypes').innerHTML = _tableShell(rows);
}
