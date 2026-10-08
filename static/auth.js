const $auth = selector => document.querySelector(selector);
const auth = $auth('#auth');
const appShell = $auth('#app');
const authStatus = $auth('#auth-status');
const loginForm = $auth('#login-form');
const otpForm = $auth('#otp-form');
let pendingEmail = '';

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

async function sendAccessCode() {
  const email = $auth('#login-email').value.trim();
  if (!email) return;
  authStatus.textContent = 'Enviando código...';
  $auth('#send-code').disabled = true;
  try {
    const { error } = await supabaseClient.auth.signInWithOtp({
      email,
      options: { shouldCreateUser: false },
    });
    if (error) throw error;
    pendingEmail = email;
    loginForm.classList.add('hidden');
    otpForm.classList.remove('hidden');
    authStatus.textContent = `Si ${email} tiene acceso, recibirá un código. Revise también la carpeta de correo no deseado.`;
    $auth('#login-code').focus();
  } catch (error) {
    authStatus.textContent = error.message || 'No se pudo enviar el código. Inténtalo de nuevo.';
  } finally {
    $auth('#send-code').disabled = false;
  }
}

async function verifyAccessCode() {
  const token = $auth('#login-code').value.trim();
  if (!pendingEmail || !token) return;
  authStatus.textContent = 'Verificando código...';
  $auth('#verify-code').disabled = true;
  try {
    const { error } = await supabaseClient.auth.verifyOtp({ email: pendingEmail, token, type: 'email' });
    if (error) throw error;
    authStatus.textContent = '';
  } catch (error) {
    authStatus.textContent = error.message || 'El código no es válido o expiró. Solicita uno nuevo.';
  } finally {
    $auth('#verify-code').disabled = false;
  }
}

loginForm.addEventListener('submit', event => {
  event.preventDefault();
  sendAccessCode();
});
otpForm.addEventListener('submit', event => {
  event.preventDefault();
  verifyAccessCode();
});
$auth('#resend-code').addEventListener('click', sendAccessCode);
$auth('#change-email').addEventListener('click', () => {
  pendingEmail = '';
  $auth('#login-code').value = '';
  otpForm.classList.add('hidden');
  loginForm.classList.remove('hidden');
  authStatus.textContent = '';
  $auth('#login-email').focus();
});
$auth('#logout').addEventListener('click', () => supabaseClient.auth.signOut());

initAuth();
