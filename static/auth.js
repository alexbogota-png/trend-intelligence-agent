let supabaseClient;
const auth=$('#auth'),appShell=$('#app'),authStatus=$('#auth-status');
async function initAuth(){try{const c=await fetch('/api/config').then(r=>r.json());if(!c.supabase_url||!c.supabase_anon_key)throw Error('Supabase todavía no está configurado en el servidor.');supabaseClient=window.supabase.createClient(c.supabase_url,c.supabase_anon_key);const {data}=await supabaseClient.auth.getSession();applySession(data.session);supabaseClient.auth.onAuthStateChange((_event,session)=>applySession(session))}catch(e){authStatus.textContent=e.message}}
function applySession(session){if(session){auth.classList.add('hidden');appShell.classList.remove('hidden');$('#user-email').textContent=session.user.email||'';window.getAccessToken=()=>session.access_token}else{auth.classList.remove('hidden');appShell.classList.add('hidden');window.getAccessToken=()=>null}}
$('#login-tab').onclick=()=>{$('#login-tab').classList.add('active');$('#signup-tab').classList.remove('active');$('#login-form').classList.remove('hidden');$('#signup-form').classList.add('hidden');authStatus.textContent=''};
$('#signup-tab').onclick=()=>{$('#signup-tab').classList.add('active');$('#login-tab').classList.remove('active');$('#signup-form').classList.remove('hidden');$('#login-form').classList.add('hidden');authStatus.textContent=''};
$('#login-form').onsubmit=async e=>{e.preventDefault();authStatus.textContent='';const {error}=await supabaseClient.auth.signInWithPassword({email:$('#login-email').value,password:$('#login-password').value});if(error)authStatus.textContent=error.message};
$('#signup-form').onsubmit=async e=>{e.preventDefault();authStatus.textContent='';const {error}=await supabaseClient.auth.signUp({email:$('#signup-email').value,password:$('#signup-password').value,options:{emailRedirectTo:location.origin}});authStatus.textContent=error?error.message:'Revisa tu correo para confirmar la cuenta.'};
$('#logout').onclick=()=>supabaseClient.auth.signOut();
initAuth();
