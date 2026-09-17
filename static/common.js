// common.js - shared utilities for SAMS dashboards

/**
 * Set the UI language and persist it (e.g., via cookie).
 * The page should reload to apply language changes.
 */
function setLanguage(lang) {
  // Store in a cookie (expires in 30 days)
  const d = new Date();
  d.setTime(d.getTime() + 30 * 24 * 60 * 60 * 1000);
  document.cookie = `lang=${lang}; expires=${d.toUTCString()}; path=/`;
  // Reload to apply translations (templates should read the cookie)
  location.reload();
}

/**
 * Show a specific dashboard section by its ID and hide others.
 * Sections are elements with class "section" and an id attribute.
 */
function showSection(sectionId) {
  // Hide all sections
  document.querySelectorAll('.section').forEach(function (el) {
    el.classList.remove('active');
  });
  // Activate the requested one if it exists
  const target = document.getElementById(sectionId);
  if (target) {
    target.classList.add('active');
  }
}

/**
 * Toggle the mobile sidebar visibility (used in mobile view).
 */
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (sidebar && overlay) {
    sidebar.classList.toggle('open');
    overlay.style.display = sidebar.classList.contains('open') ? 'block' : 'none';
  }
}

/**
 * Close the mobile sidebar.
 */
function closeSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (sidebar && overlay) {
    sidebar.classList.remove('open');
    overlay.style.display = 'none';
  }
}

// Export functions to global scope for inline event handlers
window.setLanguage = setLanguage;
window.showSection = showSection;
window.toggleSidebar = toggleSidebar;
window.closeSidebar = closeSidebar;
