/* ========= Map core (Leaflet) ========= */
/**
 * Инициализация карты и базовых слоёв.
 * Заводит глобальное окно initMap(), которое использует:
 *  - map, markersCluster, zonesLayer, drawnItems
 *  - CURRENT_ROLE, refresh, renderQuickCounters, ensureContextMenu, openMapMenu, openAdd, showToast
 */
(function() {
  function initMap() {
      const mapEl = $('#map');
      if (!mapEl) {
        console.error('#map element not found');
        return;
      }

      // Начальный центр и зум карты берём из data-атрибутов (конфиг сервера) или localStorage
      const mapContainer = document.getElementById('map');
      const savedLat = parseFloat(localStorage.getItem('map_last_lat'));
      const savedLng = parseFloat(localStorage.getItem('map_last_lng'));
      const savedZoom = parseInt(localStorage.getItem('map_last_zoom'));

      const defaultLat = parseFloat(mapContainer?.dataset?.defaultLat || window.MAP_DEFAULT_LAT || '53.9');
      const defaultLng = parseFloat(mapContainer?.dataset?.defaultLng || window.MAP_DEFAULT_LNG || '27.55');
      const defaultZoom = parseInt(mapContainer?.dataset?.defaultZoom || window.MAP_DEFAULT_ZOOM || '12');

      const initLat = (isFinite(savedLat) && savedLat !== 0) ? savedLat : defaultLat;
      const initLng = (isFinite(savedLng) && savedLng !== 0) ? savedLng : defaultLng;
      const initZoom = (isFinite(savedZoom) && savedZoom > 0) ? savedZoom : defaultZoom;

      // создаём карту
      map = L.map('map').setView([initLat, initLng], initZoom);

      // Сохраняем позицию при перемещении
      map.on('moveend zoomend', () => {
        try {
          const c = map.getCenter();
          localStorage.setItem('map_last_lat', c.lat.toFixed(6));
          localStorage.setItem('map_last_lng', c.lng.toFixed(6));
          localStorage.setItem('map_last_zoom', map.getZoom());
        } catch (_) {}
      });

      // ⬇️ ВАЖНО: убираем префикс "Leaflet" (и флажок) из атрибуции
      try { map.attributionControl.setPrefix(false); } catch (_) {}

      setTileSource('online');

      // Базовые слои
      const baseLayers = {
        'OSM': L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OSM contributors' }),
        'Тёмная': L.tileLayer('https://tiles.stadiamaps.com/tiles/alidade_dark/{z}/{x}/{y}{r}.png', { maxZoom: 19, attribution: '&copy; Stadia Maps & OSM' }),
        'Спутник': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19, attribution: 'Tiles © Esri' }),
      };
      baseLayers['OSM'].addTo(map);
      L.control.layers(baseLayers, null, { position:'topright' }).addTo(map);

      // Кластеры, зоны, drawControl — как было
      markersCluster = L.markerClusterGroup({
        disableClusteringAtZoom: 17,
        spiderfyOnMaxZoom: false,
        zoomToBoundsOnClick: true
      });
      map.addLayer(markersCluster);
      zonesLayer = L.featureGroup().addTo(map);

      drawControl = new L.Control.Draw({
        draw: {
          polygon: { showArea: true, allowIntersection: false, shapeOptions: { color: '#000000', weight: 2, fillOpacity: 0.15 } },
          marker: false, polyline: false, rectangle: false, circle: false, circlemarker: false
        },
        edit: { featureGroup: zonesLayer }
      });
      map.addControl(drawControl);

      map.on('draw:created', (e) => {
        if (e.layerType === 'polygon') {
          _pendingZoneLayer = e.layer;
          zonesLayer.addLayer(_pendingZoneLayer);
          openZoneModalForNew();
        }
      });
      map.on('draw:edited', (e) => {
        e.layers.eachLayer(layer => { if (layer instanceof L.Polygon && layer.zoneId) updateZoneToServer(layer); });
        saveZonesToLocal();
      });
      map.on('draw:deleted', (e) => {
        e.layers.eachLayer(layer => { if (layer.zoneId) deleteZoneFromServer(layer.zoneId); });
        saveZonesToLocal();
      });

      loadZonesFromServer().catch(err => console.error(err));
      zonesLayer.on('click', (e) => {
        const layer = e.layer;
        if (layer instanceof L.Polygon) openZoneModalForEdit(layer);
        else if (layer instanceof L.Marker) {
          const zid = layer.zoneId;
          if (zid && zonePolygonMap[zid]) openZoneModalForEdit(zonePolygonMap[zid]);
        }
      });

      // Правый клик — контекст‑меню
      ensureContextMenu();
      map.on('contextmenu', (e) => {
        try {
          // ВАЖНО: e.containerPoint — координаты внутри контейнера карты.
          // Меню у нас рисуется как position:fixed (координаты viewport),
          // поэтому берём clientX/clientY, иначе меню уезжает влево/вверх
          // на величину сайдбара/топбара и визуально «пропадает».
          const oe = e && e.originalEvent ? e.originalEvent : null;
          let px = null;
          if (oe && isFinite(oe.clientX) && isFinite(oe.clientY)) {
            px = { x: oe.clientX, y: oe.clientY };
          } else {
            // Надёжный вариант без originalEvent: переводим containerPoint (внутри карты)
            // в координаты viewport для position:fixed меню.
            try {
              const r = map.getContainer().getBoundingClientRect();
              px = { x: r.left + e.containerPoint.x, y: r.top + e.containerPoint.y };
            } catch (_) {
              px = e.containerPoint;
            }
          }
          openMapMenu(px, e.latlng);
        } catch (err) {
          // если чего-то нет — напрямую открываем форму
          const lat = Number(e.latlng.lat.toFixed(6));
          const lon = Number(e.latlng.lng.toFixed(6));
          openAdd({ id: null, name: '', address: '', lat, lon, notes: '', description: '',
            status: 'Локальный доступ', link: '', category: 'Видеонаблюдение' });
          showToast(`Координаты подставлены: ${lat}, ${lon}`);
        }
      });
  }

  // Экспорт в глобальную область
  window.initMap = initMap;
})();
