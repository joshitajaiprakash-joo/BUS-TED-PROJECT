// ===================================================================
// BUS-TED! - In-App Notifications Module
// ===================================================================

function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

function markNotifRead(notifId, element) {
  const csrfToken = getCsrfToken();

  fetch(`/notifications/mark-read/${notifId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken
    }
  })
  .then(res => res.json())
  .then(data => {
    if (data.status === 'success') {
      if (element) {
        const card = element.closest('.list-item-card');
        if (card) {
          card.style.background = '#f8fafc';
          card.style.borderColor = '#e2e8f0';
          element.remove();
        }
      }
      // Decrement badges
      const sidebarBadge = document.getElementById('sidebarNotifBadge');
      if (sidebarBadge) {
        let count = parseInt(sidebarBadge.textContent, 10);
        if (count > 1) {
          sidebarBadge.textContent = count - 1;
        } else {
          sidebarBadge.remove();
        }
      }
    }
  })
  .catch(err => console.error('Error marking notification read:', err));
}
