const radarEscape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const yesterdayKey=()=>{const d=new Date();d.setHours(12,0,0,0);d.setDate(d.getDate()-1);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`};
const radarNumber=value=>Number(value||0).toLocaleString('es-CO');
function renderRadar(data){
  const root=document.querySelector('#trend-radar-dashboard'); if(!root)return;
  const hashtags=data.hashtags||[], posts=data.posts||[], sounds=data.sounds||[];
  const topViews=hashtags.reduce((sum,row)=>sum+Number(row.views||0),0);
  root.innerHTML=`<div class="radar-header"><div><div class="story-kicker">RADAR · ${radarEscape(data.target_date)}</div><h3>Señales detectadas en Colombia</h3></div><span class="radar-source">Fuente: BigQuery</span></div><div class="radar-metrics"><div><span>HASHTAGS</span><strong>${radarNumber(hashtags.length)}</strong></div><div><span>VISTAS ESTIMADAS</span><strong>${radarNumber(topViews)}</strong></div><div><span>PUBLICACIONES</span><strong>${radarNumber(posts.length)}</strong></div></div><div class="radar-grid"><article><h4>Conversaciones emergentes</h4>${hashtags.length?`<ol class="radar-list">${hashtags.slice(0,10).map(row=>`<li><div><strong>#${radarEscape(row.hashtag_name)}</strong><small>${radarNumber(row.publish_count)} publicaciones · ${radarNumber(row.views)} vistas</small></div><b>#${radarEscape(row.rank_index)}</b></li>`).join('')}</ol>`:'<p class="radar-muted">No hubo hashtags disponibles para esta fecha.</p>'}</article><article><h4>Publicaciones principales</h4>${posts.length?`<ol class="radar-list">${posts.slice(0,10).map(row=>`<li><div><strong>${radarEscape(row.title||'Sin título')}</strong><small>${radarEscape(row.author||'Sin autor')} · ${radarNumber(Number(row.likes||0)+Number(row.comments||0)+Number(row.shares||0))} interacciones</small></div><b>${radarNumber(row.views)}</b></li>`).join('')}</ol>`:'<p class="radar-muted">TikHub no devolvió contenidos destacados para Colombia en esta ejecución.</p>'}</article><article><h4>Audios detectados</h4>${sounds.length?`<ol class="radar-list">${sounds.slice(0,10).map(row=>`<li><div><strong>${radarEscape(row.sound_name||'Sin nombre')}</strong><small>${radarEscape(row.sound_author||'Sin autor')} · ${radarNumber(row.video_count)} videos</small></div><b>${radarNumber(row.views)}</b></li>`).join('')}</ol>`:'<p class="radar-muted">No hay datos de audio en esta fuente para la ejecución.</p>'}</article></div>`;
}
async function loadRadar(targetDate=''){
  const root=document.querySelector('#trend-radar-dashboard'); if(!root)return;
  root.innerHTML='<div class="radar-loading">Cargando la última información persistida en BigQuery...</div>';
  try{
    const query=targetDate?`?market=CO&target_date=${targetDate}`:'?market=CO';
    const response=await fetch(`/api/trends/radar${query}`,{headers:authHeaders()});
    const data=await response.json(); if(!response.ok)throw Error(data.detail||'No se pudo cargar el radar.');
    renderRadar(data);
  }catch(error){root.innerHTML=`<div class="radar-empty">${radarEscape(error.message)}</div>`}
}
document.addEventListener('DOMContentLoaded',()=>{
  const button=document.querySelector('#run-trend-radar'); if(!button)return;
  let refreshTimer=null;
  const startAutoLoad=()=>{if(!window.getAccessToken?.())return;loadRadar();if(!refreshTimer)refreshTimer=window.setInterval(()=>loadRadar(),300000)};
  window.addEventListener('auth:changed',event=>{if(event.detail?.authenticated)startAutoLoad()});
  startAutoLoad();
  button.onclick=async()=>{
    const targetDate=yesterdayKey(), status=document.querySelector('#weekly-status');
    const weekInput=document.querySelector('#week-start'); if(weekInput)weekInput.value=targetDate;
    button.disabled=true; if(status)status.textContent=`Iniciando radar para ${targetDate}...`;
    try{
      const start=await fetch('/api/trends/radar/run',{method:'POST',headers:{...authHeaders(),'Content-Type':'application/json'},body:JSON.stringify({market:'CO',target_date:targetDate})});
      const startText=await start.text(); let data; try{data=JSON.parse(startText)}catch{throw Error(`Error del servidor (${start.status}): ${startText.slice(0,240)}`)}
      if(!start.ok)throw Error(data.detail||'No se pudo iniciar el radar.');
      const runIds=(data.runs||[]).map(run=>run.runId||run.run_id).filter(Boolean); let done=0; const completedRuns=[];
      for(const runId of runIds){
        let current='RUNNING', lastResult=null;
        for(let attempt=0;attempt<40&&current==='RUNNING';attempt++){
          const response=await fetch(`/api/trends/radar/run/${encodeURIComponent(runId)}?target_date=${targetDate}`,{headers:authHeaders()});
          const text=await response.text(); let result; try{result=JSON.parse(text)}catch{throw Error(`Error consultando el radar (${response.status}): ${text.slice(0,240)}`)}
          if(!response.ok)throw Error(result.detail||'No se pudo consultar el radar.');
          lastResult=result;
          current=String(result.run?.status||'').toUpperCase();
          if(current==='FAILED'||current==='ERROR')throw Error(`Falló la ejecución ${runId}.`);
          if(current==='RUNNING'){if(status)status.textContent=`Radar en progreso: ${done+1} de ${runIds.length}...`;await new Promise(resolve=>setTimeout(resolve,3000));}
        }
        if(current!=='COMPLETED')throw Error(`La ejecución ${runId} sigue en progreso.`); done++; if(lastResult?.run)completedRuns.push(lastResult.run);
      }
      const hashtagRun=completedRuns.find(run=>String(run.endpoint||'').endsWith('get_trends_hashtag_list'));
      const discovered=(hashtagRun?.output?.items||[]).map(item=>item.hashtagName).filter(Boolean).slice(0,20);
      if(discovered.length){
        if(status)status.textContent=`Hashtags detectados: ${discovered.length}. Buscando publicaciones...`;
        const enrich=await fetch('/api/trends/radar/enrich',{method:'POST',headers:{...authHeaders(),'Content-Type':'application/json'},body:JSON.stringify({market:'CO',target_date:targetDate,hashtags:discovered})});
        const enrichText=await enrich.text(); let enrichData; try{enrichData=JSON.parse(enrichText)}catch{throw Error(`Error enriqueciendo el radar (${enrich.status}): ${enrichText.slice(0,240)}`)}
        if(!enrich.ok)throw Error(enrichData.detail||'No se pudieron buscar las publicaciones.');
        const enrichId=enrichData.runId||enrichData.run_id; let current='RUNNING';
        for(let attempt=0;attempt<40&&current==='RUNNING';attempt++){
          const response=await fetch(`/api/trends/radar/run/${encodeURIComponent(enrichId)}?target_date=${targetDate}`,{headers:authHeaders()});
          const text=await response.text(); let result; try{result=JSON.parse(text)}catch{throw Error(`Error consultando publicaciones (${response.status}): ${text.slice(0,240)}`)}
          if(!response.ok)throw Error(result.detail||'No se pudo consultar publicaciones.');
          current=String(result.run?.status||'').toUpperCase();
          if(current==='FAILED'||current==='ERROR')throw Error(`Falló la búsqueda de publicaciones ${enrichId}.`);
          if(current==='RUNNING'){if(status)status.textContent='Buscando publicaciones de las conversaciones detectadas...';await new Promise(resolve=>setTimeout(resolve,3000));}
        }
        if(current!=='COMPLETED')throw Error(`La búsqueda de publicaciones sigue en progreso: ${enrichId}`);
      }
      const response=await fetch(`/api/trends/radar?market=CO&target_date=${targetDate}`,{headers:authHeaders()});
      const result=await response.json(); if(!response.ok)throw Error(result.detail||'No se pudo leer el radar guardado.');
      renderRadar(result); if(status)status.textContent=`Radar completado y guardado en BigQuery para ${targetDate}.`;
    }catch(error){if(status)status.textContent=error.message}
    finally{button.disabled=false}
  };
});
