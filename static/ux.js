// Global UX helpers for responsive sidebar, table->card label injection, accessibility
(function(){
  function qs(sel, ctx){ return (ctx||document).querySelector(sel); }
  function qsa(sel, ctx){ return Array.from((ctx||document).querySelectorAll(sel)); }

  function initSidebar(){
    const btn = qs('#hamburgerBtn') || qs('.sams-hamburger') || qs('.hamburger');
    const sidebar = qs('#sidebar') || qs('.sidebar') || qs('.sams-sidebar');
    const overlay = qs('#sidebarOverlay') || qs('.sidebar-overlay') || qs('.sams-sidebar-overlay');
    if(!btn || !sidebar || !overlay) return;

    function open(){ sidebar.classList.add('open'); overlay.classList.add('active'); document.body.classList.add('sams-nav-open'); sidebar.setAttribute('aria-hidden','false'); }
    function close(){ sidebar.classList.remove('open'); overlay.classList.remove('active'); document.body.classList.remove('sams-nav-open'); sidebar.setAttribute('aria-hidden','true'); }
    function toggle(){ sidebar.classList.toggle('open'); overlay.classList.toggle('active'); document.body.classList.toggle('sams-nav-open'); }

    // Remove any inline onclick to avoid duplicate handlers
    try { btn.removeAttribute && btn.removeAttribute('onclick'); btn.onclick = null; } catch (e) {}
    btn.addEventListener('click', function(e){ e.stopPropagation(); toggle(); btn.setAttribute('aria-expanded', sidebar.classList.contains('open')); });
    overlay.addEventListener('click', function(e){ close(); });

    // Close on Escape
    document.addEventListener('keydown', function(e){ if(e.key === 'Escape') close(); });

    // Close when clicking outside sidebar
    document.addEventListener('click', function(e){ if(!sidebar.contains(e.target) && !btn.contains(e.target)) close(); });

    // Auto-close when clicking a link inside (mobile)
    qsa('#sidebar a, .sidebar a, .sams-sidebar a').forEach(function(a){
      a.addEventListener('click', function(){ if(window.innerWidth < 768) setTimeout(close, 160); });
    });
  }

  function addDataLabelsToTables(){
    qsa('.sams-table:not(.no-responsive)').forEach(function(tbl){
      try{
        const ths = Array.from(tbl.querySelectorAll('thead th')).map(th=>th.textContent.trim());
        if(!ths.length) return;
        tbl.querySelectorAll('tbody tr').forEach(function(tr){
          const cells = Array.from(tr.children).filter(n=>n.tagName.toLowerCase()==='td' || n.tagName.toLowerCase()==='th');
          for(let i=0;i<cells.length;i++){
            const label = ths[i] || '';
            if(label) cells[i].setAttribute('data-label', label);
          }
        });
      }catch(e){console.error('Label injection failed', e);}
    });
  }

  function enhanceForms(){
    // Make inputs full width on small screens
    function apply(){
      qsa('form .sams-select, form select, form input, form textarea').forEach(function(el){
        if(window.innerWidth < 640) el.style.width = '100%'; else el.style.width = '';
      });
    }
    window.addEventListener('resize', apply);
    apply();
  }

  document.addEventListener('DOMContentLoaded', function(){
    initSidebar();
    addDataLabelsToTables();
    enhanceForms();

    // Accessibility: ensure focus outline visible when using keyboard
    document.body.addEventListener('keydown', function(e){ if(e.key==='Tab') document.documentElement.classList.add('show-focus'); });
  });
})();
