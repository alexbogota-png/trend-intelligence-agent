const radarEscape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const radarDateKey=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`};
const radarNumber=value=>Number(value||0).toLocaleString('es-CO');
const radarInteractions=row=>Number(row.likes||0)+Number(row.comments||0)+Number(row.shares||0);
const radarPostTitle=row=>{const title=radarEscape(row.title||'Publicación sin texto');const url=String(row.url||'');return /^https:\/\/(www\.)?tiktok\.com\//i.test(url)?`<a href="${radarEscape(url)}" target="_blank" rel="noopener noreferrer">${title}</a>`:title};
function radarRank(rows,label,value,detail,format=radarNumber){
  if(!rows.length)return '<div class="radar-empty-state">Todavía no hay señales guardadas para este corte.</div>';
  const max=Math.max(1,...rows.map(value));
  return `<ol class="radar-rank">${rows.slice(0,8).map((row,index)=>`<li><div class="rank-copy"><span class="rank-number">${String(index+1).padStart(2,'0')}</span><div><strong>${label(row)}</strong><small>${detail(row)}</small><div class="rank-track"><i style="width:${Math.max(4,(value(row)/max)*100)}%"></i></div></div></div><b>${format(value(row),row)}</b></li>`).join('')}</ol>`;
}
function renderRadar(data){
  const root=document.querySelector('#trend-radar-dashboard');if(!root)return;
  const hashtags=data.hashtags||[],posts=data.posts||[],sounds=data.sounds||[],globalSounds=data.global_sounds||[];
  const views=posts.reduce((sum,row)=>sum+Number(row.views||0),0);
  const interactions=posts.reduce((sum,row)=>sum+radarInteractions(row),0);
  const sources=data.sources||{};
  root.innerHTML=`<div class="radar-summary"><div><span class="radar-eyebrow">${radarEscape(data.period_label||'LECTURA SEMANAL')}</span><h3>Señales para explorar</h3><p>${radarEscape(data.updated_at||'Evidencia consultada desde BigQuery')} · ${radarEscape(data.market||'CO')}</p></div><span class="radar-bq-badge"><i></i> BigQuery</span></div>
    <div class="radar-kpis"><article><span>CONVERSACIONES</span><strong>${radarNumber(hashtags.length)}</strong><small>hashtags del corte</small></article><article><span>PUBLICACIONES</span><strong>${radarNumber(posts.length)}</strong><small>encontradas esta semana</small></article><article><span>VISTAS OBSERVADAS</span><strong>${radarNumber(views)}</strong><small>en la muestra de publicaciones</small></article><article><span>INTERACCIONES</span><strong>${radarNumber(interactions)}</strong><small>me gusta, comentarios y compartidos</small></article><article><span>AUDIOS</span><strong>${radarNumber(sounds.length)}</strong><small>asociados a publicaciones observadas</small></article></div>
    <div class="radar-panels"><article class="radar-panel radar-topics"><header><div><span class="radar-eyebrow">TEMAS</span><h4>Conversaciones detectadas</h4></div><small>Hashtags · ${radarEscape(sources.hashtags||'últimos 7 días')}</small></header>${radarRank(hashtags,row=>`#${radarEscape(row.hashtag_name)}`,row=>Number(row.views||row.publish_count||0),row=>`${radarNumber(row.publish_count)} publicaciones · ${radarNumber(row.views)} vistas estimadas`)}</article>
    <article class="radar-panel radar-posts"><header><div><span class="radar-eyebrow">CONTENIDO</span><h4>Publicaciones destacadas</h4></div><small>Ordenadas por interacciones</small></header>${radarRank(posts,radarPostTitle,row=>radarInteractions(row),row=>`${radarEscape(row.author||'Cuenta desconocida')} · ${radarNumber(row.views)} vistas · ${radarNumber(radarInteractions(row))} interacciones`)}</article>
    <article class="radar-panel radar-audios"><header><div><span class="radar-eyebrow">SONIDO · CO</span><h4>Audios en publicaciones</h4></div><small>Uso dentro de la muestra</small></header>${radarRank(sounds,row=>radarEscape(row.sound_name||'Audio sin título'),row=>Number(row.video_count||0),row=>`${radarEscape(row.sound_author||'Artista sin identificar')} · ${radarNumber(row.video_count)} publicaciones · ${radarNumber(row.views)} vistas`)}</article>
    <article class="radar-panel radar-global-audios"><header><div><span class="radar-eyebrow">CHART · GLOBAL</span><h4>Top y virales</h4></div><small>Top 50 + Viral 50</small></header>${radarRank(globalSounds,row=>radarEscape(row.sound_name||'Audio sin título'),row=>Math.max(1,51-Number(row.chart_rank||50)),row=>`${radarEscape(row.sound_author||'Artista sin identificar')} · ${Number(row.chart_scene)===1?'viral':'top'}`,(_value,row)=>row.chart_rank?`#${radarNumber(row.chart_rank)}`:'Posición N/D')}</article></div>
    <p class="radar-method-note">Cobertura: hashtags de los últimos 7 días; publicaciones de la semana en curso; dos charts de audio sin filtro de país, por lo que se presentan como referencia global. Las vistas e interacciones corresponden a la muestra encontrada, no al total de TikTok. Los audios asociados a publicaciones CO son una señal local distinta del chart.</p>`;
  const dateField=document.querySelector('#week-start');if(dateField)dateField.value=data.target_date||'';
}
async function loadRadar(targetDate=''){
  const root=document.querySelector('#trend-radar-dashboard');if(!root)return;
  root.innerHTML='<div class="radar-loading">Cargando la última información guardada…</div>';
  try{const query=targetDate?`?market=CO&target_date=${targetDate}`:'?market=CO';const response=await fetch(`/api/trends/radar${query}`,{headers:authHeaders()});const data=await response.json();if(!response.ok)throw Error(data.detail||'No se pudo cargar el radar.');renderRadar(data)}catch(error){root.innerHTML=`<div class="radar-empty-state">${radarEscape(error.message)}</div>`}
}
async function pollRadarRun(runId,targetDate,status,label,scene=null){
  for(let attempt=0;attempt<40;attempt++){
    const sceneQuery=scene===null?'':`&scene=${scene}`;
    const response=await fetch(`/api/trends/radar/run/${encodeURIComponent(runId)}?target_date=${targetDate}${sceneQuery}`,{headers:authHeaders()});
    const text=await response.text();let data;try{data=JSON.parse(text)}catch{throw Error(`Error consultando ${label} (${response.status}): ${text.slice(0,220)}`)}
    if(!response.ok)throw Error(data.detail||`No se pudo consultar ${label}.`);
    const state=String(data.run?.status||'').toUpperCase();
    if(state==='COMPLETED')return data.run;
    if(state==='FAILED'||state==='ERROR')throw Error(`La ejecución de ${label} falló.`);
    if(status)status.textContent=`Recolectando ${label}…`;
    await new Promise(resolve=>setTimeout(resolve,3000));
  }
  throw Error(`La búsqueda de ${label} sigue en curso. Vuelve a actualizar en un momento.`);
}
document.addEventListener('DOMContentLoaded',()=>{
  const button=document.querySelector('#run-trend-radar');if(!button)return;
  let refreshTimer=null;
  const startAutoLoad=()=>{if(!window.getAccessToken?.())return;loadRadar();if(!refreshTimer)refreshTimer=window.setInterval(()=>loadRadar(),300000)};
  window.addEventListener('auth:changed',event=>{if(event.detail?.authenticated)startAutoLoad()});startAutoLoad();
  document.querySelector('#week-start')?.addEventListener('change',event=>loadRadar(event.target.value));
  button.onclick=async()=>{
    const targetDate=radarDateKey(),status=document.querySelector('#weekly-status'),weekInput=document.querySelector('#week-start');
    if(weekInput)weekInput.value=targetDate;button.disabled=true;
    try{
      if(status)status.textContent='Buscando hashtags y temas de los últimos 7 días…';
      const response=await fetch('/api/trends/radar/run',{method:'POST',headers:{...authHeaders(),'Content-Type':'application/json'},body:JSON.stringify({market:'CO',target_date:targetDate})});
      const text=await response.text();let data;try{data=JSON.parse(text)}catch{throw Error(`No se pudo iniciar la recolección (${response.status}): ${text.slice(0,220)}`)}
      if(!response.ok)throw Error(data.detail||'No se pudo iniciar el radar.');
      const completedRuns=[];
      for(const [index,run] of (data.runs||[]).entries()){const id=run.runId||run.run_id;if(!id)continue;const isChart=String(run.endpoint||'').endsWith('fetch_music_chart_list');completedRuns.push(await pollRadarRun(id,targetDate,status,isChart?'chart de audios':'hashtags',isChart?index-1:null))}
      const hashtagRun=completedRuns.find(run=>String(run.endpoint||'').endsWith('get_trends_hashtag_list'));
      const discovered=(hashtagRun?.output?.items||[]).map(item=>item.hashtagName).filter(Boolean).slice(0,20);
      if(!discovered.length)throw Error('La fuente no devolvió hashtags; no se lanzó la búsqueda de publicaciones.');
      if(status)status.textContent=`Señales encontradas: ${discovered.length}. Buscando publicaciones y audios asociados…`;
      const enrich=await fetch('/api/trends/radar/enrich',{method:'POST',headers:{...authHeaders(),'Content-Type':'application/json'},body:JSON.stringify({market:'CO',target_date:targetDate,hashtags:discovered})});
      const enrichText=await enrich.text();let enrichData;try{enrichData=JSON.parse(enrichText)}catch{throw Error(`No se pudo iniciar la búsqueda de contenido (${enrich.status}): ${enrichText.slice(0,220)}`)}
      if(!enrich.ok)throw Error(enrichData.detail||'No se pudieron buscar publicaciones.');
      await pollRadarRun(enrichData.runId||enrichData.run_id,targetDate,status,'publicaciones y audios');
      await loadRadar(targetDate);if(status)status.textContent=`Lectura semanal guardada en BigQuery · actualización ${targetDate}.`;
    }catch(error){if(status)status.textContent=error.message}
    finally{button.disabled=false}
  };
});
