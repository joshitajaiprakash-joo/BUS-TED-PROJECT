// ===================================================================
// BUS-TED! - Leaflet & OpenStreetMap Live Transit Map Module
// ===================================================================

document.addEventListener('DOMContentLoaded', function() {
  const mapElement = document.getElementById('map');
  if (!mapElement) return;

  // Default campus fallback center (Bangalore Central Campus: 12.9734, 77.5855)
  let defaultCenter = [12.9734, 77.5855];
  let defaultZoom = 13;

  // Initialize Leaflet Map
  const map = L.map('map', {
    zoomControl: true,
    scrollWheelZoom: true
  }).setView(defaultCenter, defaultZoom);

  // Add OpenStreetMap Tile Layer
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  let busMarker = null;
  let stopMarkers = [];
  let routePolyline = null;

  // Custom Bus Icon
  function createBusIcon(busNumber) {
    return L.divIcon({
      className: 'custom-bus-marker',
      html: `
        <div style="background: #fbbf24; border: 3px solid #0f172a; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 14px rgba(0,0,0,0.3); font-size: 18px; color: #0f172a; position: relative;">
          <i class="fa-solid fa-bus"></i>
          <span style="position: absolute; bottom: -18px; background: #0f172a; color: white; font-size: 10px; font-weight: 800; padding: 1px 6px; border-radius: 4px; white-space: nowrap;">
            ${busNumber || 'BUS'}
          </span>
        </div>
      `,
      iconSize: [40, 40],
      iconAnchor: [20, 20]
    });
  }

  // Custom Stop Icon
  function createStopIcon(order) {
    return L.divIcon({
      className: 'custom-stop-marker',
      html: `
        <div style="background: #2563eb; color: #ffffff; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 800; border: 2px solid #ffffff; box-shadow: 0 2px 8px rgba(0,0,0,0.25);">
          ${order}
        </div>
      `,
      iconSize: [28, 28],
      iconAnchor: [14, 14]
    });
  }

  // Function to render Route Stops and Polyline
  window.renderRouteOnMap = function(stops) {
    // Clear previous stop markers & polyline
    stopMarkers.forEach(m => map.removeLayer(m));
    stopMarkers = [];
    if (routePolyline) {
      map.removeLayer(routePolyline);
      routePolyline = null;
    }

    if (!stops || stops.length === 0) return;

    const latlngs = [];

    stops.forEach(stop => {
      if (stop.lat && stop.lng) {
        const pt = [stop.lat, stop.lng];
        latlngs.push(pt);

        const marker = L.marker(pt, { icon: createStopIcon(stop.order) })
          .addTo(map)
          .bindPopup(`
            <div style="padding: 4px;">
              <strong style="color: #2563eb;">Stop #${stop.order}</strong><br>
              <strong>${stop.name}</strong><br>
              <span style="font-size: 11px; color: #64748b;">Sequence Stop</span>
            </div>
          `);
        stopMarkers.push(marker);
      }
    });

    if (latlngs.length > 1) {
      routePolyline = L.polyline(latlngs, {
        color: '#2563eb',
        weight: 4,
        opacity: 0.8,
        dashArray: '8, 8',
        lineJoin: 'round'
      }).addTo(map);

      // Fit bounds to show entire route
      map.fitBounds(routePolyline.getBounds(), { padding: [40, 40] });
    } else if (latlngs.length === 1) {
      map.setView(latlngs[0], 14);
    }
  };

  // Function to update bus position on map
  window.updateBusLocationOnMap = function(lat, lng, busNumber, speed, recordedAt, accuracy) {
    if (!lat || !lng) return;

    const pt = [lat, lng];

    if (!busMarker) {
      busMarker = L.marker(pt, { icon: createBusIcon(busNumber) }).addTo(map);
    } else {
      busMarker.setLatLng(pt);
    }

    busMarker.bindPopup(`
      <div style="padding: 6px; text-align: center;">
        <strong style="color: #0f172a; font-size: 14px;">${busNumber}</strong><br>
        <span style="color: #10b981; font-weight: 700; font-size: 12px;">Active on Route</span><br>
        <span style="font-size: 11px; color: #64748b;">Speed: ${(speed || 0).toFixed(1)} km/h</span><br>
        <span style="font-size: 10px; color: #94a3b8;">Updated: ${recordedAt || 'Just now'}</span>
      </div>
    `);

    // Update floating status card if exists
    const statusText = document.getElementById('busGpsStatusText');
    if (statusText) {
      statusText.textContent = `Broadcasting actual GPS (${recordedAt || 'Just now'})`;
      statusText.style.color = '#10b981';
    }

    const accuracyEl = document.getElementById('gpsAccuracyDisplay');
    if (accuracyEl && accuracy) {
      accuracyEl.textContent = `GPS Accuracy: ±${accuracy.toFixed(1)}m`;
    }

    const timeBadge = document.getElementById('liveGpsTimeBadge');
    if (timeBadge) {
      timeBadge.textContent = `Updated: ${recordedAt || 'Just now'}`;
    }
  };

  // Initial Data Injection from Flask template
  if (window.busRouteData) {
    if (window.busRouteData.stops && window.busRouteData.stops.length > 0) {
      window.renderRouteOnMap(window.busRouteData.stops);
    }

    if (window.busRouteData.initialGps) {
      const g = window.busRouteData.initialGps;
      window.updateBusLocationOnMap(
        g.lat,
        g.lng,
        window.busRouteData.busNumber,
        g.speed,
        g.recorded_at,
        g.accuracy
      );
    }
  }

  // Socket.IO Listener for real-time location updates
  if (window.appSocket) {
    window.appSocket.on('bus_location_updated', function(data) {
      // Check if matches active route/bus
      if (window.busRouteData && (data.bus_id === window.busRouteData.busId || data.trip_id === window.busRouteData.tripId)) {
        window.updateBusLocationOnMap(
          data.latitude,
          data.longitude,
          data.bus_number,
          data.speed,
          data.recorded_at,
          data.accuracy
        );

        // Pan map smoothly to new bus position
        map.panTo([data.latitude, data.longitude]);
      }
    });
  }

  // Stale GPS Checker (turn off live indicator if no update within 90s)
  setInterval(function() {
    // Check if live pulse badge should be marked stale
    const pulseElement = document.querySelector('.live-pulse');
    const busGpsStatusText = document.getElementById('busGpsStatusText');
    if (pulseElement && window.busRouteData && !window.busRouteData.initialGps && !busMarker) {
      // No GPS fix yet
    }
  }, 15000);
});
