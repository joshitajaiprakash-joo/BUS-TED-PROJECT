// ===================================================================
// BUS-TED! - Main Application JavaScript
// ===================================================================

document.addEventListener('DOMContentLoaded', function() {
  // Mobile Sidebar Toggle
  const sidebarToggle = document.getElementById('sidebarToggle');
  const appSidebar = document.getElementById('appSidebar');

  if (sidebarToggle && appSidebar) {
    sidebarToggle.addEventListener('click', function(e) {
      e.stopPropagation();
      appSidebar.classList.toggle('show');
    });

    // Close on click outside when on mobile
    document.addEventListener('click', function(e) {
      if (window.innerWidth <= 992 && appSidebar.classList.contains('show')) {
        if (!appSidebar.contains(e.target) && e.target !== sidebarToggle) {
          appSidebar.classList.remove('show');
        }
      }
    });
  }

  // Global Socket.IO Initialization
  if (typeof io !== 'undefined') {
    window.appSocket = io();

    window.appSocket.on('connect', function() {
      // If tripId is present in page context, join room
      if (window.busRouteData && window.busRouteData.tripId) {
        window.appSocket.emit('join_trip', { trip_id: window.busRouteData.tripId });
      }
    });

    // Global listener for trip start / end to update live UI
    window.appSocket.on('trip_status_changed', function(data) {
      // Reload page if current page is relevant to active trip change
      if (window.busRouteData && (data.bus_id === window.busRouteData.busId || data.trip_id === window.busRouteData.tripId)) {
        setTimeout(() => {
          window.location.reload();
        }, 1500);
      }
    });

    // Global occupancy updates
    window.appSocket.on('occupancy_updated', function(data) {
      const seatsPill = document.getElementById('busSeatsPill');
      if (seatsPill && window.busRouteData && data.trip_id === window.busRouteData.tripId) {
        seatsPill.textContent = `${Math.max(0, 50 - data.passenger_count)} seats available`;
      }
    });
  }
});
