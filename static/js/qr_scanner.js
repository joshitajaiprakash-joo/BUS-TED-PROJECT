// ===================================================================
// BUS-TED! - QR Scanner Module (html5-qrcode)
// ===================================================================

let html5QrCode = null;
let isScanning = false;

function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

function showResult(type, message, details) {
  const resultCard = document.getElementById('scanResultCard');
  if (!resultCard) return;

  resultCard.style.display = 'block';

  if (type === 'success') {
    resultCard.className = 'scan-result-card alert-success';
    resultCard.innerHTML = `
      <div style="display: flex; align-items: flex-start; gap: 12px;">
        <i class="fa-solid fa-circle-check" style="font-size: 24px; color: #10b981; margin-top: 2px;"></i>
        <div>
          <strong style="font-size: 16px; color: #065f46; display: block;">Boarding Verified!</strong>
          <p style="font-size: 14px; margin: 4px 0 8px;">${message}</p>
          <div style="font-size: 12px; color: #047857;">
            <strong>Bus:</strong> ${details.bus_number || 'College Transit'} &bull;
            <strong>Time:</strong> ${details.time || 'Just now'}
          </div>
          <div style="margin-top: 14px;">
            <a href="/student/dashboard" class="btn btn-success btn-sm">
              <i class="fa-solid fa-gauge-high"></i> Go to Dashboard
            </a>
          </div>
        </div>
      </div>
    `;
  } else if (type === 'duplicate') {
    resultCard.className = 'scan-result-card alert-warning';
    resultCard.innerHTML = `
      <div style="display: flex; align-items: flex-start; gap: 12px;">
        <i class="fa-solid fa-triangle-exclamation" style="font-size: 24px; color: #f59e0b; margin-top: 2px;"></i>
        <div>
          <strong style="font-size: 16px; color: #92400e; display: block;">Already Boarded</strong>
          <p style="font-size: 14px; margin: 4px 0 8px;">${message}</p>
          <a href="/student/dashboard" class="btn btn-outline btn-sm" style="margin-top: 6px;">
            View Dashboard
          </a>
        </div>
      </div>
    `;
  } else {
    resultCard.className = 'scan-result-card alert-danger';
    resultCard.innerHTML = `
      <div style="display: flex; align-items: flex-start; gap: 12px;">
        <i class="fa-solid fa-circle-xmark" style="font-size: 24px; color: #ef4444; margin-top: 2px;"></i>
        <div>
          <strong style="font-size: 16px; color: #991b1b; display: block;">Verification Failed</strong>
          <p style="font-size: 14px; margin: 4px 0;">${message}</p>
          <button type="button" class="btn btn-outline btn-sm" onclick="startScanner()" style="margin-top: 8px;">
            <i class="fa-solid fa-rotate-right"></i> Try Again
          </button>
        </div>
      </div>
    `;
  }
}

function verifyScannedToken(token) {
  if (!token) return;

  // Stop scanner to prevent multiple rapid scans
  stopScanner();

  const csrfToken = getCsrfToken();

  showResult('info', 'Verifying attendance token with campus transport server...', {});

  fetch('/api/student/scan-qr', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken
    },
    body: JSON.stringify({
      qr_token: token,
      csrf_token: csrfToken
    })
  })
  .then(res => res.json().then(data => ({ status: res.status, body: data })))
  .then(({ status, body }) => {
    if (status === 200 && body.status === 'success') {
      showResult('success', body.message, body);
    } else if (status === 409) {
      showResult('duplicate', body.message, body);
    } else {
      showResult('error', body.message || 'Verification rejected by server.', body);
    }
  })
  .catch(err => {
    showResult('error', 'Network communication error connecting to server.', {});
  });
}

function startScanner() {
  const startBtn = document.getElementById('startScanBtn');
  const stopBtn = document.getElementById('stopScanBtn');

  if (typeof Html5Qrcode === 'undefined') {
    alert('QR scanner library is still loading. Please check your internet connection.');
    return;
  }

  if (!html5QrCode) {
    html5QrCode = new Html5Qrcode('reader');
  }

  const config = {
    fps: 10,
    qrbox: { width: 250, height: 250 }
  };

  html5QrCode.start(
    { facingMode: 'environment' },
    config,
    (decodedText) => {
      verifyScannedToken(decodedText);
    },
    (errorMessage) => {
      // scanning frames...
    }
  ).then(() => {
    isScanning = true;
    if (startBtn) startBtn.style.display = 'none';
    if (stopBtn) stopBtn.style.display = 'inline-flex';
  }).catch((err) => {
    console.error('Camera access error:', err);
    alert('Unable to access camera. Please ensure camera permissions are granted in your browser, or use the manual test token input below.');
  });
}

function stopScanner() {
  const startBtn = document.getElementById('startScanBtn');
  const stopBtn = document.getElementById('stopScanBtn');

  if (html5QrCode && isScanning) {
    html5QrCode.stop().then(() => {
      isScanning = false;
      if (startBtn) startBtn.style.display = 'inline-flex';
      if (stopBtn) stopBtn.style.display = 'none';
    }).catch(err => console.error('Error stopping scanner:', err));
  }
}

// Manual Test Input Toggle & Submission
function toggleManualInput() {
  const container = document.getElementById('manualInputContainer');
  const icon = document.getElementById('manualToggleIcon');
  if (container.style.display === 'none') {
    container.style.display = 'block';
    icon.className = 'fa-solid fa-chevron-up';
  } else {
    container.style.display = 'none';
    icon.className = 'fa-solid fa-chevron-down';
  }
}

function submitManualToken() {
  const token = document.getElementById('manualTokenInput').value.trim();
  if (!token) {
    alert('Please paste or enter a QR token.');
    return;
  }
  verifyScannedToken(token);
}
