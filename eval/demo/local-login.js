/* Local demo sign-in (eval/kb_demo_server.py only; never deployed). Trades an
   email + password for a session from the LOCAL Supabase Auth, in the same
   shape /api/session returns, and stores it where the app looks for it. */
(function () {
  'use strict';
  var KEY = 'np_session';
  var $ = function (id) { return document.getElementById(id); };
  function current() { try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { return null; } }
  if (current()) $('signed-in').hidden = false;
  $('password').focus();
  $('signout').addEventListener('click', function () {
    try { localStorage.removeItem(KEY); } catch (e) { /* storage blocked */ }
    $('signed-in').hidden = true;
  });
  $('login').addEventListener('submit', async function (e) {
    e.preventDefault();
    var err = $('err'), btn = $('submit');
    err.textContent = ''; btn.disabled = true;
    try {
      var r = await fetch('/local-login/session', { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email: $('email').value.trim(), password: $('password').value }) });
      var body = await r.json().catch(function () { return {}; });
      if (!r.ok) throw new Error(body.reason || 'Sign-in failed');
      localStorage.setItem(KEY, JSON.stringify(body));
      location.href = '/kb/';
    } catch (ex) {
      err.textContent = ex.message; btn.disabled = false;
    }
  });
})();
