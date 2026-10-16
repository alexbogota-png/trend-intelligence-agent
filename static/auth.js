const $auth = selector => document.querySelector(selector);
const auth = $auth('#auth');
const appShell = $auth('#app');
const authStatus = $auth('#auth-status');
let supabaseClient;

function setAuthReady(ready) {
  document.querySelectorAll('#login-form button[type="submit"], #signup-form button[type="submit"]').forEach(button => {
    button.disabled = !ready;
  });
}

setAuthReady(false);

async function initAuth() {
  try {
    if (!window.supabase?.createClient) {
      throw new Error('No se pudo cargar el servicio de inicio de sesión. Recarga la página e inténtalo de nuevo.');
    }
    const response = await fetch('/api/config');
    if (!response.ok) throw new Error('No se pudo consultar la configuración de inicio de sesión.');
    const config = await response.json();
    if (!config.supabase_url || !config.supabase_anon_key) {
      throw new Error('Supabase todavía no está configurado en el servidor.');
    }
    supabaseClient = window.supabase.createClient(config.supabase_url, config.supabase_anon_key);
    if (!supabaseClient?.auth) {
      throw new Error('No se pudo inicializar el inicio de sesión. Recarga la página e inténtalo de nuevo.');
    }
    const { data } = await supabaseClient.auth.getSession();
    applySession(data.session);
    supabaseClient.auth.onAuthStateChange((_event, session) => applySession(session));
    setAuthReady(true);
  } catch (error) {
    authStatus.textContent = error.message || 'No se pudo preparar el inicio de sesión.';
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
  if (!supabaseClient?.auth) {
    authStatus.textContent = 'El inicio de sesión todavía no está listo. Recarga la página e inténtalo de nuevo.';
    return;
  }
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
  if (!supabaseClient?.auth) {
    authStatus.textContent = 'El inicio de sesión todavía no está listo. Recarga la página e inténtalo de nuevo.';
    return;
  }
  authStatus.textContent = '';
  const submitButton = event.currentTarget.querySelector('[type="submit"]');
  submitButton.disabled = true;
  try {
    const { error } = await supabaseClient.auth.signUp({
      email: $auth('#signup-email').value.trim(),
      password: $auth('#signup-password').value,
      options: { emailRedirectTo: location.origin },
    });
    authStatus.textContent = error ? error.message : 'Revisa tu correo para confirmar la cuenta.';
  } catch (error) {
    authStatus.textContent = error.message || 'No se pudo crear la cuenta.';
  } finally {
    submitButton.disabled = false;
  }
});
$auth('#logout').addEventListener('click', () => supabaseClient?.auth?.signOut());

initAuth();
