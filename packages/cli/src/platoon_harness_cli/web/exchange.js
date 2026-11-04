// platoon-harness: the link exchange, which runs before SwarmChat's gate below looks for a token. A link opens once: it is
// spent for a session token that expires, and the gate opens the page with that, through the address it watches.
(function () {
  const form = document.querySelector('form'), err = document.querySelector('.err');
  const said = document.createElement('p');
  said.textContent = 'Open a link that platoon-harness web says, or one a page acting for you made. Each opens once.';
  form.append(said);
  const link = (location.hash.match(/(^#|&)link=([0-9a-f]{16,})/) || [])[2];
  if (!link) return;
  localStorage.removeItem('swarmchat.view.token');  // so the gate opens nothing older first
  history.replaceState(null, '', location.pathname);
  fetch('/x/exchange', {method: 'POST', body: '{}',
    headers: {'Authorization': 'Bearer ' + link, 'Content-Type': 'application/json'}})
    .then(async r => {
      const p = await r.json().catch(() => ({error: `The server answered ${r.status}.`}));
      if (!r.ok) throw new Error(p.error);
      location.hash = 'token=' + p.token;
    })
    .catch(x => { err.textContent = x.message; });
})();
