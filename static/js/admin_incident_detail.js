/* admin_incident_detail.js — страница подробностей инцидента

   Загружает данные инцидента, отображает адрес, описание,
   приоритет, статус, камеры, назначение и таймлайн событий.
   Позволяет назначить активный наряд и отправлять изменения
   статуса реакции. Для этого используются соответствующие
   API (/api/incidents/<id>, /api/incidents/<id>/assign, /api/incidents/<id>/status,
   /api/incidents/<id>/events) и список активных смен из
   /api/duty/admin/dashboard.
*/

(function(){
  'use strict';

  // Получаем идентификатор инцидента из дата-атрибута
  const incMain = document.getElementById('inc-main');
  if(!incMain) return;
  const incidentId = incMain.dataset.incidentId;

  // DOM элементы
  const elAddress = document.getElementById('inc-address');
  const elStatus = document.getElementById('inc-status');
  const elKv = document.getElementById('inc-kv');
  const elDesc = document.getElementById('inc-desc');
  const elCams = document.getElementById('inc-cameras');
  const elAssignActions = document.getElementById('inc-assign-actions');
  const elEvents = document.getElementById('inc-events');
  const elRefresh = document.getElementById('inc-refresh');
  const elToast = document.getElementById('toast');

  // Элемент для отображения назначений и SLA
  const elAssignments = document.getElementById('inc-assignments');

  // CSRF токен
  const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

  // Показать всплывающее уведомление
  function showToast(msg, type){
    if(!elToast) return;
    elToast.textContent = msg;
    elToast.className = 'adm-toast ' + (type || '');
    elToast.style.display = 'block';
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => { elToast.style.display = 'none'; }, 3200);
  }

  function escapeHtml(s){
    return String(s ?? '')
      .replaceAll('&','&amp;')
      .replaceAll('<','&lt;')
      .replaceAll('>','&gt;')
      .replaceAll('"','&quot;')
      .replaceAll("'", '&#39;');
  }

  /**
   * Загружаем детали инцидента и отображаем.
   */
  async function loadIncident(){
    elAddress.textContent = '…';
    elStatus.textContent = '…';
    elKv.innerHTML = '';
    elDesc.textContent = '';
    elCams.innerHTML = '';
    elAssignActions.innerHTML = '';
    try{
      const res = await fetch(`/api/incidents/${incidentId}`, { credentials:'same-origin' });
      if(!res.ok){
        const data = await res.json().catch(() => ({}));
        throw { status: res.status, data };
      }
      const data = await res.json();
      renderIncident(data);
    }catch(e){
      console.error(e);
      showToast('Ошибка загрузки инцидента', 'error');
    }
  }

  /**
   * Отрисовать данные инцидента.
   * @param {Object} inc
   */
  function renderIncident(inc){
    // Адрес или координаты
    if(inc.address){
      elAddress.textContent = inc.address;
    }else if(inc.lat != null && inc.lon != null){
      elAddress.textContent = `[${Number(inc.lat).toFixed(5)}, ${Number(inc.lon).toFixed(5)}]`;
    }else{
      elAddress.textContent = '—';
    }
    // Статус с тегом
    const stat = inc.status || 'new';
    const tag = document.createElement('span');
    tag.className = 'tag tag-status-' + stat;
    tag.textContent = stat.replace('_',' ');
    elStatus.innerHTML = '';
    elStatus.appendChild(tag);
    // Приоритет
    const kvParts = [];
    kvParts.push(`<b>ID:</b> ${inc.id}`);
    if(inc.priority){
      kvParts.push(`<b>Priority:</b> <span class="tag tag-priority-${inc.priority}">P${inc.priority}</span>`);
    }
    if(inc.created_at){
      kvParts.push(`<b>Created:</b> ${escapeHtml(inc.created_at.replace('T',' '))}`);
    }
    if(inc.updated_at){
      kvParts.push(`<b>Updated:</b> ${escapeHtml(inc.updated_at.replace('T',' '))}`);
    }
    elKv.innerHTML = kvParts.join(' &nbsp; | &nbsp; ');
    // Описание
    elDesc.textContent = inc.description || '—';
    // Камеры: из связанного объекта
    elCams.innerHTML = '';
    const cams = [];
    if(inc.object && inc.object.cameras){
      for(const cam of inc.object.cameras){
        cams.push(cam);
      }
    }
    if(cams.length > 0){
      for(const cam of cams){
        const div = document.createElement('div');
        div.className = 'inc-cam';
        const link = document.createElement('a');
        link.href = cam.url;
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = cam.label || cam.url;
        div.appendChild(link);
        elCams.appendChild(div);
      }
    }
    // Назначение и статус реакций
    renderAssignSection(inc);
  }

  /**
   * Загрузить события инцидента и отобразить.
   */
  async function loadEvents(){
    elEvents.textContent = 'Загрузка…';
    try{
      const res = await fetch(`/api/incidents/${incidentId}/events`, { credentials:'same-origin' });
      if(!res.ok){
        const data = await res.json().catch(() => ({}));
        throw { status: res.status, data };
      }
      const items = await res.json();
      renderEvents(items);
    }catch(e){
      console.error(e);
      showToast('Ошибка загрузки таймлайна', 'error');
      elEvents.textContent = 'Ошибка загрузки';
    }
  }

  /**
   * Отрисовать события.
   * @param {Array} events
   */
  function renderEvents(events){
    if(!events || events.length === 0){
      elEvents.textContent = 'Нет событий';
      return;
    }
    elEvents.innerHTML = '';
    for(const ev of events){
      const div = document.createElement('div');
      div.className = 'inc-event';
      const typeSpan = document.createElement('span');
      typeSpan.className = 'inc-ev-type';
      typeSpan.textContent = ev.event_type;
      const tsSpan = document.createElement('span');
      tsSpan.className = 'inc-ev-ts';
      tsSpan.textContent = ev.ts ? ev.ts.replace('T',' ') : '';
      // payload: stringify for now
      const payloadSpan = document.createElement('span');
      payloadSpan.className = 'inc-ev-payload';
      const payload = ev.payload || {};
      const payloadParts = [];
      for(const k in payload){
        if(Object.hasOwn(payload,k)){
          payloadParts.push(`${k}: ${String(payload[k])}`);
        }
      }
      payloadSpan.textContent = payloadParts.length ? ` (${payloadParts.join(', ')})` : '';
      div.appendChild(typeSpan);
      div.appendChild(tsSpan);
      div.appendChild(payloadSpan);
      elEvents.appendChild(div);
    }
  }

  /**
   * Отрисовать блок назначения/управления статусами.
   * @param {Object} inc
   */
  async function renderAssignSection(inc){
    elAssignActions.innerHTML = '';
    // Если назначений нет — показать список активных смен и кнопку назначить
    const assignments = inc.assignments || [];
    if(assignments.length === 0){
      // Сформировать селект активных смен
      const { shifts, error } = await fetchActiveShifts();
      if(error){
        const err = document.createElement('div');
        err.className = 'muted';
        err.textContent = 'Нет данных о сменах';
        elAssignActions.appendChild(err);
        return;
      }
      if(!shifts || shifts.length === 0){
        const div = document.createElement('div');
        div.className = 'muted';
        div.textContent = 'Нет активных смен';
        elAssignActions.appendChild(div);
        return;
      }
      const sel = document.createElement('select');
      sel.className = 'input';
      sel.style.height = '34px';
      for(const sh of shifts){
        const opt = document.createElement('option');
        opt.value = sh.shift_id;
        opt.textContent = `${sh.unit_label || sh.user_id || 'Shift ' + sh.shift_id}`;
        sel.appendChild(opt);
      }
      const btnAssign = document.createElement('button');
      btnAssign.className = 'btn primary';
      btnAssign.type = 'button';
      btnAssign.textContent = 'Назначить';
      btnAssign.onclick = async () => {
        const shiftId = Number(sel.value);
        if(!shiftId) return;
        try{
          const resp = await fetch(`/api/incidents/${incidentId}/assign`, {
            method:'POST',
            headers:{
              'Content-Type':'application/json',
              'X-CSRFToken': csrfToken,
            },
            credentials:'same-origin',
            body: JSON.stringify({ shift_id: shiftId })
          });
          if(!resp.ok){
            const data = await resp.json().catch(() => ({}));
            throw { status: resp.status, data };
          }
          showToast('Наряд назначен', 'ok');
          await reload();
        }catch(e){
          console.error(e);
          showToast('Ошибка назначения', 'error');
        }
      };
      elAssignActions.appendChild(sel);
      elAssignActions.appendChild(btnAssign);
    }else{
      // Есть назначение: покажем информацию о наряде и кнопки статуса
      // Будем использовать первое назначение (для MVP)
      const ass = assignments[0];
      // Отобразим shift label
      const shiftLabelEl = document.createElement('div');
      shiftLabelEl.className = 'muted';
      shiftLabelEl.style.marginBottom = '4px';
      shiftLabelEl.textContent = `Наряд: ${ass.shift_id}`;
      elAssignActions.appendChild(shiftLabelEl);
      // Кнопки статусов (accepted, enroute, on_scene, resolved, closed)
      const statuses = [
        { key:'accepted', label:'Принято' },
        { key:'enroute', label:'В пути' },
        { key:'on_scene', label:'На месте' },
        { key:'resolved', label:'Завершено' },
        { key:'closed', label:'Закрыто' },
      ];
      const btnsDiv = document.createElement('div');
      btnsDiv.className = 'inc-status-buttons';
      btnsDiv.style.display = 'flex';
      btnsDiv.style.flexWrap = 'wrap';
      btnsDiv.style.gap = '6px';
      for(const st of statuses){
        const b = document.createElement('button');
        b.className = 'btn';
        b.type = 'button';
        b.textContent = st.label;
        // Disable button if status already reached
        if(ass[`${st.key}_at`]){
          b.disabled = true;
          b.classList.add('muted');
        }
        b.onclick = async () => {
          await updateStatus(ass.shift_id, st.key);
        };
        btnsDiv.appendChild(b);
      }
      elAssignActions.appendChild(btnsDiv);
    }
  }

  /**
   * Загрузить список активных смен.
   * @returns {Promise<{shifts:Array, error:boolean}>}
   */
  async function fetchActiveShifts(){
    try{
      const res = await fetch('/api/duty/admin/dashboard', { credentials:'same-origin' });
      if(!res.ok){
        return { shifts: [], error: true };
      }
      const data = await res.json();
      const shifts = data.active_shifts || [];
      return { shifts, error: false };
    }catch(e){
      return { shifts: [], error: true };
    }
  }

  /**
   * Обновить статус реакции на инцидент.
   * @param {number} shiftId
   * @param {string} status
   */
  async function updateStatus(shiftId, status){
    try{
      const resp = await fetch(`/api/incidents/${incidentId}/status`, {
        method:'POST',
        headers:{
          'Content-Type':'application/json',
          'X-CSRFToken': csrfToken,
        },
        credentials:'same-origin',
        body: JSON.stringify({ shift_id: shiftId, status })
      });
      if(!resp.ok){
        const data = await resp.json().catch(() => ({}));
        throw { status: resp.status, data };
      }
      showToast('Статус обновлён', 'ok');
      await reload();
    }catch(e){
      console.error(e);
      showToast('Ошибка смены статуса', 'error');
    }
  }

  /**
   * Перезагрузка инцидента и событий.
   */
  async function reload(){
    await loadIncident();
    await loadEvents();
    await loadAssignments();
  }

  /**
   * Загрузить назначения и SLA по инциденту.
   */
  async function loadAssignments(){
    if(!elAssignments) return;
    elAssignments.textContent = 'Загрузка…';
    try{
      const res = await fetch(`/api/incidents/${incidentId}/assignments`, { credentials:'same-origin' });
      if(!res.ok){ throw new Error('bad'); }
      const items = await res.json();
      renderAssignments(Array.isArray(items) ? items : []);
    }catch(e){
      console.error(e);
      elAssignments.textContent = 'Ошибка загрузки';
    }
  }

  /**
   * Отрисовать назначения и SLA.
   * @param {Array} items
   */
  function renderAssignments(items){
    if(!elAssignments) return;
    if(!items || items.length === 0){
      elAssignments.textContent = 'Нет назначений';
      return;
    }
    elAssignments.innerHTML = '';
    const now = new Date();
    items.forEach((ass) => {
      const wrapper = document.createElement('div');
      let breach = ass.sla_accept_breach || ass.sla_enroute_breach || ass.sla_onscene_breach;
      wrapper.className = 'inc-assign' + (breach ? ' sla-breach' : '');
      // Заголовок: shift
      const headRow = document.createElement('div');
      headRow.className = 'inc-assign-row';
      const headLbl = document.createElement('span');
      headLbl.className = 'inc-assign-label';
      headLbl.textContent = `Наряд: ${ass.shift_id}`;
      headRow.appendChild(headLbl);
      wrapper.appendChild(headRow);
      // helper to format diff
      function formatDiff(startIso, endIso){
        if(!startIso) return '';
        const start = new Date(startIso);
        const end = endIso ? new Date(endIso) : now;
        const diffSec = Math.max(0, (end - start) / 1000);
        const diffMin = Math.floor(diffSec / 60);
        return diffMin + ' мин';
      }
      // Принятие
      const rowAccept = document.createElement('div');
      rowAccept.className = 'inc-assign-row';
      const lblAccept = document.createElement('span');
      lblAccept.className = 'inc-assign-label';
      lblAccept.textContent = 'Принятие:';
      rowAccept.appendChild(lblAccept);
      const valAccept = document.createElement('span');
      if(ass.accepted_at){
        valAccept.textContent = 'ок';
      }else{
        valAccept.textContent = formatDiff(ass.assigned_at, ass.accepted_at);
      }
      rowAccept.appendChild(valAccept);
      if(ass.sla_accept_breach) rowAccept.classList.add('sla-breach');
      wrapper.appendChild(rowAccept);
      // В пути
      const rowEnroute = document.createElement('div');
      rowEnroute.className = 'inc-assign-row';
      const lblEnroute = document.createElement('span');
      lblEnroute.className = 'inc-assign-label';
      lblEnroute.textContent = 'В пути:';
      rowEnroute.appendChild(lblEnroute);
      const valEnroute = document.createElement('span');
      if(ass.enroute_at){
        valEnroute.textContent = 'ок';
      }else{
        // Если принято, считаем от accepted_at, иначе от assigned_at
        const start = ass.accepted_at || ass.assigned_at;
        valEnroute.textContent = formatDiff(start, ass.enroute_at);
      }
      rowEnroute.appendChild(valEnroute);
      if(ass.sla_enroute_breach) rowEnroute.classList.add('sla-breach');
      wrapper.appendChild(rowEnroute);
      // На месте
      const rowOnScene = document.createElement('div');
      rowOnScene.className = 'inc-assign-row';
      const lblOnScene = document.createElement('span');
      lblOnScene.className = 'inc-assign-label';
      lblOnScene.textContent = 'На месте:';
      rowOnScene.appendChild(lblOnScene);
      const valOnScene = document.createElement('span');
      if(ass.on_scene_at){
        valOnScene.textContent = 'ок';
      }else{
        const start = ass.enroute_at || ass.accepted_at || ass.assigned_at;
        valOnScene.textContent = formatDiff(start, ass.on_scene_at);
      }
      rowOnScene.appendChild(valOnScene);
      if(ass.sla_onscene_breach) rowOnScene.classList.add('sla-breach');
      wrapper.appendChild(rowOnScene);
      elAssignments.appendChild(wrapper);
    });
  }

  // Назначаем обработчик для кнопки обновления
  if(elRefresh){
    elRefresh.addEventListener('click', () => { reload(); });
  }

  // Инициализация: загружаем данные
  reload();
})();