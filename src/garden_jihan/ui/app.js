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
let boundaries = {};

function api(path, options={}) {
  const headers = new Headers(options.headers || {});
  if (options.method && options.method !== 'GET') headers.set('X-GOJ-Token', token);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type','application/json');
  return fetch(path, {...options, headers});
}
function showStep(n,{scroll=true}={}){
  step=Math.max(0,Math.min(5,n));
  screens.forEach((el,i)=>el.classList.toggle('active',i===step));
  stepButtons.forEach((el,i)=>{el.classList.toggle('active',i===step);el.classList.toggle('done',i<step)});
  stepCount.textContent=`Step ${step+1} of 6`;
  back.disabled=step===0;
  next.textContent=step===5?'Start over ↻':'Next →';
  if(scroll)document.querySelector('.workspace').scrollIntoView({behavior:'smooth',block:'start'});
}
back.addEventListener('click',()=>showStep(step-1));
next.addEventListener('click',()=>step===5?showStep(0):showStep(step+1));
stepButtons.forEach(btn=>btn.addEventListener('click',()=>showStep(Number(btn.dataset.step))));

const sourceMessage=document.getElementById('sourceMessage');
const inspectSourceButton=document.getElementById('inspectSource');
inspectSourceButton.addEventListener('click', async()=>{
  const url=document.getElementById('sourceUrl').value.trim();
  sourceMessage.classList.remove('hidden','error');
  sourceMessage.textContent='Checking source safely…';
  inspectSourceButton.disabled=true;
  try{
    const res=await api('/api/source/inspect',{method:'POST',body:JSON.stringify({url})});
    const data=await res.json();
    if(!res.ok) throw new Error(data.detail || 'Could not inspect source');
    source={url:data.url,uploadId:null};
    const duration=data.duration?` • ${Math.round(data.duration/60)} min`:'';
    sourceMessage.innerHTML=`<strong>Ready:</strong> ${escapeHtml(data.title || data.provider)}${duration}`;
  }catch(err){sourceMessage.classList.add('error');sourceMessage.textContent=err.message;}
  finally{inspectSourceButton.disabled=false;}
});

const fileInput=document.getElementById('fileInput');
const fileMessage=document.getElementById('fileMessage');
fileInput.addEventListener('change', async()=>{
  if(!fileInput.files.length)return;
  fileMessage.classList.remove('hidden','error');
  fileMessage.textContent='Copying video into an isolated local job…';
  fileInput.disabled=true;
  const form=new FormData();form.append('file',fileInput.files[0]);
  try{
    const res=await api('/api/upload',{method:'POST',body:form});
    const data=await res.json();
    if(!res.ok) throw new Error(data.detail || 'Upload failed');
    source={url:null,uploadId:data.upload_id};
    fileMessage.innerHTML=`<strong>Ready:</strong> ${escapeHtml(fileInput.files[0].name)} • local only`;
  }catch(err){fileMessage.classList.add('error');fileMessage.textContent=err.message;}
  finally{fileInput.disabled=false;}
});

function selectedMode(){return document.querySelector('input[name="mode"]:checked').value;}
function setProgress(value,label){
  const progress=Math.max(0,Math.min(100,Number(value)||0));
  document.getElementById('progressValue').textContent=`${progress}%`;
  document.getElementById('progressBar').style.width=`${progress}%`;
  document.getElementById('progressTrack').setAttribute('aria-valuenow',String(progress));
  document.getElementById('analysisGarden').style.setProperty('--growth',`${progress}%`);
  document.getElementById('progressLabel').textContent=label;
  [['phase1','growth1',15],['phase2','growth2',38],['phase3','growth3',65],['phase4','growth4',90]].forEach(([phaseId,growthId,threshold])=>{
    document.getElementById(phaseId).classList.toggle('done',progress>=threshold);
    document.getElementById(growthId).classList.toggle('grown',progress>=threshold);
  });
}

const startAnalysisButton=document.getElementById('startAnalysis');
let analysisBusy=false;
function setAnalysisBusy(busy){
  analysisBusy=busy;
  startAnalysisButton.disabled=busy;
  startAnalysisButton.setAttribute('aria-busy',String(busy));
}
startAnalysisButton.addEventListener('click',async()=>{
  if(analysisBusy)return;
  const error=document.getElementById('analysisError');error.classList.add('hidden');
  if(!source.url && !source.uploadId){error.textContent='Add a video first.';error.classList.remove('hidden');return;}
  setAnalysisBusy(true);
  setProgress(4,'Creating secure job…');
  const body={url:source.url,upload_id:source.uploadId,mode:selectedMode(),min_clip_seconds:Number(document.getElementById('minSeconds').value),max_clip_seconds:Number(document.getElementById('maxSeconds').value),max_clips:Number(document.getElementById('maxClips').value)};
  try{
    const res=await api('/api/jobs/analyze',{method:'POST',body:JSON.stringify(body)});const data=await res.json();if(!res.ok)throw new Error(data.detail||'Could not start analysis');
    currentJob=data.job_id;pollJob();
  }catch(err){setAnalysisBusy(false);error.textContent=err.message;error.classList.remove('hidden');}
});
async function pollJob(){
  try{
    const res=await api(`/api/jobs/${currentJob}`);const data=await res.json();if(!res.ok)throw new Error(data.detail||'Job failed');
    setProgress(data.progress,data.message);
    if(data.status==='failed')throw new Error(data.error||'Analysis failed');
    if(data.status==='complete'){
      setAnalysisBusy(false);candidates=data.candidates||[];boundaries={};selected=new Set(candidates.filter(c=>c.score>=85).map(c=>c.id));renderRankingStatus(data);renderCandidates();showStep(4);return;
    }
    setTimeout(pollJob,900);
  }catch(err){setAnalysisBusy(false);const box=document.getElementById('analysisError');box.textContent=err.message;box.classList.remove('hidden');}
}
function renderRankingStatus(data){
  const status=document.getElementById('rankingStatus');
  const method=String(data.ranking_method||'base_fallback');
  status.classList.remove('hidden','active','safe','fallback');
  if(method==='local_multilingual_embeddings'){
    status.classList.add('active');status.innerHTML='<b>Local meaning model active</b><span>Dense multilingual embeddings support topic coherence and reduce paraphrased repeats. Somali quality remains benchmark-gated.</span>';return;
  }
  if(method==='quran_safe'){
    status.classList.add('safe');status.innerHTML='<b>Qur’an-safe ranking</b><span>Uses pauses and completeness only. It does not infer Surah, Ayah, or Qira’at from semantic embeddings.</span>';return;
  }
  status.classList.add('fallback');status.innerHTML='<b>Base ranking used</b><span>The local meaning model was unavailable; no cloud or paid API fallback was used.</span>';
}
function quranMatchMarkup(match){
  if(!match)return '';
  const status=String(match.status||'uncertain');
  if(status==='reference_unavailable'||status==='reference_invalid'){
    const heading=status==='reference_invalid'?'Qur’an reference needs attention':'Qur’an reference not installed';
    return `<div class="quran-match unavailable"><div><b>${escapeHtml(heading)}</b><small>${escapeHtml(match.message||'Install the reviewed local reference before identifying Surah/Ayah.')}</small></div></div>`;
  }
  if(status!=='verified'){
    const confidence=Number(match.confidence||0);
    const confidenceText=Number.isFinite(confidence)&&confidence>0?` • ${Math.round(confidence)}% candidate confidence`:'';
    const heading=status==='possible'?'Possible Qur’an text — not identified':'Surah/Ayah uncertain';
    return `<div class="quran-match ${status==='possible'?'possible':'uncertain'}"><div><b>${escapeHtml(heading)}</b><small>${escapeHtml(match.message||'Review this passage manually before export.')}${escapeHtml(confidenceText)}</small><small class="qiraat-note">${escapeHtml(match.qiraat_message||'Qira’at is not assessed from text.')}</small></div></div>`;
  }
  const start=`${Number(match.surah)}:${Number(match.ayah)}`;
  const label=match.end_ayah?`${start}–${Number(match.end_ayah)}`:start;
  const confidence=Number(match.confidence||0);
  const confidenceText=Number.isFinite(confidence)?`${Math.round(confidence)}% confidence`:'Verified reference';
  const verses=Array.isArray(match.verses)?match.verses:[];
  const sacredText=verses.map(verse=>`<div class="quran-verse"><div class="quran-display" lang="ar" dir="rtl" translate="no">${escapeHtml(verse.text_display||'')}</div><small>${Number(verse.surah)}:${Number(verse.ayah)}</small></div>`).join('');
  const alignment=Array.isArray(match.word_alignment)?match.word_alignment:[];
  const wordTrack=alignment.length?`<div class="quran-alignment"><div class="quran-alignment-head"><b>Word alignment</b><span>${Number(match.matched_words)||0} of ${Number(match.total_words)||alignment.filter(word=>!word.optional).length} locating words</span></div><div class="quran-word-track" lang="ar" dir="rtl" translate="no">${alignment.map(word=>`<span class="${word.optional?'optional':word.matched?'matched':'missed'}" title="${word.optional?'Optional opening formula':word.matched?`${Math.round(Number(word.similarity)||0)}% aligned`:'Not aligned'}">${escapeHtml(word.reference_word||'')}</span>`).join(' ')}</div></div>`:'';
  const boundaryWarning=match.starts_mid_ayah||match.ends_mid_ayah?'<div class="quran-boundary-warning"><b>Review clip boundaries</b><small>The aligned words suggest this candidate may begin or end inside an ayah.</small></div>':'';
  return `<div class="quran-match high"><div class="quran-match-head"><b>Verified Qur’an ${escapeHtml(label)}</b><span>${escapeHtml(confidenceText)}</span></div>${sacredText}${wordTrack}${boundaryWarning}<small>${escapeHtml(match.source||'Reviewed local reference')} ${match.source_version?`v${escapeHtml(match.source_version)}`:''}</small><small class="qiraat-note">${escapeHtml(match.qiraat_message||'Qira’at is not assessed from text matching.')}</small></div>`;
}
function renderCandidates(){
  const grid=document.getElementById('candidateGrid');grid.innerHTML='';
  document.getElementById('emptyCandidates').classList.toggle('hidden',candidates.length>0);
  if(currentJob)document.getElementById('sourcePreview').src=`/api/jobs/${currentJob}/source`;
  candidates.forEach((c,index)=>{
    const card=document.createElement('article');card.className='candidate';
    const breakdown=Object.entries(c.score_breakdown||{}).filter(([,v])=>Number(v)>0).sort((a,b)=>b[1]-a[1]).slice(0,4);
    const timing=boundaries[c.id]||{start:c.start,end:c.end};
    card.innerHTML=`<div class="candidate-head"><div><h3>${escapeHtml(c.title)} #${index+1}</h3><small class="timing-label">${formatTime(timing.start)} → ${formatTime(timing.end)}</small></div><div class="score">${Math.round(c.score)}</div></div><div class="score-breakdown">${breakdown.map(([k,v])=>`<span><b>${escapeHtml(scoreLabel(k))}</b>${Math.round(v)}</span>`).join('')}</div>${quranMatchMarkup(c.quran_match)}<ul class="reason-list">${c.reasons.map(r=>`<li>${escapeHtml(r)}</li>`).join('')}</ul><div class="candidate-actions"><button class="secondary preview">Preview</button><button class="secondary adjust">Adjust timing</button><button class="keep ${selected.has(c.id)?'on':''}">${selected.has(c.id)?'Kept':'Keep'}</button></div><div class="boundary-editor hidden"><label>Start (seconds)<input class="boundary-start" type="number" min="0" step="0.1" value="${timing.start.toFixed(1)}"></label><label>End (seconds)<input class="boundary-end" type="number" min="0.1" step="0.1" value="${timing.end.toFixed(1)}"></label><button class="primary apply-boundary">Apply timing</button><small>Use this to restore context or trim a slow opening. Maximum adjusted clip: 3 minutes.</small></div>`;
    card.querySelector('.preview').addEventListener('click',()=>{const effective=boundaries[c.id]||{start:c.start,end:c.end};const video=document.getElementById('sourcePreview');video.currentTime=effective.start;video.play();setTimeout(()=>{if(video.currentTime>=effective.end)video.pause()},Math.max(1000,(effective.end-effective.start)*1000));video.scrollIntoView({behavior:'smooth',block:'center'});});
    const editor=card.querySelector('.boundary-editor');
    card.querySelector('.adjust').addEventListener('click',()=>editor.classList.toggle('hidden'));
    card.querySelector('.apply-boundary').addEventListener('click',()=>{const start=Number(card.querySelector('.boundary-start').value);const end=Number(card.querySelector('.boundary-end').value);if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start||end-start>180){window.alert('Choose a valid range up to 3 minutes.');return;}boundaries[c.id]={start,end};card.querySelector('.timing-label').textContent=`${formatTime(start)} → ${formatTime(end)}`;editor.classList.add('hidden');});
    const keep=card.querySelector('.keep');keep.addEventListener('click',()=>{if(selected.has(c.id))selected.delete(c.id);else selected.add(c.id);keep.classList.toggle('on',selected.has(c.id));keep.textContent=selected.has(c.id)?'Kept':'Keep';syncExportSummary();});
    grid.appendChild(card);
  });syncExportSummary();
}
document.getElementById('selectStrong').addEventListener('click',()=>{selected=new Set(candidates.filter(c=>c.score>=85).map(c=>c.id));renderCandidates();});
function syncCaptionControls(){
  const enabled=document.getElementById('captions').value==='segments';
  document.getElementById('captionStyle').disabled=!enabled;
  document.getElementById('captionPosition').disabled=!enabled;
  document.getElementById('exportCaptions').textContent=enabled?'Timed':'Off';
}
function syncExportSummary(){document.getElementById('selectedCount').textContent=selected.size;document.getElementById('exportAspect').textContent=document.getElementById('aspect').value;syncCaptionControls();}
document.getElementById('captions').addEventListener('change',syncExportSummary);
document.getElementById('aspect').addEventListener('change',syncExportSummary);
syncCaptionControls();

const renderClipsButton=document.getElementById('renderClips');
let exportBusy=false;
renderClipsButton.addEventListener('click',async()=>{
  if(exportBusy)return;
  const box=document.getElementById('exportMessage');const list=document.getElementById('downloadList');list.innerHTML='';box.classList.remove('hidden','error');
  if(!currentJob||selected.size===0){box.textContent='Choose at least one clip first.';return;}
  const captions=document.getElementById('captions').value==='segments';
  if(captions&&candidates.some(candidate=>selected.has(candidate.id)&&candidate.mode==='quran')){box.classList.add('error');box.textContent='Qur’an burn-in captions stay disabled until verified acoustic timing exists. Export without captions and use the reference-backed review panel.';return;}
  exportBusy=true;renderClipsButton.disabled=true;renderClipsButton.setAttribute('aria-busy','true');
  box.textContent='Rendering locally with FFmpeg…';
  try{
    const selectedBoundaries=Object.fromEntries([...selected].filter(id=>boundaries[id]).map(id=>[id,boundaries[id]]));
    const res=await api(`/api/jobs/${currentJob}/export`,{method:'POST',body:JSON.stringify({candidate_ids:[...selected],aspect:document.getElementById('aspect').value,framing:document.getElementById('framing').value,captions,caption_style:document.getElementById('captionStyle').value,caption_position:document.getElementById('captionPosition').value,boundaries:selectedBoundaries})});const data=await res.json();if(!res.ok)throw new Error(data.detail||'Render failed');
    box.innerHTML=`<strong>Ready.</strong> ${data.files.length} clip${data.files.length===1?'':'s'} rendered.`;
    [...new Set(data.files.map(file=>file.framing?.message).filter(Boolean))].forEach(message=>{const note=document.createElement('div');note.className='export-note';note.textContent=message;box.appendChild(note);});
    data.files.forEach(file=>{const a=document.createElement('a');a.className='download-link';a.href=file.url;a.download=file.name;a.title=file.framing?.message||'';a.innerHTML=`<span>${escapeHtml(file.name)}</span><strong>Save ↓</strong>`;list.appendChild(a);});
  }catch(err){box.classList.add('error');box.textContent=err.message;}
  finally{exportBusy=false;renderClipsButton.disabled=false;renderClipsButton.setAttribute('aria-busy','false');}
});

window.addEventListener('scroll',()=>{
  const y=Math.min(window.scrollY,900);
  document.querySelector('.hill-back').style.transform=`translateY(${y*.025}px)`;
  document.querySelector('.hill-front').style.transform=`translateY(${y*.05}px)`;
});
function scoreLabel(key){return ({hook:'Hook',emotion:'Emotion',curiosity:'Curiosity',payoff:'Payoff',completeness:'Complete',density:'Density',novelty:'Novelty',audio:'Audio',visual:'Visual',replay:'Replay',semantic_coherence:'Topic coherence'}[key]||key);}
function formatTime(sec){sec=Math.max(0,Math.floor(sec));const m=Math.floor(sec/60);const s=sec%60;return `${m}:${String(s).padStart(2,'0')}`;}
function escapeHtml(value){return String(value).replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));}
showStep(0,{scroll:false});
