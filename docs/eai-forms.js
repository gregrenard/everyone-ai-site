// Deploy-time overlay, published as docs/eai-forms.js by build.py (config: site-config.json).
// Design ships forms with an empty endpoint: they showed "Thank you" and dropped the message.
//  - newsletter forms post to MailerLite, the list the live site already uses; the page's
//    own handler then shows its thank-you line.
//  - other forms post to formEndpoint when one is set (a Google Apps Script web app, source in
//    forms-apps-script.gs), with _form naming the sheet tab, chosen from the first segment of
//    the page's canonical path through formTabs. Until it is set they open the visitor's email
//    app with the message filled in, and no false success is shown.
//  - a checked "newsletter" box (Home contact form) also subscribes the email to MailerLite.
(function () {
  var C = window.EAI_FORMS || {};
  function tabFor() {
    var c = document.querySelector('link[rel=canonical]');
    var path = c ? new URL(c.href).pathname : location.pathname;
    var seg = path.split('/').filter(Boolean)[0] || '';
    var tabs = C.formTabs || {};
    return Object.prototype.hasOwnProperty.call(tabs, seg) ? tabs[seg] : 'Other';
  }
  function subscribe(email) {
    var b = new URLSearchParams();
    b.append('fields[email]', email);
    b.append('ml-submit', '1');
    b.append('anticsrf', 'true');
    fetch(C.newsletter, { method: 'POST', mode: 'no-cors', body: b }).catch(function () {});
  }
  var NOTE = {
    en: 'Your email app has opened with your message. Please press Send there to finish.',
    fr: 'Votre messagerie s’est ouverte avec votre message. Cliquez sur Envoyer pour terminer.',
    es: 'Tu aplicación de correo se ha abierto con tu mensaje. Pulsa Enviar para terminar.',
    de: 'Ihr E-Mail-Programm wurde mit Ihrer Nachricht geöffnet. Klicken Sie dort auf Senden.',
    nl: 'Uw e-mailprogramma is geopend met uw bericht. Klik daar op Verzenden om af te ronden.',
    it: 'La sua app di posta si è aperta con il messaggio. Prema Invia per completare.',
    pt: 'A sua aplicação de e-mail abriu com a mensagem. Clique em Enviar para concluir.',
    zh: '您的邮件应用已打开并填好了内容，请在其中点击发送。'
  };
  function isNewsletter(f) {
    return f.querySelector('input[type=email]') && !f.querySelector('textarea') &&
      f.querySelectorAll('input:not([type=hidden]),select').length === 1;
  }
  function label(el) {
    var l = el.closest('label');
    var s = l && l.querySelector('span');
    return (s ? s.textContent : el.name).replace(/\s*\*\s*$/, '');
  }
  function lines(f) {
    var out = [];
    Array.prototype.forEach.call(f.elements, function (el) {
      if (!el.name || !el.value || el.type === 'submit') return;
      if ((el.type === 'checkbox' || el.type === 'radio') && !el.checked) return;
      out.push(label(el) + ': ' + el.value);
    });
    return out.join('\n');
  }
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (isNewsletter(f)) {
      if (C.newsletter) subscribe(f.querySelector('input[type=email]').value);
      return;
    }
    if (C.formEndpoint) {
      var body = new URLSearchParams(new FormData(f));
      body.append('_form', tabFor());
      body.append('_page', location.href);
      body.append('_lang', document.documentElement.lang || '');
      // Apps Script does not keep the order of posted fields: send it, so sheet columns follow the form.
      body.append('_fields', Array.prototype.map.call(f.elements, function (el) { return el.name; })
        .filter(function (n, i, a) { return n && a.indexOf(n) === i; }).join(','));
      fetch(C.formEndpoint, { method: 'POST', mode: 'no-cors', body: body }).catch(function () {});
      var opt = f.querySelector('input[name=newsletter]');
      if (opt && opt.checked && C.newsletter && body.get('email')) subscribe(body.get('email'));
      return;
    }
    e.preventDefault();
    e.stopImmediatePropagation();
    var page = document.title.split('|')[0].trim();
    location.href = 'mailto:' + C.contactEmail + '?subject=' + encodeURIComponent('Website message: ' + page) +
      '&body=' + encodeURIComponent(lines(f));
    var note = f.querySelector('[data-eai-form-note]');
    if (!note) {
      note = document.createElement('p');
      note.setAttribute('data-eai-form-note', '');
      note.style.cssText = "margin:16px 0 0;font:600 15px/1.5 'Open Sans',sans-serif;color:#2f855a";
      f.appendChild(note);
    }
    note.textContent = NOTE[document.documentElement.lang] || NOTE.en;
  }, true);
})();
