const radarEscape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const radarDateKey=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`};
const radarNumber=value=>Number(value||0).toLocaleString('es-CO');
const radarInteractions=row=>Number(row.likes||0)+Number(row.comments||0)+Number(row.shares||0);
const radarPostTitle=row=>{const title=radarEscape(row.title||'Publicación sin texto');const url=String(row.url||'');return /^https:\/\/(www\.)?tiktok\.com\//i.test(url)?`<a href="${radarEscape(url)}" target="_blank" rel="noopener noreferrer">${title}</a>`:title};
let radarHistory=[];
let radarWeeks=[];
let radarPlatform='tiktok';
const radarCache=new Map();
const RADAR_TTL_MS=60_000;
const RADAR_HISTORY_TTL_MS=5*60_000;
const RADAR_WEEKS_TTL_MS=5*60_000;
let radarLoadSequence=0;
function radarRank(rows,label,value,detail,format=radarNumber){
  if(!rows.length)return '<div class="radar-empty-state">Todavía no hay señales guardadas para este corte.</div>';
  const max=Math.max(1,...rows.map(value));
  return `<ol class="radar-rank">${rows.slice(0,8).map((row,index)=>`<li><div class="rank-copy"><span class="rank-number">${String(index+1).padStart(2,'0')}</span><div><strong>${label(row)}</strong><small>${detail(row)}</small><div class="rank-track"><i style="width:${Math.max(4,(value(row)/max)*100)}%"></i></div></div></div><b>${format(value(row),row)}</b></li>`).join('')}</ol>`;
}
function trendChart(history,weeks){
  const historyKeys=new Set(history.map(row=>String(row.week_start)));
  const orderedWeeks=weeks.filter(item=>historyKeys.has(String(item.week_start))).sort((a,b)=>String(a.week_start).localeCompare(String(b.week_start)));
  const weekKeys=orderedWeeks.map(item=>String(item.week_start));
  if(weekKeys.length<2)return `<div class="trend-history-empty">${weekKeys.length?'Hay una sola semana observada. Se necesitan al menos dos semanas guardadas para mostrar evolución.':'Todavía no hay capturas semanales de hashtags.'}</div>`;
  const latest=weekKeys.at(-1);
  const rows=history.filter(row=>weekKeys.includes(String(row.week_start)));
  const presentLatest=rows.filter(row=>String(row.week_start)===latest).sort((a,b)=>Number(b.views||0)-Number(a.views||0));
  const chosen=presentLatest.slice(0,5);
  if(!chosen.length)return '<div class="trend-history-empty">No hay métricas de hashtags en las semanas seleccionadas.</div>';
  const colors=['#3448d2','#00a78a','#e27836','#8856c7','#d34e77'];
  const W=760,H=250,L=56,R=18,T=18,B=42,innerW=W-L-R,innerH=H-T-B;
  const scoreMax=Math.max(120,...chosen.map(tag=>Math.max(...rows.filter(row=>row.hashtag_id===tag.hashtag_id).map(row=>{const v=Number(row.views||0);const first=rows.filter(x=>x.hashtag_id===tag.hashtag_id).sort((a,b)=>String(a.week_start).localeCompare(String(b.week_start)))[0];return first&&Number(first.views)?v/Number(first.views)*100:100})))) ;
  const y=value=>T+innerH-(value/scoreMax)*innerH;
  const x=index=>L+(weekKeys.length===1?innerW/2:index*innerW/(weekKeys.length-1));
  const grid=[0,.25,.5,.75,1].map(part=>{const value=Math.round(scoreMax*part);const yy=y(value);return `<line x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}" class="trend-chart-grid"/><text x="${L-9}" y="${yy+4}" text-anchor="end" class="trend-chart-axis">${value}</text>`}).join('');
  const xLabels=weekKeys.map((key,index)=>`<text x="${x(index)}" y="${H-12}" text-anchor="middle" class="trend-chart-axis">${key.slice(5)}</text>`).join('');
  const series=chosen.map((tag,index)=>{
    const points=weekKeys.map((week,weekIndex)=>{
      const row=rows.find(item=>String(item.week_start)===week&&item.hashtag_id===tag.hashtag_id);
      if(!row)return null;
      const first=rows.filter(item=>item.hashtag_id===tag.hashtag_id).sort((a,b)=>String(a.week_start).localeCompare(String(b.week_start)))[0];
      const value=first&&Number(first.views)?Number(row.views||0)/Number(first.views)*100:100;
      return {x:x(weekIndex),y:y(value),value,weekIndex};
    }).filter(Boolean);
    const segments=points.slice(1).map(point=>{const prev=points[points.indexOf(point)-1];return point.weekIndex-prev.weekIndex===1?`<line x1="${prev.x}" y1="${prev.y}" x2="${point.x}" y2="${point.y}" stroke="${colors[index]}" class="trend-chart-line"/>`:''}).join('');
    const dots=points.map(point=>`<circle cx="${point.x}" cy="${point.y}" r="4" fill="${colors[index]}" class="trend-chart-dot"><title>${radarEscape(tag.hashtag_name)} · ${point.value.toFixed(0)} índice · ${weekKeys[point.weekIndex]}</title></circle>`).join('');
    return `${segments}${dots}`;
  }).join('');
  const legend=chosen.map((tag,index)=>{
    const values=rows.filter(row=>row.hashtag_id===tag.hashtag_id).sort((a,b)=>String(a.week_start).localeCompare(String(b.week_start)));
    const prior=values.at(-2),current=values.at(-1);
    let change=values.length===1?'1 corte':'Sin comparación semanal';
    if(prior&&current&&Number(prior.views)){
      const days=(Date.parse(`${current.week_start}T00:00:00Z`)-Date.parse(`${prior.week_start}T00:00:00Z`))/86400000;
      if(days===7){const pct=(Number(current.views)-Number(prior.views))/Number(prior.views)*100;change=`${pct>0?'+':''}${pct.toFixed(0)}% vs semana anterior`}
    }
    return `<span><i style="--trend-color:${colors[index]}"></i><b>#${radarEscape(tag.hashtag_name)}</b><small>${change}</small></span>`;
  }).join('');
  return `<svg class="trend-history-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Evolución semanal indexada de las conversaciones principales">${grid}${series}${xLabels}</svg><div class="trend-history-legend">${legend}</div><p class="trend-history-note">Índice de vistas observadas por hashtag, con su primera semana registrada = 100. Una señal ausente significa que no apareció en el corte, no que tuviera valor cero. Las semanas sin captura no se interpolan.</p>`;
}
function renderXRadar(data){
  const root=document.querySelector('#trend-radar-dashboard');if(!root)return;
  const topics=data.topics||[];
  const sightings=new Map();
  for(const row of radarHistory){const name=String(row.topic_name||'');if(!name)continue;if(!sightings.has(name))sightings.set(name,new Set());sightings.get(name).add(String(row.week_start||''))}
  const frequency=name=>sightings.get(name)?.size||1;
  const recurring=[...sightings.entries()].map(([name,weeks])=>({name,weeks:weeks.size})).sort((a,b)=>b.weeks-a.weeks||a.name.localeCompare(b.name)).slice(0,12);
  root.innerHTML=`<div class="radar-summary"><div><span class="radar-eyebrow">${radarEscape(data.target_date||'LECTURA DE X')}</span><h3>Tendencias detectadas en X · Colombia</h3><p>Temas devueltos por la fuente para el corte seleccionado.</p></div><span class="radar-bq-badge"><i></i> BigQuery</span></div>
    <div class="radar-kpis radar-x-kpis"><article><span>TEMAS EN TENDENCIA</span><strong>${radarNumber(topics.length)}</strong><small>reportados en este corte</small></article><article><span>PLATAFORMA</span><strong>X</strong><small>tendencias de Colombia</small></article><article><span>MEDICIÓN</span><strong>N/D</strong><small>este endpoint no devuelve volumen de posts ni interacciones</small></article></div>
    <div class="radar-panels radar-x-panels"><article class="radar-panel radar-x-topics"><header><div><span class="radar-eyebrow">CONVERSACIONES</span><h4>Temas reportados por X</h4></div><small>Orden de la fuente</small></header>${topics.length?`<ol class="radar-rank">${topics.map((row,index)=>{const rank=Number(row.rank_index)||index+1;const name=String(row.topic_name||'');return `<li><div class="rank-copy"><span class="rank-number">${String(rank).padStart(2,'0')}</span><div><strong>${radarEscape(name)}</strong><small>${radarEscape(row.topic_context||'Tendencia')} · ${frequency(name)} ${frequency(name)===1?'corte':'cortes'}</small></div></div><b>#${radarNumber(rank)}</b></li>`}).join('')}</ol>`:'<div class="radar-empty-state">Todavía no hay tendencias de X guardadas para este corte.</div>'}</article>
    <article class="radar-panel radar-x-history"><header><div><span class="radar-eyebrow">PERSISTENCIA</span><h4>Temas que reaparecen</h4></div><small>Semanas con captura</small></header>${radarRank(recurring,row=>radarEscape(row.name),row=>row.weeks,row=>`${row.weeks} ${row.weeks===1?'semana':'semanas'} con presencia`,(_value,row)=>`${radarNumber(row.weeks)} ${row.weeks===1?'corte':'cortes'}`)}</article></div>
    <p class="radar-method-note">Cobertura: tendencias reportadas por X para Colombia en la fecha seleccionada. Este endpoint no incluye conteos de publicaciones, impresiones, vistas o interacciones. La persistencia compara presencia en cortes guardados, no volumen ni crecimiento de conversación.</p>`;
}
function renderRadar(data){
  if(radarPlatform==='x'){renderXRadar(data);return}
  const root=document.querySelector('#trend-radar-dashboard');if(!root)return;
  const hashtags=data.hashtags||[],posts=data.posts||[],sounds=data.sounds||[],globalSounds=data.global_sounds||[];
  const views=posts.reduce((sum,row)=>sum+Number(row.views||0),0),interactions=posts.reduce((sum,row)=>sum+radarInteractions(row),0),sources=data.sources||{};
  root.innerHTML=`<section class="radar-evolution"><header><div><span class="radar-eyebrow">HISTÓRICO SEMANAL</span><h3>Qué gana y qué pierde fuerza</h3><p>Comparación de conversaciones a través de los cortes guardados.</p></div><span class="radar-history-count">${radarWeeks.length} semanas con captura</span></header>${trendChart(radarHistory,radarWeeks)}</section><div class="radar-summary"><div><span class="radar-eyebrow">${radarEscape(data.period_label||'LECTURA SEMANAL')}</span><h3>Señales para explorar</h3><p>${radarEscape(data.target_date||'')} · Evidencia consultada en BigQuery · ${radarEscape(data.market||'CO')}</p></div><span class="radar-bq-badge"><i></i> BigQuery</span></div>
    <div class="radar-kpis"><article><span>CONVERSACIONES</span><strong>${radarNumber(hashtags.length)}</strong><small>hashtags del corte</small></article><article><span>PUBLICACIONES</span><strong>${radarNumber(posts.length)}</strong><small>encontradas esta semana</small></article><article><span>VISTAS OBSERVADAS</span><strong>${radarNumber(views)}</strong><small>en la muestra de publicaciones</small></article><article><span>INTERACCIONES</span><strong>${radarNumber(interactions)}</strong><small>me gusta, comentarios y compartidos</small></article><article><span>AUDIOS</span><strong>${radarNumber(sounds.length)}</strong><small>asociados a publicaciones observadas</small></article></div>
    <div class="radar-panels"><article class="radar-panel radar-topics"><header><div><span class="radar-eyebrow">TEMAS</span><h4>Conversaciones detectadas</h4></div><small>Hashtags · ${radarEscape(sources.hashtags||'últimos 7 días')}</small></header>${radarRank(hashtags,row=>`#${radarEscape(row.hashtag_name)}`,row=>Number(row.views||row.publish_count||0),row=>`${radarNumber(row.publish_count)} publicaciones · ${radarNumber(row.views)} vistas estimadas`)}</article>
    <article class="radar-panel radar-posts"><header><div><span class="radar-eyebrow">CONTENIDO</span><h4>Publicaciones destacadas</h4></div><small>Ordenadas por interacciones</small></header>${radarRank(posts,radarPostTitle,row=>radarInteractions(row),row=>`${radarEscape(row.author||'Cuenta desconocida')} · ${radarNumber(row.views)} vistas · ${radarNumber(radarInteractions(row))} interacciones`)}</article>
    <article class="radar-panel radar-audios"><header><div><span class="radar-eyebrow">SONIDO · CO</span><h4>Audios en publicaciones</h4></div><small>Uso dentro de la muestra</small></header>${radarRank(sounds,row=>radarEscape(row.sound_name||'Audio sin título'),row=>Number(row.video_count||0),row=>`${radarEscape(row.sound_author||'Artista sin identificar')} · ${radarNumber(row.video_count)} publicaciones · ${radarNumber(row.views)} vistas`)}</article>
    <article class="radar-panel radar-global-audios"><header><div><span class="radar-eyebrow">CHART · GLOBAL</span><h4>Top y virales</h4></div><small>Top 50 + Viral 50</small></header>${radarRank(globalSounds,row=>radarEscape(row.sound_name||'Audio sin título'),row=>Math.max(1,51-Number(row.chart_rank||50)),row=>`${radarEscape(row.sound_author||'Artista sin identificar')} · ${Number(row.chart_scene)===1?'viral':'top'}`,(_value,row)=>row.chart_rank?`#${radarNumber(row.chart_rank)}`:'Posición N/D')}</article></div>
    <p class="radar-method-note">Cobertura: hashtags de los últimos 7 días; publicaciones de la semana en curso; charts de audio sin filtro de país, por lo que se presentan como referencia global. Vistas e interacciones son de la muestra encontrada, no del total de TikTok.</p>`;
}
function setStatus(message){const status=document.querySelector('#weekly-status');if(status)status.textContent=message}
async function loadWeeks(platform=radarPlatform){
  const data=await fetchRadarWeeks(platform);renderRadarWeeks(data,platform);return data;
}
async function fetchRadarWeeks(platform){
  const response=await fetch(`/api/trends/radar/weeks?market=CO&platform=${encodeURIComponent(platform)}`,{headers:authHeaders()}),data=await response.json();if(!response.ok)throw Error(data.detail||'No se pudieron consultar las semanas.');
  radarCache.set(`weeks:${platform}`,{data,savedAt:Date.now()});return data;
}
function renderRadarWeeks(data,platform){
  if(platform!==radarPlatform)return;
  radarWeeks=data;const select=document.querySelector('#radar-week');if(!select)return;
  const previous=select.value;select.innerHTML='<option value="">Última semana disponible</option>'+data.map(item=>{const start=new Date(`${item.week_start}T12:00:00`),end=new Date(start);end.setDate(end.getDate()+6);const fmt=new Intl.DateTimeFormat('es-CO',{day:'2-digit',month:'short'});return `<option value="${radarEscape(item.week_start)}" data-date="${radarEscape(item.latest_date)}">${fmt.format(start)} – ${fmt.format(end)} · ${item.snapshot_days} ${item.snapshot_days===1?'día':'días'} con captura</option>`}).join('');
  if(previous&&[...select.options].some(option=>option.value===previous))select.value=previous;
}
function cachedRadarValue(key,ttl){const value=radarCache.get(key);return value?{data:value.data,fresh:Date.now()-value.savedAt<ttl}:null}
function invalidateRadarCache(platform){for(const key of radarCache.keys())if(key.endsWith(`:${platform}`)||key.startsWith(`${platform}:`))radarCache.delete(key)}
async function loadRadar(weekStart='',platform=null){
  const root=document.querySelector('#trend-radar-dashboard');if(!root)return;
  radarPlatform=platform||document.querySelector('#radar-platform')?.value||'tiktok';
  const requestId=++radarLoadSequence,currentPlatform=radarPlatform;
  try{
    const selected=weekStart||document.querySelector('#radar-week')?.value||'';
    const radarKey=`${currentPlatform}:${selected||'latest'}`,historyKey=`history:${currentPlatform}`,weeksKey=`weeks:${currentPlatform}`;
    const cachedRadar=cachedRadarValue(radarKey,RADAR_TTL_MS),cachedHistory=cachedRadarValue(historyKey,RADAR_HISTORY_TTL_MS),cachedWeeks=cachedRadarValue(weeksKey,RADAR_WEEKS_TTL_MS);
    const hasCachedView=Boolean(cachedRadar&&cachedHistory&&cachedWeeks);
    if(hasCachedView){
      radarHistory=cachedHistory.data;radarWeeks=cachedWeeks.data;renderRadarWeeks(radarWeeks,currentPlatform);root.dataset.loaded='true';root.dataset.platform=currentPlatform;renderRadar(cachedRadar.data);
      if(cachedRadar.fresh&&cachedHistory.fresh&&cachedWeeks.fresh){setStatus(`Datos guardados en BigQuery · corte ${cachedRadar.data.target_date} · caché local.`);return}
    }else if(!root.dataset.loaded||root.dataset.platform!==currentPlatform){root.dataset.loaded='';root.innerHTML=`<div class="radar-loading" role="status" aria-live="polite">Cargando señales de ${currentPlatform==='x'?'X':'TikTok'}…</div>`}
    setStatus(hasCachedView?'Mostrando datos guardados · actualizando en segundo plano…':'Consultando señales guardadas en BigQuery…');
    const [radarResponse,historyResponse,weeksData]=await Promise.all([
      fetch(`/api/trends/radar?market=CO&platform=${encodeURIComponent(currentPlatform)}${selected?`&week_start=${encodeURIComponent(selected)}`:''}`,{headers:authHeaders()}),
      fetch(`/api/trends/radar/history?market=CO&weeks=12&platform=${encodeURIComponent(currentPlatform)}`,{headers:authHeaders()}),
      fetchRadarWeeks(currentPlatform)
    ]);
    const [data,history]=await Promise.all([radarResponse.json(),historyResponse.json()]);
    if(!radarResponse.ok)throw Error(data.detail||'No se pudo cargar el radar.');
    if(!historyResponse.ok)throw Error(history.detail||'No se pudo consultar el histórico semanal.');
    radarCache.set(radarKey,{data,savedAt:Date.now()});radarCache.set(historyKey,{data:history,savedAt:Date.now()});
    if(requestId!==radarLoadSequence)return;
    radarHistory=history;radarWeeks=weeksData;renderRadarWeeks(weeksData,currentPlatform);
    if(!selected){const newest=weeksData[0];if(newest){const select=document.querySelector('#radar-week');if(select)select.value=newest.week_start}}
    root.dataset.loaded='true';root.dataset.platform=currentPlatform;renderRadar(data);setStatus(currentPlatform==='x'&&!data.topics?.length?'Aún no hay cortes de X guardados. Usa “Recolectar tendencias de X” para iniciar uno.':`Datos guardados en BigQuery · corte ${data.target_date}.`);
  }catch(error){if(requestId!==radarLoadSequence)return;if(root.dataset.loaded){setStatus(`No se pudo actualizar. Se conserva la última lectura. ${error.message}`)}else{setStatus(error.message);root.innerHTML=`<div class="radar-empty-state">${radarEscape(error.message)}</div>`}}
}
async function pollRadarRun(runId,targetDate,status,label,scene=null){
  for(let attempt=0;attempt<40;attempt++){
    const sceneQuery=scene===null?'':`&scene=${scene}`;const response=await fetch(`/api/trends/radar/run/${encodeURIComponent(runId)}?target_date=${targetDate}${sceneQuery}`,{headers:authHeaders()});
    const text=await response.text();let data;try{data=JSON.parse(text)}catch{throw Error(`Error consultando ${label} (${response.status}): ${text.slice(0,220)}`)}
    if(!response.ok)throw Error(data.detail||`No se pudo consultar ${label}.`);
    const state=String(data.run?.status||'').toUpperCase();if(state==='COMPLETED')return data.run;if(state==='FAILED'||state==='ERROR')throw Error(`La ejecución de ${label} falló.`);
    if(status)status.textContent=`Recolectando ${label}…`;await new Promise(resolve=>setTimeout(resolve,3000));
  }
  throw Error(`La búsqueda de ${label} sigue en curso. Vuelve a actualizar en un momento.`);
}
document.addEventListener('DOMContentLoaded',()=>{
  const button=document.querySelector('#run-trend-radar');if(!button)return;
  const platformSelect=document.querySelector('#radar-platform');
  const updateCollectLabel=()=>{const label=button.childNodes[0];if(label?.nodeType===Node.TEXT_NODE)label.textContent=platformSelect?.value==='x'?'Recolectar tendencias de X ':'Recolectar esta semana '};
  updateCollectLabel();
  const startAutoLoad=()=>{if(!window.getAccessToken?.())return;loadRadar()};
  window.addEventListener('auth:changed',event=>{if(event.detail?.authenticated)startAutoLoad()});startAutoLoad();
  document.querySelector('#radar-week')?.addEventListener('change',event=>loadRadar(event.target.value,radarPlatform));
  platformSelect?.addEventListener('change',event=>{const weekSelect=document.querySelector('#radar-week');if(weekSelect)weekSelect.value='';updateCollectLabel();loadRadar('',event.target.value)});
  button.onclick=async()=>{
    const targetDate=radarDateKey(),status=document.querySelector('#weekly-status'),weekSelect=document.querySelector('#radar-week'),platformSelect=document.querySelector('#radar-platform'),platform=platformSelect?.value||'tiktok';button.disabled=true;
    try{
      if(status)status.textContent=platform==='x'?'Buscando tendencias de X en Colombia…':'Buscando hashtags y temas de los últimos 7 días…';
      const response=await fetch('/api/trends/radar/run',{method:'POST',headers:{...authHeaders(),'Content-Type':'application/json'},body:JSON.stringify({market:'CO',target_date:targetDate,platform})});
      const text=await response.text();let data;try{data=JSON.parse(text)}catch{throw Error(`No se pudo iniciar la recolección (${response.status}): ${text.slice(0,220)}`)}
      if(!response.ok)throw Error(data.detail||'No se pudo iniciar el radar.');
      const completedRuns=[];
      for(const [index,run] of (data.runs||[]).entries()){const id=run.runId||run.run_id;if(!id)continue;const endpoint=String(run.endpoint||''),isChart=endpoint.endsWith('fetch_music_chart_list'),isX=endpoint.includes('/twitter/');completedRuns.push(await pollRadarRun(id,targetDate,status,isX?'tendencias de X':isChart?'chart de audios':'hashtags',isChart?index-1:null))}
      if(platform==='x'){
        if(weekSelect)weekSelect.value='';invalidateRadarCache(platform);await loadRadar('',platform);
        if(status)status.textContent=`Tendencias de X guardadas en BigQuery · captura ${targetDate}.`;
        return;
      }
      const hashtagRun=completedRuns.find(run=>String(run.endpoint||'').endsWith('get_trends_hashtag_list'));
      const discovered=(hashtagRun?.output?.items||[]).map(item=>item.hashtagName).filter(Boolean).slice(0,20);
      if(!discovered.length)throw Error('La fuente no devolvió hashtags; no se lanzó la búsqueda de publicaciones.');
      if(status)status.textContent=`Señales encontradas: ${discovered.length}. Buscando publicaciones y audios asociados…`;
      const enrich=await fetch('/api/trends/radar/enrich',{method:'POST',headers:{...authHeaders(),'Content-Type':'application/json'},body:JSON.stringify({market:'CO',target_date:targetDate,hashtags:discovered})});
      const enrichText=await enrich.text();let enrichData;try{enrichData=JSON.parse(enrichText)}catch{throw Error(`No se pudo iniciar la búsqueda de contenido (${enrich.status}): ${enrichText.slice(0,220)}`)}
      if(!enrich.ok)throw Error(enrichData.detail||'No se pudieron buscar publicaciones.');
      await pollRadarRun(enrichData.runId||enrichData.run_id,targetDate,status,'publicaciones y audios');invalidateRadarCache(platform);
      await loadWeeks(platform);if(weekSelect){const monday=new Date(`${targetDate}T12:00:00`);monday.setDate(monday.getDate()-((monday.getDay()+6)%7));weekSelect.value=`${monday.getFullYear()}-${String(monday.getMonth()+1).padStart(2,'0')}-${String(monday.getDate()).padStart(2,'0')}`}await loadRadar(weekSelect?.value||'',platform);if(status)status.textContent=`Lectura semanal guardada en BigQuery · captura ${targetDate}.`;
    }catch(error){if(status)status.textContent=error.message}
    finally{button.disabled=false}
  };
});
