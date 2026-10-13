// ===================================================================
// BUS-TED! - Driver GPS Geolocation & Real-time Broadcasting Module
// ===================================================================

let watchId = null;
let isBroadcasting = true;
let packetsSent = 0;
let lastGpsSendTime = 0;
const GPS_SEND_INTERVAL_MS = 3000; // Send updates at max 3s intervals to balance real-time & bandwidth

function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

function updateStatusBadge(status, text) {
  const pill = document.getElementById('broadcastStatusPill');
  if (!pill) return;

  if (status === 'active') {
    pill.style.background = '#ecfdf5';
    pill.style.color = '#065f46';
    pill.style.border = '1px solid #10b981';
    pill.innerHTML = '<span class="pulse-dot"></span> BROADCASTING LIVE';
  } else if (status === 'paused') {
    pill.style.background = '#fffbeb';
    pill.style.color = '#92400e';
    pill.style.border = '1px solid #fde68a';
    pill.textContent = 'BROADCAST PAUSED';
  } else if (status === 'error') {
    pill.style.background = '#fef2f2';
    pill.style.color = '#991b1b';
    pill.style.border = '1px solid #fecaca';
    pill.textContent = text || 'GPS PERMISSION DENIED';
  } else {
    pill.style.background = '#f1f5f9';
    pill.style.color = '#64748b';
    pill.textContent = text || 'INITIALIZING';
  }
}

function handleLocationSuccess(position) {
  if (!isBroadcasting) return;

  const lat = position.coords.latitude;
  const lng = position.coords.longitude;
  const accuracy = position.coords.accuracy;
  const speed = position.coords.speed ? (position.coords.speed * 3.6) : 0; // m/s to km/h
  const heading = position.coords.heading || 0;

  // Update telemetry display
  const dLat = document.getElementById('dispLat');
  const dLng = document.getElementById('dispLng');
  const dAcc = document.getElementById('dispAccuracy');
  const dSpd = document.getElementById('dispSpeed');
  const dPkt = document.getElementById('dispCount');
  const dTime = document.getElementById('lastPacketTime');

  if (dLat) dLat.textContent = lat.toFixed(6);
  if (dLng) dLng.textContent = lng.toFixed(6);
  if (dAcc) dAcc.textContent = `${accuracy.toFixed(1)} m`;
  if (dSpd) dSpd.textContent = `${speed.toFixed(1)} km/h`;

  const now = Date.now();

  // Update local map immediately
  if (window.updateBusLocationOnMap && window.busRouteData) {
    window.updateBusLocationOnMap(
      lat,
      lng,
      window.busRouteData.busNumber || 'MY BUS',
      speed,
      new Date().toLocaleTimeString(),
      accuracy
    );
  }

  // Throttle HTTP transmission
  if (now - lastGpsSendTime >= GPS_SEND_INTERVAL_MS) {
    lastGpsSendTime = now;
    sendGpsCoordinates(lat, lng, accuracy, speed, heading);
  }
}

function sendGpsCoordinates(lat, lng, accuracy, speed, heading) {
  const csrfToken = getCsrfToken();

  fetch('/api/driver/gps', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken
    },
    body: JSON.stringify({
      latitude: lat,
      longitude: lng,
      accuracy: accuracy,
      speed: speed,
      heading: heading,
      csrf_token: csrfToken
    })
  })
  .then(res => res.json())
  .then(data => {
    if (data.status === 'success') {
      packetsSent++;
      const dPkt = document.getElementById('dispCount');
      const dTime = document.getElementById('lastPacketTime');
      if (dPkt) dPkt.textContent = `${packetsSent} packets`;
      if (dTime) dTime.textContent = `Last transmission: ${new Date().toLocaleTimeString()}`;
      updateStatusBadge('active');
    } else {
      console.warn('GPS transmission server response:', data.message);
    }
  })
  .catch(err => {
    console.error('Error broadcasting GPS packet:', err);
  });
}

function handleLocationError(error) {
  let errorMsg = 'GPS unavailable';
  switch (error.code) {
    case error.PERMISSION_DENIED:
      errorMsg = 'Location permission denied by user';
      break;
    case error.POSITION_UNAVAILABLE:
      errorMsg = 'Location information unavailable';
      break;
    case error.TIMEOUT:
      errorMsg = 'Location acquisition timed out';
      break;
  }
  console.warn('Geolocation Error:', errorMsg);
  updateStatusBadge('error', errorMsg);
}

function startGpsBroadcaster() {
  if (!navigator.geolocation) {
    alert('Geolocation API is not supported by your browser.');
    updateStatusBadge('error', 'Browser Geolocation Unsupported');
    return;
  }

  const options = {
    enableHighAccuracy: true,
    timeout: 10000,
    maximumAge: 0
  };

  watchId = navigator.geolocation.watchPosition(
    handleLocationSuccess,
    handleLocationError,
    options
  );

  isBroadcasting = true;
  updateStatusBadge('active');
}

function stopGpsBroadcaster() {
  if (watchId !== null) {
    navigator.geolocation.clearWatch(watchId);
    watchId = null;
  }
  isBroadcasting = false;
  updateStatusBadge('paused');
}

function toggleTracking() {
  const btn = document.getElementById('toggleTrackingBtn');
  if (isBroadcasting) {
    stopGpsBroadcaster();
    if (btn) {
      btn.innerHTML = '<i class="fa-solid fa-play"></i> Resume Broadcast';
      btn.className = 'btn btn-primary';
    }
  } else {
    startGpsBroadcaster();
    if (btn) {
      btn.innerHTML = '<i class="fa-solid fa-pause"></i> Pause Broadcast';
      btn.className = 'btn btn-outline';
    }
  }
}

// Clean up geolocation on window leave/unload
window.addEventListener('beforeunload', function() {
  stopGpsBroadcaster();
});

// Start tracking on load if page is gps_broadcast
document.addEventListener('DOMContentLoaded', function() {
  if (document.getElementById('dispLat')) {
    startGpsBroadcaster();
  }
});
