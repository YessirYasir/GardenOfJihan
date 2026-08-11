const token = document.querySelector('meta[name="goj-token"]').content;
const screens = [...document.querySelectorAll('.screen')];
const stepButtons = [...document.querySelectorAll('.step')];
const back = document.getElementById('backStep');
const next = document.getElementById('nextStep');
const stepCount = document.getElementById('stepCount');
let step = 0;
let source = {url:null, uploadId:null};
let currentJob = null;
let candidates = [];
let selected = new Set();

function api(path, options={}) {
  const headers = new Headers(options.headers || {});
  if (options.method && options.method !== 'GET') headers.set('X-GOJ-Token', token);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type','application/json');
  return fetch(path, {...options, headers});
}
function showStep(n){
  step=Math.max(0,Math.min(5,n));
  screens.forEach((el,i)=>el.classList.toggle('active',i===step));
  stepButtons.forEach((el,i)=>{el.classList.toggle('active',i===step);el.classList.toggle('done',i<step)});
  stepCount.textContent=`Step ${step+1} of 6`;
  back.disabled=step===0;
  next.textContent=step===5?'Start over ↻':'Next →';
  document.querySelector('.workspace').scrollIntoView({behavior:'smooth',block:'start'});
}
back.addEventListener('click',()=>showStep(step-1));
next.addEventListener('click',()=>step===5?showStep(0):showStep(step+1));
stepButtons.forEach(btn=>btn.addEventListener('click',()=>showStep(Number(btn.dataset.step))));

const sourceMessage=document.getElementById('sourceMessage');
document.getElementById('inspectSource').addEventListener('click', async()=>{
  const url=document.getElementById('sourceUrl').value.trim();
  sourceMessage.classList.remove('hidden','error');
  sourceMessage.textContent='Checking source safely…';
  try{
    const res=await api('/api/source/inspect',{method:'POST',body:JSON.stringify({url})});
    const data=await res.json();
    if(!res.ok) throw new Error(data.detail || 'Could not inspect source');
    source={url:data.url,uploadId:null};
    const duration=data.duration?` • ${Math.round(data.duration/60)} min`:'';
    sourceMessage.innerHTML=`<strong>Ready:</strong> ${escapeHtml(data.title || data.provider)}${duration}`;
  }catch(err){sourceMessage.classList.add('error');sourceMessage.textContent=err.message;}
});

const fileInput=document.getElementById('fileInput');
const fileMessage=document.getElementById('fileMessage');
fileInput.addEventListener('change', async()=>{
  if(!fileInput.files.length)return;
  fileMessage.classList.remove('hidden','error');
  fileMessage.textContent='Copying video into an isolated local job…';
  const form=new FormData();form.append('file',fileInput.files[0]);
  try{
    const res=await api('/api/upload',{method:'POST',body:form});
    const data=await res.json();
    if(!res.ok) throw new Error(data.detail || 'Upload failed');
    source={url:null,uploadId:data.upload_id};
    fileMessage.innerHTML=`<strong>Ready:</strong> ${escapeHtml(fileInput.files[0].name)} • local only`;
  }catch(err){fileMessage.classList.add('error');fileMessage.textContent=err.message;}
});

function selectedMode(){return document.querySelector('input[name="mode"]:checked').value;}
function setProgress(value,label){
  document.getElementById('progressValue').textContent=`${value}%`;
  document.getElementById('progressBar').style.width=`${value}%`;
  document.getElementById('progressLabel').textContent=label;
  [['phase1',15],['phase2',38],['phase3',65],['phase4',90]].forEach(([id,threshold])=>document.getElementById(id).classList.toggle('done',value>=threshold));
}

document.getElementById('startAnalysis').addEventListener('click',async()=>{
  const error=document.getElementById('analysisError');error.classList.add('hidden');
  if(!source.url && !source.uploadId){error.textContent='Add a video first.';error.classList.remove('hidden');return;}
  setProgress(4,'Creating secure job…');
  const body={url:source.url,upload_id:source.uploadId,mode:selectedMode(),min_clip_seconds:Number(document.getElementById('minSeconds').value),max_clip_seconds:Number(document.getElementById('maxSeconds').value),max_clips:Number(document.getElementById('maxClips').value)};
  try{
    const res=await api('/api/jobs/analyze',{method:'POST',body:JSON.stringify(body)});const data=await res.json();if(!res.ok)throw new Error(data.detail||'Could not start analysis');
    currentJob=data.job_id;pollJob();
  }catch(err){error.textContent=err.message;error.classList.remove('hidden');}
});
async function pollJob(){
  try{
    const res=await api(`/api/jobs/${currentJob}`);const data=await res.json();if(!res.ok)throw new Error(data.detail||'Job failed');
    setProgress(data.progress,data.message);
    if(data.status==='failed')throw new Error(data.error||'Analysis failed');
    if(data.status==='complete'){
      candidates=data.candidates||[];selected=new Set(candidates.filter(c=>c.score>=85).map(c=>c.id));renderCandidates();showStep(4);return;
    }
    setTimeout(pollJob,900);
  }catch(err){const box=document.getElementById('analysisError');box.textContent=err.message;box.classList.remove('hidden');}
}
function renderCandidates(){
  const grid=document.getElementById('candidateGrid');grid.innerHTML='';
  document.getElementById('emptyCandidates').classList.toggle('hidden',candidates.length>0);
  if(currentJob)document.getElementById('sourcePreview').src=`/api/jobs/${currentJob}/source`;
  candidates.forEach((c,index)=>{
    const card=document.createElement('article');card.className='candidate';
    const breakdown=Object.entries(c.score_breakdown||{}).filter(([,v])=>Number(v)>0).sort((a,b)=>b[1]-a[1]).slice(0,4);
    card.innerHTML=`<div class="candidate-head"><div><h3>${escapeHtml(c.title)} #${index+1}</h3><small>${formatTime(c.start)} → ${formatTime(c.end)}</small></div><div class="score">${Math.round(c.score)}</div></div><div class="score-breakdown">${breakdown.map(([k,v])=>`<span><b>${escapeHtml(scoreLabel(k))}</b>${Math.round(v)}</span>`).join('')}</div><ul class="reason-list">${c.reasons.map(r=>`<li>${escapeHtml(r)}</li>`).join('')}</ul><div class="candidate-actions"><button class="secondary preview">Preview</button><button class="keep ${selected.has(c.id)?'on':''}">${selected.has(c.id)?'Kept':'Keep'}</button></div>`;
    card.querySelector('.preview').addEventListener('click',()=>{const video=document.getElementById('sourcePreview');video.currentTime=c.start;video.play();setTimeout(()=>{if(video.currentTime>=c.end)video.pause()},Math.max(1000,(c.end-c.start)*1000));video.scrollIntoView({behavior:'smooth',block:'center'});});
    const keep=card.querySelector('.keep');keep.addEventListener('click',()=>{if(selected.has(c.id))selected.delete(c.id);else selected.add(c.id);keep.classList.toggle('on',selected.has(c.id));keep.textContent=selected.has(c.id)?'Kept':'Keep';syncExportSummary();});
    grid.appendChild(card);
  });syncExportSummary();
}
document.getElementById('selectStrong').addEventListener('click',()=>{selected=new Set(candidates.filter(c=>c.score>=85).map(c=>c.id));renderCandidates();});
function syncExportSummary(){document.getElementById('selectedCount').textContent=selected.size;document.getElementById('exportAspect').textContent=document.getElementById('aspect').value;}

document.getElementById('renderClips').addEventListener('click',async()=>{
  const box=document.getElementById('exportMessage');const list=document.getElementById('downloadList');list.innerHTML='';box.classList.remove('hidden','error');
  if(!currentJob||selected.size===0){box.textContent='Choose at least one clip first.';return;}
  box.textContent='Rendering locally with FFmpeg…';
  try{
    const res=await api(`/api/jobs/${currentJob}/export`,{method:'POST',body:JSON.stringify({candidate_ids:[...selected],aspect:document.getElementById('aspect').value})});const data=await res.json();if(!res.ok)throw new Error(data.detail||'Render failed');
    box.innerHTML=`<strong>Ready.</strong> ${data.files.length} clip${data.files.length===1?'':'s'} rendered.`;
    data.files.forEach(file=>{const a=document.createElement('a');a.className='download-link';a.href=file.url;a.download=file.name;a.innerHTML=`<span>${escapeHtml(file.name)}</span><strong>Save ↓</strong>`;list.appendChild(a);});
  }catch(err){box.classList.add('error');box.textContent=err.message;}
});

window.addEventListener('scroll',()=>{
  const y=Math.min(window.scrollY,900);
  document.querySelector('.hill-back').style.transform=`translateY(${y*.025}px)`;
  document.querySelector('.hill-front').style.transform=`translateY(${y*.05}px)`;
});
function scoreLabel(key){return ({hook:'Hook',emotion:'Emotion',curiosity:'Curiosity',payoff:'Payoff',completeness:'Complete',density:'Density',novelty:'Novelty',audio:'Audio',visual:'Visual',replay:'Replay'}[key]||key);}
function formatTime(sec){sec=Math.max(0,Math.floor(sec));const m=Math.floor(sec/60);const s=sec%60;return `${m}:${String(s).padStart(2,'0')}`;}
function escapeHtml(value){return String(value).replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));}
showStep(0);
