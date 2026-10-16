const $auth = selector => document.querySelector(selector);
const auth = $auth('#auth');
const appShell = $auth('#app');
const authStatus = $auth('#auth-status');
let supabaseClient;

async function initAuth() {
  try {
    const config = await fetch('/api/config').then(response => response.json());
    if (!config.supabase_url || !config.supabase_anon_key) {
      throw new Error('Supabase todavía no está configurado en el servidor.');
    }
    supabaseClient = window.supabase.createClient(config.supabase_url, config.supabase_anon_key);
    const { data } = await supabaseClient.auth.getSession();
    applySession(data.session);
    supabaseClient.auth.onAuthStateChange((_event, session) => applySession(session));
  } catch (error) {
    authStatus.textContent = error.message;
  }
}

function applySession(session) {
  if (session) {
    auth.classList.add('hidden');
    appShell.classList.remove('hidden');
    $auth('#user-email').textContent = session.user.email || '';
    window.getAccessToken = () => session.access_token;
  } else {
    auth.classList.remove('hidden');
    appShell.classList.add('hidden');
    window.getAccessToken = () => null;
  }
  window.dispatchEvent(new CustomEvent('auth:changed', { detail: { authenticated: Boolean(session) } }));
}

$auth('#login-tab').addEventListener('click', () => {
  $auth('#login-tab').classList.add('active');
  $auth('#signup-tab').classList.remove('active');
  $auth('#login-form').classList.remove('hidden');
  $auth('#signup-form').classList.add('hidden');
  authStatus.textContent = '';
});
$auth('#signup-tab').addEventListener('click', () => {
  $auth('#signup-tab').classList.add('active');
  $auth('#login-tab').classList.remove('active');
  $auth('#signup-form').classList.remove('hidden');
  $auth('#login-form').classList.add('hidden');
  authStatus.textContent = '';
});
$auth('#login-form').addEventListener('submit', async event => {
  event.preventDefault();
  const submitButton = event.currentTarget.querySelector('[type="submit"]');
  authStatus.textContent = 'Validando correo y contraseña…';
  submitButton.disabled = true;
  try {
    const { error } = await supabaseClient.auth.signInWithPassword({
      email: $auth('#login-email').value.trim(),
      password: $auth('#login-password').value,
    });
    authStatus.textContent = error ? error.message : '';
  } catch (error) {
    authStatus.textContent = error.message || 'No se pudo iniciar sesión.';
  } finally {
    submitButton.disabled = false;
  }
});
$auth('#signup-form').addEventListener('submit', async event => {
  event.preventDefault();
  authStatus.textContent = '';
  const { error } = await supabaseClient.auth.signUp({
    email: $auth('#signup-email').value.trim(),
    password: $auth('#signup-password').value,
    options: { emailRedirectTo: location.origin },
  });
  authStatus.textContent = error ? error.message : 'Revisa tu correo para confirmar la cuenta.';
});
$auth('#logout').addEventListener('click', () => supabaseClient.auth.signOut());

initAuth();
