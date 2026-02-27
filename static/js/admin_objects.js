/* admin_objects.js

Admin page: /admin/objects
- list objects
- search/filter
- export CSV/XLSX
- import CSV/XLSX (optionally dry-run)
- download templates
- quick actions: show on map, edit, create incident

No frameworks, vanilla JS.
*/

(function(){
  'use strict';

  const params = new URLSearchParams(window.location.search || '');
  const HIGHLIGHT_ID = (params.get('highlight') || '').trim();

  const elQ = document.getElementById('flt-q');
  const elTag = document.getElementById('flt-tag');
  const elBtnApply = document.getElementById('btn-apply');
  const elBtnClear = document.getElementById('btn-clear');

  const elBtnExportCsv = document.getElementById('btn-export-csv');
  const elBtnExportXlsx = document.getElementById('btn-export-xlsx');
  const elBtnTplCsv = document.getElementById('btn-template-csv');
  const elBtnTplXlsx = document.getElementById('btn-template-xlsx');

  const elBtnImport = document.getElementById('btn-import');
  const elInpImport = document.getElementById('inp-import');
  const elDry = document.getElementById('chk-dryrun');

  const elCount = document.getElementById('count');
  const elErr = document.getElementById('err');
  const elLoading = document.getElementById('loading');
  const elTbody = document.querySelector('#tbl tbody');

  function esc(s){
    return String(s ?? '').replace(/[&<>"]|'/g, (c)=>({
      '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
    }[c]));
  }

  function showLoading(on, text){
    if(!elLoading) return;
    elLoading.style.display = on ? 'block' : 'none';
    if(text != null) elLoading.textContent = text;
  }

  function showError(html){
    if(!elErr) return;
    if(!html){
      elErr.style.display = 'none';
      elErr.innerHTML = '';
      return;
    }
    elErr.style.display = 'block';
    elErr.innerHTML = html;
  }

  async function fetchJson(url, opts){
    const r = await fetch(url, Object.assign({ credentials: 'include' }, (opts||{})));
    const t = await r.text();
    let data = null;
    try{ data = t ? JSON.parse(t) : null; }catch(e){ data = t; }
    if(!r.ok){
      const msg = (data && data.error) ? data.error : ('HTTP ' + r.status);
      const err = new Error(msg);
      err.data = data;
      err.status = r.status;
      throw err;
    }
    return data;
  }

  async function postForm(url, fd){
    // csrf.js patches fetch in this project (adds X-CSRFToken). We keep it simple.
    return fetchJson(url, { method: 'POST', body: fd });
  }

  function buildExportUrl(ext, template=false){
    const q = (elQ?.value || '').trim();
    const tag = (elTag?.value || '').trim();
    const base = template ? `/api/objects/export/template.${ext}` : `/api/objects/export/objects.${ext}`;
    const u = new URL(base, window.location.origin);
    if(!template){
      if(q) u.searchParams.set('q', q);
      if(tag) u.searchParams.set('tag', tag);
    }
    return u.toString();
  }

  function highlightRow(id){
    if(!id) return;
    const tr = document.querySelector(`tr[data-id="${CSS.escape(String(id))}"]`);
    if(!tr) return;
    tr.classList.add('row-highlight');
    try{ tr.scrollIntoView({ block:'center', behavior:'smooth' }); }catch(_){ try{ tr.scrollIntoView(true); }catch(__){} }
  }

  function render(items){
    if(!elTbody) return;
    elTbody.innerHTML = '';

    const count = Array.isArray(items) ? items.length : 0;
    if(elCount) elCount.textContent = String(count);

    if(!items || !items.length){
      const tr = document.createElement('tr');
      tr.innerHTML = `<td colspan="6" class="muted small">Нет объектов. Нажмите «Создать на карте» или импортируйте CSV/XLSX.</td>`;
      elTbody.appendChild(tr);
      return;
    }

    for(const it of items){
      const id = it.id;
      const name = it.name || '';
      const tags = it.tags || '';
      const lat = it.lat;
      const lon = it.lon;
      const cams = Array.isArray(it.cameras) ? it.cameras.length : 0;

      const tr = document.createElement('tr');
      tr.dataset.id = String(id);
      tr.innerHTML = `
        <td><span class="badge">${esc(id)}</span></td>
        <td>
          <div style="font-weight:700">${esc(name)}</div>
          <div class="muted small">${esc(it.description || '')}</div>
        </td>
        <td>${esc(tags)}</td>
        <td class="muted small">${esc((lat ?? '—') + ', ' + (lon ?? '—'))}</td>
        <td>${cams ? `<span class="badge">${cams}</span>` : '—'}</td>
        <td>
          <div class="row" style="gap:8px;flex-wrap:wrap">
            <a class="btn" href="/admin/panel?focus_object=${encodeURIComponent(id)}" title="Показать на карте"><i class="fa-solid fa-location-crosshairs"></i> Карта</a>
            <a class="btn" href="/admin/panel?edit_object=${encodeURIComponent(id)}" title="Редактировать"><i class="fa-solid fa-pen"></i> Редакт</a>
            <button class="btn warn" type="button" data-act="incident" title="Создать инцидент от объекта"><i class="fa-solid fa-triangle-exclamation"></i> Инцидент</button>
          </div>
        </td>
      `;
      elTbody.appendChild(tr);
    }

    if(HIGHLIGHT_ID) highlightRow(HIGHLIGHT_ID);
  }

  async function load(){
    showError('');
    showLoading(true, 'Загрузка…');

    const q = (elQ?.value || '').trim();
    const tag = (elTag?.value || '').trim();
    const u = new URL('/api/objects', window.location.origin);
    if(q) u.searchParams.set('q', q);
    if(tag) u.searchParams.set('tag', tag);
    u.searchParams.set('limit', '500');

    try{
      const data = await fetchJson(u.toString());
      render(Array.isArray(data) ? data : []);
    }catch(e){
      render([]);
      showError(`<b>Ошибка загрузки:</b> ${esc(e.message || e)}`);
    }finally{
      showLoading(false);
    }
  }

  async function createIncident(objectId){
    showError('');
    showLoading(true, 'Создаю инцидент…');
    try{
      const obj = await fetchJson('/api/objects/' + encodeURIComponent(objectId));
      const payload = {
        object_id: Number(objectId),
        lat: obj?.lat,
        lon: obj?.lon,
        address: obj?.name || obj?.address || ('Объект #' + objectId),
        description: (obj?.description || '') || 'Инцидент создан из объекта',
        priority: 3,
        status: 'new'
      };
      const res = await fetchJson('/api/incidents', {
        method: 'POST',
        headers: { 'Content-Type':'application/json' },
        body: JSON.stringify(payload),
      });
      const id = res?.id;
      if(id){
        window.location.href = '/admin/incidents/' + encodeURIComponent(id);
      }else{
        showError('<b>Инцидент создан</b>, но id не получен');
      }
    }catch(e){
      showError(`<b>Ошибка создания инцидента:</b> ${esc(e.message || e)}`);
    }finally{
      showLoading(false);
    }
  }

  function renderImportErrors(errors){
    if(!errors || !errors.length) return '';
    const rows = errors.slice(0, 20).map(er => {
      const row = esc(er.row);
      const msg = esc(er.error);
      return `<li><code>row ${row}</code>: ${msg}</li>`;
    }).join('');
    const more = errors.length > 20 ? `<div class="muted small">Показаны первые 20 ошибок из ${esc(errors.length)}</div>` : '';
    return `<div style="margin-top:8px"><b>Ошибки:</b><ul style="margin:6px 0 0 18px">${rows}</ul>${more}</div>`;
  }

  async function doImport(file){
    if(!file) return;

    const dry = !!(elDry && elDry.checked);
    const url = dry ? '/api/objects/import?dry_run=1' : '/api/objects/import';

    const fd = new FormData();
    fd.append('file', file);

    showError('');
    showLoading(true, dry ? 'Проверяю файл (dry-run)…' : 'Импорт…');

    try{
      const res = await postForm(url, fd);
      const created = Number(res?.created ?? 0);
      const updated = Number(res?.updated ?? 0);
      const errorsCount = Number(res?.errors_count ?? 0);
      const dryRun = !!res?.dry_run;

      let html = `<b>${dryRun ? 'Dry-run:' : 'Импорт:'}</b> created=${created}, updated=${updated}, errors=${errorsCount}`;
      if(errorsCount){
        html += renderImportErrors(res?.errors || []);
      }else{
        html += `<div class="muted small" style="margin-top:6px">${dryRun ? 'Ошибок нет. Можно снять Dry-run и импортировать.' : 'Готово.'}</div>`;
      }
      showError(html);

      if(!dryRun){
        await load();
      }
    }catch(e){
      showError(`<b>Ошибка импорта:</b> ${esc(e.message || e)}`);
    }finally{
      showLoading(false);
    }
  }

  function bind(){
    elBtnApply?.addEventListener('click', (ev)=>{ ev.preventDefault(); load(); });
    elBtnClear?.addEventListener('click', (ev)=>{
      ev.preventDefault();
      if(elQ) elQ.value = '';
      if(elTag) elTag.value = '';
      load();
    });

    elQ?.addEventListener('keydown', (ev)=>{ if(ev.key === 'Enter'){ load(); } });
    elTag?.addEventListener('keydown', (ev)=>{ if(ev.key === 'Enter'){ load(); } });

    elBtnExportCsv?.addEventListener('click', (ev)=>{ ev.preventDefault(); window.location.href = buildExportUrl('csv'); });
    elBtnExportXlsx?.addEventListener('click', (ev)=>{ ev.preventDefault(); window.location.href = buildExportUrl('xlsx'); });

    elBtnTplCsv?.addEventListener('click', (ev)=>{ ev.preventDefault(); window.location.href = buildExportUrl('csv', true); });
    elBtnTplXlsx?.addEventListener('click', (ev)=>{ ev.preventDefault(); window.location.href = buildExportUrl('xlsx', true); });

    elBtnImport?.addEventListener('click', (ev)=>{ ev.preventDefault(); elInpImport?.click(); });

    elInpImport?.addEventListener('change', async ()=>{
      const f = elInpImport.files && elInpImport.files[0];
      await doImport(f);
      elInpImport.value = '';
    });

    document.getElementById('tbl')?.addEventListener('click', (ev)=>{
      const btn = ev.target?.closest?.('button[data-act="incident"]');
      if(!btn) return;
      const tr = btn.closest('tr');
      const id = tr?.dataset?.id;
      if(!id) return;
      ev.preventDefault();
      createIncident(id);
    });
  }

  function init(){
    bind();
    load();
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  }else{
    init();
  }
})();
