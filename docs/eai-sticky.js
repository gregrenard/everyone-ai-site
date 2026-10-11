// Deploy-time overlay: keep the white menu bar visible while the page scrolls.
// Published as docs/eai-sticky.js by build.py. Goes inert once Design ships a sticky header.
//
// The announcement banner above the menu scrolls away; only the menu bar sticks.
// On Home the <header> is a direct child of the page column, so it can stick itself.
// On every other page it sits with the banner inside the short SiteHeader wrapper, where
// position:sticky has no room to act: the wrapper sticks instead, with a negative top
// equal to the banner height.
(function () {
  var css = document.createElement('style');
  css.id = 'eai-sticky-css';
  css.textContent =
    '[data-eai-sticky]{position:sticky!important;top:var(--eai-sticky-top,0px)!important;z-index:100!important}' +
    // Open mobile menu taller than the screen: scroll inside it rather than cut it off.
    // Not on desktop, where it would clip the "Our Initiatives" and language dropdowns.
    '@media (max-width:980px){[data-eai-sticky]{max-height:calc(100vh - var(--eai-sticky-top,0px));' +
    'max-height:calc(100dvh - var(--eai-sticky-top,0px));overflow-y:auto;overscroll-behavior:contain}}';
  document.head.appendChild(css);

  var BAR_MAX = 200; // above this the mobile menu is open: keep the last closed-bar height

  function apply() {
    var root = document.getElementById('dc-root');
    var header = root && root.querySelector('header');
    if (!header || !header.offsetHeight) return;
    // Climb to the first ancestor whose parent holds the page content.
    var box = header;
    while (box.parentElement && box.parentElement !== root &&
           box.parentElement.offsetHeight <= box.offsetHeight + 300) box = box.parentElement;
    var old = document.querySelectorAll('[data-eai-sticky]');
    for (var i = 0; i < old.length; i++) if (old[i] !== box) old[i].removeAttribute('data-eai-sticky');
    if (!box.hasAttribute('data-eai-sticky')) box.setAttribute('data-eai-sticky', '');
    var above = Math.round(header.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop);
    var top = -above + 'px';
    if (box.style.getPropertyValue('--eai-sticky-top') !== top) box.style.setProperty('--eai-sticky-top', top);
    // Anchors (#mission, #press, ...) must stop below the bar, not under it.
    if (header.offsetHeight < BAR_MAX) {
      var pad = header.offsetHeight + 'px';
      if (document.documentElement.style.scrollPaddingTop !== pad) document.documentElement.style.scrollPaddingTop = pad;
    }
  }

  var queued = false;
  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(function () { queued = false; apply(); });
  }
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
  addEventListener('resize', schedule);
  addEventListener('load', schedule);
  schedule();
})();
