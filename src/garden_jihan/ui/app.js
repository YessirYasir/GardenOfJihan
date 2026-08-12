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
let projectSaveTimer = null;
let pendingProjectSave = null;
let projectSaveQueue = Promise.resolve(true);
let previewEnd = null;
let exportedFiles = [];

function api(path, options={}) {
  const headers = new Headers(options.headers || {});
  if (options.method && options.method !== 'GET') headers.set('X-GOJ-Token', token);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type','application/json');
  return fetch(path, {...options, headers});
}
async function initializeWelcome(){
  const welcome=document.getElementById('welcomeGarden');
  try{
    const res=await api('/api/health');const data=await res.json();if(!res.ok||data.product!=='garden-of-jihan')throw new Error('Local health check failed');
    if(data.first_run){welcome.classList.remove('hidden');document.getElementById('beginGarden').focus();}
  }catch(err){console.warn('Garden of Jihan local readiness check failed',err);}
}
document.getElementById('beginGarden').addEventListener('click',async event=>{
  const button=event.currentTarget;button.disabled=true;button.textContent='Opening your garden…';
  try{await api('/api/onboarding/complete',{method:'POST'});}catch(err){console.warn('First-run preference was not saved',err);}
  document.getElementById('welcomeGarden').classList.add('hidden');
  button.disabled=false;button.innerHTML='Begin with a video <span>→</span>';
  document.getElementById('sourceUrl').focus();
});
function projectPayload(){
  const captionMode=document.getElementById('captions').value;
  return {name:document.getElementById('projectName').value.trim()||'Untitled project',selected_ids:[...selected],boundaries,aspect:document.getElementById('aspect').value,framing:document.getElementById('framing').value,captions:captionMode!=='off',word_tracking:captionMode==='words',caption_style:document.getElementById('captionStyle').value,caption_position:document.getElementById('captionPosition').value};
}
function enqueueProjectSave(jobId,payload){
  const persist=async()=>{
    const status=document.getElementById('projectSaveStatus');if(currentJob===jobId)status.textContent='Saving locally…';
    try{const res=await api(`/api/jobs/${jobId}/project`,{method:'PUT',body:JSON.stringify(payload)});const data=await res.json();if(!res.ok)throw new Error(data.detail||'Project save failed');if(currentJob===jobId)status.textContent='Saved locally';loadProjects();return true;}
    catch(err){if(currentJob===jobId)status.textContent=`Not saved: ${err.message}`;return false;}
  };
  projectSaveQueue=projectSaveQueue.then(persist,persist);return projectSaveQueue;
}
function flushPendingProjectSave(){
  clearTimeout(projectSaveTimer);projectSaveTimer=null;
  if(!pendingProjectSave)return projectSaveQueue;
  const snapshot=pendingProjectSave;pendingProjectSave=null;
  return enqueueProjectSave(snapshot.jobId,snapshot.payload);
}
function saveProject(){
  if(!currentJob)return Promise.resolve(true);
  pendingProjectSave={jobId:currentJob,payload:projectPayload()};
  return flushPendingProjectSave();
}
function queueProjectSave(){
  if(!currentJob)return;
  pendingProjectSave={jobId:currentJob,payload:projectPayload()};clearTimeout(projectSaveTimer);document.getElementById('projectSaveStatus').textContent='Changes waiting to save…';projectSaveTimer=setTimeout(flushPendingProjectSave,450);
}
function restoreProject(data,{defaultStrong=false}={}){
  if(pendingProjectSave&&pendingProjectSave.jobId!==data.id)flushPendingProjectSave();
  const project=data.project||{};currentJob=data.id;candidates=data.candidates||[];boundaries=project.boundaries||{};exportedFiles=[];syncPublishFiles();
  const validIds=new Set(candidates.map(candidate=>candidate.id));const restored=(project.selected_ids||[]).filter(id=>validIds.has(id));selected=new Set(restored.length||!defaultStrong?restored:candidates.filter(candidate=>candidate.score>=85).map(candidate=>candidate.id));
  document.getElementById('projectName').value=project.name||'Untitled project';
  document.getElementById('aspect').value=project.aspect||'9:16';document.getElementById('framing').value=project.framing||'auto';document.getElementById('captions').value=project.captions?(project.word_tracking?'words':'segments'):'off';document.getElementById('captionStyle').value=project.caption_style||'garden';document.getElementById('captionPosition').value=project.caption_position||'bottom';
  document.getElementById('projectSaveStatus').textContent=data.source_available?'Saved locally':'Source video is missing; export is unavailable';renderRankingStatus(data);renderCandidates();showStep(4);
}
function renderProjects(projects){
  const list=document.getElementById('projectList');const empty=document.getElementById('emptyProjects');list.innerHTML='';empty.classList.toggle('hidden',projects.length>0);
  projects.forEach(project=>{const item=document.createElement('div');item.className=`project-item${project.source_available?'':' unavailable'}`;const details=document.createElement('div');const name=document.createElement('b');name.textContent=project.name;const meta=document.createElement('small');const date=new Date(project.updated_at);meta.textContent=`${project.candidate_count} clips • ${project.selected_count} kept • ${Number.isNaN(date.getTime())?'saved locally':date.toLocaleDateString()}`;details.append(name,meta);const resume=document.createElement('button');resume.className='secondary';resume.textContent=project.source_available?'Resume':'Source missing';resume.disabled=!project.source_available;resume.addEventListener('click',()=>resumeProject(project.id));const remove=document.createElement('button');remove.className='secondary remove-project';remove.textContent='Remove';remove.addEventListener('click',()=>removeProject(project));item.append(details,resume,remove);list.appendChild(item);});
}
async function loadProjects(){
  const empty=document.getElementById('emptyProjects');
  try{const res=await api('/api/projects');const data=await res.json();if(!res.ok)throw new Error(data.detail||'Could not load projects');renderProjects(data.projects||[]);}
  catch(err){empty.classList.remove('hidden');empty.textContent=`Local projects unavailable: ${err.message}`;}
}
async function resumeProject(jobId){
  try{const res=await api(`/api/jobs/${jobId}`);const data=await res.json();if(!res.ok)throw new Error(data.detail||'Could not resume project');restoreProject(data);}
  catch(err){window.alert(err.message);}
}
async function removeProject(project){
  if(!window.confirm(`Remove “${project.name}” and its local source, clips, and review data from this computer?`))return;
  if(pendingProjectSave?.jobId===project.id){clearTimeout(projectSaveTimer);projectSaveTimer=null;pendingProjectSave=null;}
  try{const res=await api(`/api/projects/${project.id}`,{method:'DELETE'});const data=await res.json();if(!res.ok)throw new Error(data.detail||'Could not remove project');if(currentJob===project.id){currentJob=null;candidates=[];selected=new Set();boundaries={};exportedFiles=[];syncPublishFiles();showStep(0);}loadProjects();}
  catch(err){window.alert(err.message);}
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
    source={url:data.url,uploadId:null,name:data.title||'Imported video'};
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
    source={url:null,uploadId:data.upload_id,name:fileInput.files[0].name.replace(/\.[^.]+$/,'')};
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
  const body={url:source.url,upload_id:source.uploadId,mode:selectedMode(),min_clip_seconds:Number(document.getElementById('minSeconds').value),max_clip_seconds:Number(document.getElementById('maxSeconds').value),max_clips:Number(document.getElementById('maxClips').value),project_name:source.name||null};
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
      setAnalysisBusy(false);restoreProject(data,{defaultStrong:true});queueProjectSave();return;
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
  const acousticStatus=match.acoustic_timing_status==='supported'?`<small class="acoustic-note supported">Word captions available • minimum acoustic confidence ${Math.round(Number(match.acoustic_timing_confidence)||0)}%. Timing is model-estimated.</small>`:`<small class="acoustic-note">${escapeHtml(match.acoustic_timing_message||'Acoustic word timing is unavailable; Qur’an word captions stay disabled.')}</small>`;
  return `<div class="quran-match high"><div class="quran-match-head"><b>Verified Qur’an ${escapeHtml(label)}</b><span>${escapeHtml(confidenceText)}</span></div>${sacredText}${wordTrack}${acousticStatus}${boundaryWarning}<small>${escapeHtml(match.source||'Reviewed local reference')} ${match.source_version?`v${escapeHtml(match.source_version)}`:''}</small><small class="qiraat-note">${escapeHtml(match.qiraat_message||'Qira’at is not assessed from text matching.')}</small></div>`;
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
    card.querySelector('.preview').addEventListener('click',()=>{const effective=boundaries[c.id]||{start:c.start,end:c.end};const video=document.getElementById('sourcePreview');previewEnd=effective.end;video.currentTime=effective.start;video.play();video.scrollIntoView({behavior:'smooth',block:'center'});});
    const editor=card.querySelector('.boundary-editor');
    card.querySelector('.adjust').addEventListener('click',()=>editor.classList.toggle('hidden'));
    card.querySelector('.apply-boundary').addEventListener('click',()=>{const start=Number(card.querySelector('.boundary-start').value);const end=Number(card.querySelector('.boundary-end').value);const duration=document.getElementById('sourcePreview').duration;if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start||end-start>180||(Number.isFinite(duration)&&end>duration+.05)){window.alert('Choose a valid range within the source, up to 3 minutes.');return;}boundaries[c.id]={start,end};card.querySelector('.timing-label').textContent=`${formatTime(start)} → ${formatTime(end)}`;editor.classList.add('hidden');queueProjectSave();});
    const keep=card.querySelector('.keep');keep.addEventListener('click',()=>{if(selected.has(c.id))selected.delete(c.id);else selected.add(c.id);keep.classList.toggle('on',selected.has(c.id));keep.textContent=selected.has(c.id)?'Kept':'Keep';syncExportSummary();queueProjectSave();});
    grid.appendChild(card);
  });syncExportSummary();
}
document.getElementById('selectStrong').addEventListener('click',()=>{selected=new Set(candidates.filter(c=>c.score>=85).map(c=>c.id));renderCandidates();queueProjectSave();});
function syncCaptionControls(){
  const captionMode=document.getElementById('captions').value;const enabled=captionMode!=='off';
  document.getElementById('captionStyle').disabled=!enabled;
  document.getElementById('captionPosition').disabled=!enabled;
  document.getElementById('exportCaptions').textContent=captionMode==='words'?'Words':enabled?'Timed':'Off';
}
function syncExportSummary(){document.getElementById('selectedCount').textContent=selected.size;document.getElementById('exportAspect').textContent=document.getElementById('aspect').value;syncCaptionControls();}
document.getElementById('captions').addEventListener('change',()=>{syncExportSummary();queueProjectSave();});
document.getElementById('aspect').addEventListener('change',()=>{syncExportSummary();queueProjectSave();});
['framing','captionStyle','captionPosition'].forEach(id=>document.getElementById(id).addEventListener('change',queueProjectSave));
document.getElementById('saveProject').addEventListener('click',saveProject);
document.getElementById('projectName').addEventListener('change',queueProjectSave);
document.getElementById('refreshProjects').addEventListener('click',loadProjects);
document.getElementById('sourcePreview').addEventListener('timeupdate',event=>{if(previewEnd!==null&&event.currentTarget.currentTime>=previewEnd){event.currentTarget.pause();previewEnd=null;}});
syncCaptionControls();

const renderClipsButton=document.getElementById('renderClips');
let exportBusy=false;
function setExportBusy(busy){exportBusy=busy;renderClipsButton.disabled=busy;renderClipsButton.setAttribute('aria-busy',String(busy));}
function showExportedFiles(files){
  const box=document.getElementById('exportMessage');const list=document.getElementById('downloadList');
  box.innerHTML=`<strong>Ready.</strong> ${files.length} clip${files.length===1?'':'s'} rendered.`;exportedFiles=files;syncPublishFiles();
  [...new Set(files.map(file=>file.framing?.message).filter(Boolean))].forEach(message=>{const note=document.createElement('div');note.className='export-note';note.textContent=message;box.appendChild(note);});
  files.forEach(file=>{const a=document.createElement('a');a.className='download-link';a.href=file.url;a.download=file.name;a.title=file.framing?.message||'';a.innerHTML=`<span>${escapeHtml(file.name)}</span><strong>Save ↓</strong>`;list.appendChild(a);});
}
async function pollExport(exportId,projectId){
  const box=document.getElementById('exportMessage');
  try{
    const res=await api(`/api/exports/${exportId}`);const data=await res.json();if(!res.ok)throw new Error(data.detail||'Export status unavailable');
    box.textContent=`${data.message} • ${data.progress}%`;
    if(data.status==='failed')throw new Error(data.error||'Local render failed');
    if(data.status==='complete'){
      setExportBusy(false);
      if(currentJob!==projectId){box.textContent='Export completed for another project. Resume that project to render or publish its clips.';return;}
      showExportedFiles(data.files||[]);return;
    }
    setTimeout(()=>pollExport(exportId,projectId),900);
  }catch(err){box.classList.add('error');box.textContent=err.message;setExportBusy(false);}
}
renderClipsButton.addEventListener('click',async()=>{
  if(exportBusy)return;
  const box=document.getElementById('exportMessage');const list=document.getElementById('downloadList');list.innerHTML='';exportedFiles=[];syncPublishFiles();box.classList.remove('hidden','error');
  if(!currentJob||selected.size===0){box.textContent='Choose at least one clip first.';return;}
  const captionMode=document.getElementById('captions').value;const captions=captionMode!=='off';const wordTracking=captionMode==='words';
  if(captions&&!wordTracking&&candidates.some(candidate=>selected.has(candidate.id)&&candidate.mode==='quran')){box.classList.add('error');box.textContent='Qur’an segment captions are disabled. Choose acoustic word highlighting; it will render only when the verified reference alignment and local timestamps pass every confidence check.';return;}
  setExportBusy(true);
  box.textContent='Rendering locally with FFmpeg…';
  try{
    const exportProject=currentJob;
    const selectedBoundaries=Object.fromEntries([...selected].filter(id=>boundaries[id]).map(id=>[id,boundaries[id]]));
    const res=await api(`/api/jobs/${currentJob}/export`,{method:'POST',body:JSON.stringify({candidate_ids:[...selected],aspect:document.getElementById('aspect').value,framing:document.getElementById('framing').value,captions,word_tracking:wordTracking,caption_style:document.getElementById('captionStyle').value,caption_position:document.getElementById('captionPosition').value,boundaries:selectedBoundaries})});const data=await res.json();if(!res.ok)throw new Error(data.detail||'Render failed');
    pollExport(data.id,exportProject);
  }catch(err){box.classList.add('error');box.textContent=err.message;setExportBusy(false);}
});

let youtubeConnected=false;
function syncPublishFiles(){
  const select=document.getElementById('publishFile');const previous=select.value;select.innerHTML='';
  if(!exportedFiles.length){const option=document.createElement('option');option.value='';option.textContent='Export a clip first';select.appendChild(option);}else{exportedFiles.forEach(file=>{const option=document.createElement('option');option.value=file.name;option.textContent=file.name;select.appendChild(option);});if(exportedFiles.some(file=>file.name===previous))select.value=previous;if(!document.getElementById('youtubeTitle').value)document.getElementById('youtubeTitle').value=select.value.replace(/^clip_\d+_/,'').replace(/\.mp4$/,'').replace(/[_-]+/g,' ');}
  document.getElementById('publishYoutube').disabled=!youtubeConnected||!exportedFiles.length;
}
async function refreshPublishingStatus(){
  try{const res=await api('/api/publish/status');const data=await res.json();if(!res.ok)throw new Error(data.detail||'Publishing status unavailable');const youtube=data.youtube||{};youtubeConnected=Boolean(youtube.connected);const status=document.getElementById('youtubeStatus');status.textContent=youtubeConnected?'YouTube connected':youtube.configured?'YouTube ready to connect':'YouTube OAuth not configured';status.classList.toggle('connected',youtubeConnected);document.getElementById('connectYoutube').disabled=!youtube.configured||youtubeConnected;document.getElementById('disconnectYoutube').disabled=!youtubeConnected;document.getElementById('tiktokStatus').textContent=data.tiktok?.message||'Official TikTok posting is unavailable.';syncPublishFiles();return youtubeConnected;}
  catch(err){const box=document.getElementById('publishMessage');box.classList.remove('hidden');box.classList.add('error');box.textContent=err.message;return false;}
}
document.getElementById('installYoutubeClient').addEventListener('click',async()=>{const input=document.getElementById('youtubeClientFile');const box=document.getElementById('publishMessage');box.classList.remove('hidden','error');if(!input.files.length){box.classList.add('error');box.textContent='Choose a Google OAuth Desktop app JSON file.';return;}const form=new FormData();form.append('file',input.files[0]);try{const res=await api('/api/publish/youtube/client',{method:'POST',body:form});const data=await res.json();if(!res.ok)throw new Error(data.detail||'OAuth client install failed');box.textContent='YouTube OAuth client stored with Windows user encryption. Connect the account next.';refreshPublishingStatus();}catch(err){box.classList.add('error');box.textContent=err.message;}});
document.getElementById('connectYoutube').addEventListener('click',async()=>{const box=document.getElementById('publishMessage');box.classList.remove('hidden','error');try{const res=await api('/api/publish/youtube/connect',{method:'POST'});const data=await res.json();if(!res.ok)throw new Error(data.detail||'Could not start YouTube authorization');const popup=window.open('','goj-youtube-oauth','width=720,height=760');if(!popup)throw new Error('Allow the YouTube authorization window, then try again.');popup.opener=null;popup.location.href=data.authorization_url;box.textContent='Complete Google authorization in the new window. Only upload permission is requested.';let checks=0;const timer=setInterval(async()=>{checks+=1;if(await refreshPublishingStatus()||checks>=150)clearInterval(timer);},2000);}catch(err){box.classList.add('error');box.textContent=err.message;}});
document.getElementById('disconnectYoutube').addEventListener('click',async()=>{if(!window.confirm('Forget the YouTube connection on this computer? You can also revoke Garden of Jihan in your Google Account permissions.'))return;const box=document.getElementById('publishMessage');try{const res=await api('/api/publish/youtube/connection',{method:'DELETE'});const data=await res.json();if(!res.ok)throw new Error(data.detail||'Could not forget connection');box.classList.remove('hidden','error');box.textContent='Local YouTube tokens removed. Revoke the app in Google Account permissions if you also want server-side revocation.';refreshPublishingStatus();}catch(err){box.classList.remove('hidden');box.classList.add('error');box.textContent=err.message;}});
async function pollYoutubeUpload(uploadId){
  const box=document.getElementById('publishMessage');try{const res=await api(`/api/publish/youtube/uploads/${uploadId}`);const data=await res.json();if(!res.ok)throw new Error(data.detail||'Upload status unavailable');box.textContent=`${data.message} • ${data.progress}%`;if(data.status==='failed')throw new Error(data.error||'YouTube upload failed');if(data.status==='complete'){box.innerHTML='<strong>YouTube accepted the upload.</strong>';const link=document.createElement('a');link.className='publish-result';link.href=data.url;link.target='_blank';link.rel='noreferrer';link.textContent='Open uploaded video on YouTube ↗';box.appendChild(link);document.getElementById('publishYoutube').disabled=false;document.getElementById('publishYoutube').setAttribute('aria-busy','false');return;}setTimeout(()=>pollYoutubeUpload(uploadId),1000);}catch(err){box.classList.add('error');box.textContent=err.message;document.getElementById('publishYoutube').disabled=false;document.getElementById('publishYoutube').setAttribute('aria-busy','false');}}
document.getElementById('publishYoutube').addEventListener('click',async()=>{const box=document.getElementById('publishMessage');const button=document.getElementById('publishYoutube');box.classList.remove('hidden','error');const filename=document.getElementById('publishFile').value;const title=document.getElementById('youtubeTitle').value.trim();const kids=document.getElementById('youtubeKids').value;const synthetic=document.getElementById('youtubeSynthetic').value;if(!filename||!title||!kids||!synthetic){box.classList.add('error');box.textContent='Choose an exported clip, title, audience, and synthetic-media disclosure.';return;}button.disabled=true;button.setAttribute('aria-busy','true');box.textContent='Starting official YouTube upload…';const payload={filename,title,description:document.getElementById('youtubeDescription').value,privacy:document.getElementById('youtubePrivacy').value,made_for_kids:kids==='yes',contains_synthetic_media:synthetic==='yes'};try{const res=await api(`/api/jobs/${currentJob}/publish/youtube`,{method:'POST',body:JSON.stringify(payload)});const data=await res.json();if(!res.ok)throw new Error(data.detail||'Could not start YouTube upload');pollYoutubeUpload(data.id);}catch(err){box.classList.add('error');box.textContent=err.message;button.disabled=false;button.setAttribute('aria-busy','false');}});

document.getElementById('quitApp').addEventListener('click',async event=>{
  const button=event.currentTarget;
  if(!window.confirm('Quit Garden of Jihan? Saved projects stay on this computer.'))return;
  button.disabled=true;button.textContent='Saving…';
  try{
    if(!await flushPendingProjectSave())throw new Error('Project changes could not be saved. Fix the save error before quitting.');
    button.textContent='Closing…';
    const res=await api('/api/app/quit',{method:'POST'});const data=await res.json();if(!res.ok)throw new Error(data.detail||'Could not close the app safely');
    const screen=document.createElement('div');screen.className='shutdown-screen';screen.innerHTML='<div><h2>Garden of Jihan is closed</h2><p>Your local projects are saved. You can close this browser tab.</p></div>';document.body.appendChild(screen);
  }catch(err){button.disabled=false;button.textContent='Quit app';window.alert(err.message);}
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
initializeWelcome();
loadProjects();
refreshPublishingStatus();
