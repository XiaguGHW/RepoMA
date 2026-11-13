
const $=id=>document.getElementById(id);let busy=false,lastQuestion='',compareSlots=[{value:'claude-haiku-5-5',custom:''}],savedTargetSelection=new Set(),treeRestoreNote='',lastScanReport=null,scannedSelection='',uiLanguage='de',activeContextDrawer=null,lastStatusSnapshot=null,lastUsageSnapshot=null,lastCodebookProfile=null,lastCodebookTask=null,lastCodebookWorkspaceProfile=null,lastDocumentsSnapshot=null,lastCoverageReport=null,lastCacheAudit=null,lastSessionRows=[],lastTargetTreePayload=null,lastComparison=null;
// Single source of translated copy. Compatibility adapters are temporary;
// new UI components must use t('area.item', parameters).
const CATALOG=__WORKBENCH_I18N_JSON__;
const I18N=CATALOG.messages;
const LEGACY_KEYS=CATALOG.legacy_keys;
const UI=Object.fromEntries(['zh','en','de'].map(language=>[
  language,Object.fromEntries(Object.entries(LEGACY_KEYS).map(([source,key])=>[source,I18N[language][key]]))
]));
// Bind only server-rendered interface copy once.  Model responses, filenames,
// user input and text added later must never enter this collection.
let initialStaticI18nBound=false;
const initialStaticText=[],initialStaticAttributes=[];
const STATIC_ELEMENT_BINDINGS=[
  ['#cancelchat','stream.stop'],
  ['.chat-title','chat.title'],['.chat-subtitle','chat.subtitle'],
  ['.welcome .eyebrow','welcome.eyebrow'],['.welcome h1','welcome.title'],
  ['.welcome p','welcome.description'],['.welcome .row button','welcome.choose_folder','▣\u00a0 '],
  ['.welcome .row button.ghost','welcome.manage_rules','▤\u00a0 '],
  ['#contextpanel > .context-title','context.title']
];
function t(key,variables={}){
  const template=(I18N[uiLanguage]||I18N.zh)[key];
  if(template===undefined){console.warn('Unknown UI translation key:',key);return key}
  return template.replace(/\{(\w+)\}/g,(_,name)=>Object.prototype.hasOwnProperty.call(variables,name)?String(variables[name]):'{'+name+'}');
}
function uiCopy(value){
  if(value==null)return '';
  if(Array.isArray(value))return value.map(uiCopy).join('');
  if(typeof value==='string')return value;
  if(value.message_key){let params=Object.fromEntries(Object.entries(value.params||{}).map(([key,item])=>[key,item&&typeof item==='object'&&(item.message_key||typeof item.text==='string')?uiCopy(item):item]));return t(value.message_key,params)}
  return String(value.text??value.message??'');
}
function registerUI(node,kind,data){node.dataset.uiComponent=kind;node.uiData=data;return node}
function setUIMessage(host,data,kind=''){if(!host)return;let node=document.createElement('span');node.className=kind;node.textContent=uiCopy(data);registerUI(node,'message',data);host.replaceChildren(node);return node}
function showStartupNotice(data){
  let host=$('startupnotice');
  if(!host){host=document.createElement('div');host.id='startupnotice';host.className='message error';host.setAttribute('role','alert');host.style.cssText='margin:8px 14px;max-height:30vh;overflow:auto;flex-shrink:0';$('chat').before(host)}
  setUIMessage(host,data,'error');
}

function uiMessageNode(data,kind='assistant'){return registerUI(message(uiCopy(data),kind),'message',data)}
function scopeCopy(record){
  if(record.scope_message)return uiCopy(record.scope_message);
  if(record.reading_scope_message)return uiCopy(record.reading_scope_message);
  let scope=record.scope??record.reading_scope??'';
  return scope==='完整文本预读'?t('material.scope_full'):scope==='Datasheet 前 15 页预读（其余页尚未覆盖）'?t('material.scope_datasheet',{pages:15}):scope==='已读取'?t('coverage.default_scope'):scope;
}
function stateCopy(value){let keys={'ok':'state.ok','not_needed':'state.not_needed','partial':'state.partial','unknown':'state.unknown','not_requested':'state.not_requested','not_applicable':'state.not_applicable','not applicable':'state.not_applicable','已完成':'state.complete','部分完成':'state.partial','不需要（原生文字页）':'state.native_text','不适用（无页码文档）':'state.not_applicable','不需要 / 无 PDF 页':'state.no_pdf_pages'};return keys[value]?t(keys[value]):String(value??'—')}
function roleCopy(value){let keys={'技术图纸':'material.role_drawing','BOM / 装配表':'material.role_bom','数据表 / 目录':'material.role_datasheet','DFC 结构图':'material.role_dfc','CAD 截图':'material.role_cad','派生重复资料':'material.role_derived','Inventor 源图（暂不支持）':'material.role_unsupported','其他资料':'material.role_other'};return keys[value]?t(keys[value]):String(value||t('material.role_other'))}
function rerenderUIComponents(){
  for(let node of document.querySelectorAll('[data-ui-component]')){
    let data=node.uiData;
    if(node.dataset.uiComponent==='classification')node.innerHTML=classificationCard(data).innerHTML;
    else if(node.dataset.uiComponent==='coverage')node.innerHTML=coverageSummaryCard(data).innerHTML;
    else if(node.dataset.uiComponent==='message')node.textContent=uiCopy(data);
    else if(node.dataset.uiComponent==='ready')node.innerHTML=readyCardHtml(data);
    else if(node.dataset.uiComponent==='classify_request')node.innerHTML='<span>'+CLASSIFY_ICON+esc(t('classify.request_tag'))+'</span>';
    else if(node.dataset.uiComponent==='notices')node.textContent=data.map(uiCopy).join('\n');
    else if(node.dataset.uiComponent==='processing'){
      node.querySelector('[data-process-title]').textContent=t('model.processing');
      node.querySelector('[data-process-text]').textContent=uiCopy(data)||t('model.connecting');
    }
    else if(node.dataset.uiComponent==='preview')node.querySelector('.muted').textContent=t('stream.preview');
    else if(node.dataset.uiComponent==='reasoning')node.querySelector('summary').textContent=t('model.reasoning');
  }
}
function setI18nText(element,key,variables){if(element)element.textContent=t(key,variables)}
function tr(source){return LEGACY_KEYS[source]?t(LEGACY_KEYS[source]):source}
function P(mark){return uiLanguage==='zh'?mark:({'：':': ','；':'; ','、':', ','（':' (','）':')','｜':'|'})[mark]||mark}
function pricingSourceText(source){
  source=source||{};let text=source.kind==='page'?t('status.pricing_page',{file:esc(source.file||''),date:esc(source.date||''),count:source.models||0}):t('status.pricing_bundled');
  if(source.page_error)text+=' · <span class="error">'+t('status.pricing_page_error',{detail:esc(source.page_error)})+'</span>';
  return '<span class="muted">'+t('status.pricing')+P('：')+text+'</span>'}
function kindCopy(key){let keys={datasheet:'doc.kind.datasheet',offer:'doc.kind.offer',catalog:'doc.kind.catalog',manual:'doc.kind.manual',drawing:'doc.kind.drawing',bom:'doc.kind.bom',dfc:'doc.kind.dfc',cad:'doc.kind.cad',other:'doc.kind.other'};return keys[key]?t(keys[key]):''}
function pageList(pages){pages=[...pages].map(Number).sort((a,b)=>a-b);let out=[],i=0;while(i<pages.length){let j=i;while(j+1<pages.length&&pages[j+1]===pages[j]+1)j++;out.push(j>i?pages[i]+'–'+pages[j]:String(pages[i]));i=j+1}return out.join(P('、'))}
function reasonsCopy(reasons){let by={};Object.entries(reasons||{}).forEach(([page,list])=>(list||[]).forEach(reason=>{(by[reason]=by[reason]||[]).push(page)}));let names={start:'reason.start',bom:'reason.bom',rules:'reason.rules',graphic:'reason.graphic',dense:'reason.dense'};return Object.keys(names).filter(key=>by[key]).map(key=>t(names[key])+' '+pageList(by[key])).join(P('；'))}
function rt(key,values={}){return t(key,values)}
function bindInitialStaticI18n(){
  if(initialStaticI18nBound)return;
  initialStaticI18nBound=true;
  let walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  for(let node;node=walker.nextNode();){
    let source=node.nodeValue,key=LEGACY_KEYS[source.trim()];
    if(key)initialStaticText.push({node,key,lead:source.match(/^\s*/)[0],tail:source.match(/\s*$/)[0]});
  }
  for(let el of document.querySelectorAll('[placeholder],[title],[aria-label]'))for(let attr of ['placeholder','title','aria-label']){
    let source=el.getAttribute(attr),key=source&&LEGACY_KEYS[source];
    if(key)initialStaticAttributes.push({el,attr,key});
  }
}
function applyLanguage(){
  bindInitialStaticI18n();
  document.documentElement.lang=uiLanguage;document.documentElement.dataset.uiLanguage=uiLanguage;
  document.title='Bosch Assembly Assistant';
  for(let item of initialStaticText)item.node.nodeValue=item.lead+t(item.key)+item.tail;
  for(let item of initialStaticAttributes)item.el.setAttribute(item.attr,t(item.key));
  for(let [selector,key,prefix=''] of STATIC_ELEMENT_BINDINGS){let el=document.querySelector(selector);if(el)el.textContent=prefix+t(key)}
  $('leftsplitter')?.setAttribute('aria-label',t('layout.left_panel_width'));
  setI18nText(document.querySelector('.side .brand + .muted'),'app.local_only');
  setI18nText($('workspace')?.closest('.field')?.querySelector('label'),'workspace.path_label');
  setI18nText($('targetpath')?.closest('.field')?.previousElementSibling,'materials.description');
  setI18nText($('comparemodels')?.previousElementSibling,'compare.description');
}
let languageSave=Promise.resolve();
async function changeLanguage(){uiLanguage=$('language').value;applyLanguage();rerenderLanguageSensitiveUI();let language=uiLanguage;languageSave=languageSave.catch(()=>{}).then(()=>api('/api/language',{method:'POST',body:JSON.stringify({language})}));try{await languageSave}catch(e){console.warn('Language save failed',e)}}

// A rule preparation holds the model slot, so /api/setup would be refused as
// busy after a reload.  The running job belongs to the session the saved
// settings describe: attach to it read-only and keep following the job.
// The page no longer fills #workspace on restore (the server opens the
// automatic session folder), so an empty field matches the server's session.
let codebookAttachedTaskId=null;
async function attachToRunningRulePreparation(){
  try{
    let job=await api('/api/codebook/task');if(!job.running||!job.task)return false;
    let s=await api('/api/status'),chosen=$('workspace').value.trim();if(chosen&&s.workspace!==chosen)return false;
    renderStatus(s);codebookAttachedTaskId=job.task.task_id;await restoreSessionContext();
    await Promise.all([loadDocs(),loadSessions(),loadHistory()]);
    setUIMessage($('setupmsg'),{message_key:'workspace.opened'});refreshAppChrome();$('startupnotice')?.remove();return true;
  }catch{return false}
}
// The status drawer shows a copy of the sidebar coverage status; keep the
// copy live so progress and errors of "read all pages" are visible there.
// The rule review (shown in the chat area) sits beside the open rules drawer
// instead of underneath it, so it can be read without closing the drawer.
function syncRuleReviewLayout(){let head=document.querySelector('.context-drawer-head');if(head&&head.offsetHeight)document.documentElement.style.setProperty('--rule-review-head',head.offsetHeight+'px');let on=activeContextDrawer==='rules'&&!!$('contextbackdrop')?.classList.contains('open')&&!!$('chat')?.classList.contains('codebook-workspace');let was=document.body.classList.contains('rules-side-by-side');document.body.classList.toggle('rules-side-by-side',on);if(on&&!was)$('chat').scrollTop=0}
function watchRuleReviewLayout(){let observer=new MutationObserver(syncRuleReviewLayout);for(let id of ['chat','contextbackdrop']){let node=$(id);if(node)observer.observe(node,{attributes:true,attributeFilter:['class']})}}
function mirrorCoverageStatus(){let source=$('coveragestatus');if(!source)return;new MutationObserver(()=>{let copy=$('contextcoveragestatus');if(copy)copy.innerHTML=source.innerHTML}).observe(source,{childList:true,subtree:true,characterData:true})}
async function restoreLastWorkspace(){
  try{
    let s=await api('/api/settings');
    uiLanguage=['zh','en','de'].includes(s.language)?s.language:'de';$('language').value=uiLanguage;applyLanguage();
    // No workspace to choose: the server opens the automatic session folder.
    setSelectedModel(s.model||'claude-haiku-5-5');
    $('session').innerHTML='<option>'+ esc(s.session||'default') +'</option>';
    setUIMessage($('setupmsg'),{message_key:'workspace.restoring'});
    if(await attachToRunningRulePreparation())return;
    await setup();
  }catch{
    setUIMessage($('setupmsg'),{message_key:'workspace.restore_failed'});
  }
}
function setLeftPanelWidth(width){let available=Math.max(240,window.innerWidth-420-300-8);let bounded=Math.max(235,Math.min(Number(width)||270,Math.min(600,available)));document.documentElement.style.setProperty('--left-panel-width',bounded+'px');let drawerStyle=$('scan-drawer-position')||Object.assign(document.createElement('style'),{id:'scan-drawer-position'});drawerStyle.textContent='#scanbackdrop .scan-drawer{left:'+bounded+'px!important}';if(!drawerStyle.parentNode)document.head.append(drawerStyle);localStorage.setItem('bosch-workbench-left-panel-width',String(bounded))}
function initLeftSplitter(){let splitter=$('leftsplitter');if(!splitter)return;let saved=Number(localStorage.getItem('bosch-workbench-left-panel-width'));if(saved)setLeftPanelWidth(saved);let dragging=false;function stop(){if(!dragging)return;dragging=false;splitter.classList.remove('dragging');document.body.style.userSelect=''}splitter.addEventListener('pointerdown',event=>{dragging=true;splitter.classList.add('dragging');splitter.setPointerCapture(event.pointerId);document.body.style.userSelect='none';event.preventDefault()});splitter.addEventListener('pointermove',event=>{if(dragging)setLeftPanelWidth(event.clientX)});splitter.addEventListener('pointerup',stop);splitter.addEventListener('pointercancel',stop);window.addEventListener('resize',()=>setLeftPanelWidth(Number(getComputedStyle(document.documentElement).getPropertyValue('--left-panel-width').replace('px',''))||270))}
function initDarkScrollbars(){let style=document.createElement('style');style.textContent='*{scrollbar-color:#52637a #182235;scrollbar-width:thin}::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-track{background:#182235;border-radius:10px}::-webkit-scrollbar-thumb{background:#52637a;border:2px solid #182235;border-radius:10px}::-webkit-scrollbar-thumb:hover{background:#70839c}::-webkit-scrollbar-corner{background:#182235}select{width:100%;background:#0f172a!important;color:#e5e7eb!important;border:1px solid #3b4960!important;border-radius:6px;padding:8px;outline:none}select:hover{border-color:#526b88!important}select:focus{border-color:#3b82a8!important;box-shadow:0 0 0 2px rgba(59,130,168,.18)}select option{background:#172033;color:#e5e7eb}.language-picker select{width:auto;padding:3px 6px}.splitter{background:#263449!important}.splitter:hover,.splitter.dragging{background:#3b82a8!important}';document.head.append(style)}
window.addEventListener('DOMContentLoaded',()=>{bindInitialStaticI18n();mirrorCoverageStatus();watchRuleReviewLayout();applyLanguage();setUIMessage($('coveragestatus'),{message_key:'coverage.auto_hint'});initDarkScrollbars();initLeftSplitter();initSessionSidebar();initComposerControls();initLanguageLayout();initThemeLayer();renderCompareSlots();loadCodebookStatus();ensureMaterialFlow();initContextPanel();refreshAppChrome();restoreLastWorkspace()});
function rerenderLanguageSensitiveUI(){
  refreshAppChrome();
  $('contextbackdrop')?.querySelector('.context-drawer')?.setAttribute('aria-label',t('context.detail'));
  localizeComposerControls();
  localizeSessionChrome();
  for(let kind of ['materials','rules']){let node=$('contextshortcut-'+kind);if(node){node.title=t(kind==='materials'?'context.materials':'rules.title');node.setAttribute('aria-label',node.title)}}
  if(lastStatusSnapshot)renderStatus(lastStatusSnapshot);
  if(lastUsageSnapshot)renderUsageDetail(lastUsageSnapshot.usage,lastUsageSnapshot.model);
  if(lastCodebookProfile)renderCodebookStatus(lastCodebookProfile);
  renderAnswerMode();
  if(lastDocumentsSnapshot)renderDocuments(lastDocumentsSnapshot);
  if(lastTargetTreePayload){captureTargetTreeSelection();renderTargetTreeForLanguage(lastTargetTreePayload);}
  localizeMaterialFlowControls();
  if(lastCoverageReport)renderCoverageReport(lastCoverageReport);
  if(lastScanReport){setScanReportAvailable(lastScanReport);if($('scanbackdrop')?.classList.contains('open'))renderScanDrawer(lastScanReport)}
  if(lastCacheAudit)renderCacheAudit(lastCacheAudit);
  if(lastSourcesSnapshot)renderEvidenceSources(lastSourcesSnapshot.sources,lastSourcesSnapshot.dfc);
  if(lastSessionRows.length)renderSessionRowsForLanguage(lastSessionRows,false);
  renderCompareSlots();
  if(lastComparison)renderComparisonForLanguage(lastComparison);
  if(ruleEditState)renderRuleEditor();
  else if(lastCodebookWorkspaceProfile&&$('chat')?.classList.contains('codebook-workspace'))showCodebookWorkspace(lastCodebookWorkspaceProfile);
  rerenderUIComponents();
  for(let node of document.querySelectorAll('button[data-plan-id]'))node.textContent=t('changes.apply');
  for(let node of document.querySelectorAll('button[onclick="exportBgAnalysis()"]'))node.textContent=t('export.assembly');
  if(activeContextDrawer){
    let kind=activeContextDrawer,values=[...$('contextdrawerbody').querySelectorAll('input[id],textarea[id]')].filter(node=>!node.classList.contains('tree-file')&&!node.classList.contains('tree-folder')).map(node=>[node.id,node.value,node.selectionStart,node.selectionEnd]);
    let notices=[...$('contextdrawerbody').querySelectorAll('[data-ui-component="message"]')].filter(node=>node.parentElement?.id.startsWith('context')).map(node=>[node.parentElement.id,node.uiData,node.className]);
    openContextDrawer(kind);
    for(let [id,value,start,end] of values){let node=$(id);if(node){node.value=value;if(node.setSelectionRange&&start!=null)node.setSelectionRange(start,end)}}
    for(let [id,data,kind] of notices)setUIMessage($(id),data,kind);
  }
  refreshContextPanel();
}
function responseTextSummary(raw){let text=String(raw||'').replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim();return text.length>360?text.slice(0,357)+'…':text}
function apiErrorMessage(response,body){let detail=body?.message_key?uiCopy(body):'';if(!detail&&body&&typeof body==='object')detail=typeof body.detail==='string'?body.detail:(typeof body.message==='string'?body.message:'');let summary=detail||responseTextSummary(typeof body==='string'?body:'');return `HTTP ${response.status}${response.statusText?` ${response.statusText}`:''}${summary?`${P('：')}${summary}`:`${P('：')}${t('api.failed')}`}`}
async function readApiResponse(response){let raw=await response.text(),body=null;if(raw.trim()){try{body=JSON.parse(raw)}catch{body=raw}}if(!response.ok){let error=Error(apiErrorMessage(response,body));if(body?.message_key)error.uiMessage=body;throw error}if(body===null||typeof body==='string')throw Error(`HTTP ${response.status}${P('：')}${t('api.invalid_json')}${responseTextSummary(raw)?' '+responseTextSummary(raw):''}`);return body}
// The session/context this page displays. Every request carries it; the server
// rejects context actions from a page that another tab has made stale.
let workbenchContext='',pageContextStale=false;
const PAGE_BINDING_URLS=['/api/setup','/api/session/open','/api/session/new'];
function contextHeaders(){return workbenchContext?{'X-Workbench-Context':workbenchContext}:{}}
function learnPageContext(url,method,response){
  if(response.headers.get('X-Workbench-Stale')){pageContextStale=true;return}
  let token=response.headers.get('X-Workbench-Context');if(!token||!response.ok)return;
  let path=String(url).split('?')[0];
  if(PAGE_BINDING_URLS.includes(path)){pageContextStale=false;workbenchContext=token;return}
  // A GET must not silently re-bind a stale page whose view was not refreshed.
  if(pageContextStale||(method==='GET'&&workbenchContext))return;
  workbenchContext=token;
}
async function api(url,opt={}){let response,method=String(opt.method||'GET').toUpperCase();try{response=await fetch(url,{...opt,headers:{'Content-Type':'application/json','X-Workbench-Language':uiLanguage,...contextHeaders(),...(opt.headers||{})}})}catch(error){throw Error(t('model.connection_failed')+(error?.message?` ${error.message}`:''))}learnPageContext(url,method,response);return readApiResponse(response)}
async function pick(kind,target){try{$(target).value=(await api('/api/pick/'+kind)).path||''}catch(e){if(target==='codebook')setUIMessage($('codebookstatus'),e.uiMessage||{text:e.message},'error');else appNotice(e.message)}}
async function pickWorkspace(){try{let path=(await api('/api/pick/folder')).path||'';if(!path)return;$('workspace').value=path;await setup()}catch(e){setUIMessage($('setupmsg'),e.uiMessage||{text:e.message},'error')}}
function refreshAppChrome(){let path=$('workspace')?.value.trim();let short=path?path.replace(/\\/g,'/').split('/').filter(Boolean).slice(-2).join(' / '):tr('选择工作区文件夹');if($('workspaceshortcut'))$('workspaceshortcut').textContent=short;if($('topbarstatus'))$('topbarstatus').textContent=(path||lastStatusSnapshot)?t('app.workspace_open'):tr('本地运行')}
// Visual layer: one token set for borders, surfaces, type sizes and states.
// Appended after the older injected blocks so it is the single place where the
// final look of shared components is decided.
function initThemeLayer(){if($('theme-layer'))return;let style=document.createElement('style');style.id='theme-layer';style.textContent=`
:root{--th-line:rgba(148,170,200,.14);--th-line-2:rgba(148,170,200,.24);--th-s1:#0f1727;--th-s2:#141e31;--th-s3:#1a263b;
--th-text:#e8eef7;--th-text-2:#a9b6c8;--th-text-3:#71819a;--th-accent:#4d94f0;--th-accent-soft:rgba(77,148,240,.14);
--th-ok:#3ec28f;--th-ok-soft:rgba(62,194,143,.14);--th-warn:#e6ad55;--th-warn-soft:rgba(230,173,85,.14);--th-bad:#ef7b84;--th-mono:"Cascadia Mono",Consolas,"JetBrains Mono",monospace}
.splitter{background:var(--th-line)!important}.splitter:hover,.splitter:active{background:var(--th-accent)!important}
.header-action{width:auto!important;height:30px!important;padding:0 11px;gap:6px;display:inline-flex!important;align-items:center;border:1px solid var(--th-line-2)!important;background:var(--th-s1)!important;color:var(--th-text-2)!important;font-size:12px;white-space:nowrap}
.header-action:hover{color:var(--th-text)!important;border-color:var(--th-accent)!important;background:var(--th-accent-soft)!important}
@media(max-width:900px){.header-action span{display:none}.header-action{width:31px!important;padding:0;justify-content:center}}
.message.user{background:var(--th-accent-soft);border:1px solid rgba(77,148,240,.3);border-radius:14px 14px 4px 14px;width:fit-content;max-width:min(680px,78%);margin-left:auto;margin-right:max(0px,calc((100% - 920px)/2))}
.message.assistant{background:transparent;border:0;border-left:2px solid var(--th-line-2);border-radius:0;padding:4px 0 4px 16px}
.message.assistant.error,.message.error{border-left-color:var(--th-bad)}
.composer-tools select{border-radius:8px!important}
.composer:focus-within{border-color:rgba(77,148,240,.55);box-shadow:0 0 0 3px rgba(77,148,240,.14),0 14px 40px #00000038}
.model-test{display:inline-flex!important;align-items:center;gap:7px;height:30px;padding:0 11px!important;border:1px solid var(--th-line-2)!important;border-radius:8px;color:var(--th-text-2)!important}
.model-test::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--th-text-3);flex:none}
.model-test[data-state="ok"]::before{background:var(--th-ok);box-shadow:0 0 0 3px rgba(62,194,143,.18)}
.model-test[data-state="failed"]::before{background:var(--th-bad);box-shadow:0 0 0 3px rgba(239,123,132,.18)}
.model-test:hover{border-color:var(--th-accent)!important;color:var(--th-text)!important;background:transparent!important}
.scope-chip svg{flex:none;opacity:.85}.scope-menu button svg{margin-right:6px;vertical-align:-2px}
.scope-tag .chip{background:var(--th-s3);border:1px solid var(--th-line);color:var(--th-text-2);border-radius:6px;padding:1px 8px}
.context-card{background:var(--th-s1)!important;border-color:var(--th-line)!important}.context-card:hover{border-color:var(--th-line-2)!important;background:var(--th-s2)!important}
.classification-card.result-card,.classification-card.coverage-card{margin:0 auto 16px;padding:0;overflow:hidden;background:var(--th-s1);border:1px solid var(--th-line);border-radius:14px;line-height:1.6}
.card-head{display:flex;align-items:center;flex-wrap:wrap;gap:6px 12px;padding:11px 18px;border-bottom:1px solid var(--th-line)}
.card-head h3{margin:0!important;font-size:13px!important;font-weight:600;color:var(--th-text)!important}
.card-head-note{font-size:12px;color:var(--th-text-3)}
.card-body{padding:16px 18px 18px}
.card-badge{display:inline-flex;align-items:center;gap:5px;height:22px;padding:0 9px;border-radius:999px;font-size:11.5px;font-weight:500;white-space:nowrap}
.card-badge i{width:6px;height:6px;border-radius:50%;background:currentColor}
.card-badge.ok{background:var(--th-ok-soft);color:#7fe0b6}.card-badge.warn{background:var(--th-warn-soft);color:#f3c886}
.card-badge.info{background:var(--th-accent-soft);color:#9cc4ff}.card-badge.mute{background:rgba(148,170,200,.1);color:var(--th-text-2)}
.card-tag{display:inline-flex;align-items:center;min-height:22px;padding:0 8px;border-radius:6px;background:var(--th-s3);border:1px solid var(--th-line);font-size:12px;color:#cfe0f7}
.card-tag.mono{font-family:var(--th-mono);font-size:11.5px}
.cls-result{display:flex;align-items:center;flex-wrap:wrap;gap:8px 12px}
.cls-caption{font-size:12px;color:var(--th-text-3)}
.cls-label{font-size:21px;font-weight:650;color:#fff;letter-spacing:-.01em}
.cls-alt{margin-top:4px;font-size:12.5px;color:var(--th-text-3)}.cls-alt b{color:var(--th-text-2);font-weight:500}
.cls-kv{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:9px 16px;margin:14px 0 0;padding:13px 0;border-top:1px solid var(--th-line);border-bottom:1px solid var(--th-line);font-size:13px}
.cls-kv dt{color:var(--th-text-3)}.cls-kv dd{margin:0;display:flex;flex-wrap:wrap;gap:6px;align-items:center;min-width:0}
.cls-note{font-size:12px;color:var(--th-text-3)}
.cls-cols{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin-top:14px}
.cls-cols h4{margin:0 0 8px;font-size:12px;font-weight:500;color:var(--th-text-3)}
.cls-list{list-style:none;margin:0!important;padding:0!important;display:grid;gap:7px;font-size:13px}
.cls-list li{display:flex;gap:9px;align-items:flex-start;color:var(--th-text)}
.cls-list li::before{content:"";flex:none;width:6px;height:6px;border-radius:50%;margin-top:8px;background:var(--th-ok)}
.cls-list.uncertain li::before{background:var(--th-warn)}.cls-list li.empty{color:var(--th-text-3)}.cls-list li.empty::before{background:var(--th-text-3)}
.cov-row{display:grid;grid-template-columns:46px minmax(0,1fr) minmax(120px,190px) auto;align-items:center;gap:12px;padding:10px 18px;border-top:1px solid var(--th-line);font-size:13px}
.cov-row:first-child{border-top:0}
.cov-ext{height:22px;border-radius:5px;font:600 10px/22px var(--th-mono);text-align:center;background:rgba(148,170,200,.12);color:var(--th-text-2)}
.cov-ext.pdf{background:rgba(239,123,132,.14);color:#f6a2a9}.cov-ext.sheet{background:var(--th-ok-soft);color:#86e2bb}.cov-ext.image{background:var(--th-accent-soft);color:#9cc4ff}
.cov-name{min-width:0}.cov-name b{display:block;font-weight:500;color:var(--th-text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cov-name small{display:block;font-size:11.5px;color:var(--th-text-3)}
.cov-bar{height:4px;border-radius:2px;background:var(--th-s3);overflow:hidden}.cov-bar span{display:block;height:100%;background:var(--th-ok)}
.cov-bar.part span{background:var(--th-warn)}.cov-pages{font-size:11px;color:var(--th-text-3);margin-top:4px;font-variant-numeric:tabular-nums}
.rulejob-file{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px;margin:4px 0 10px}.rulejob-file b{font-weight:600;color:var(--th-text);overflow-wrap:anywhere}.rulejob-file .muted{font-size:12px}
.rulejob-steps{list-style:none;display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px;padding:0}
.rulejob-steps li{display:inline-flex;align-items:center;gap:7px;padding:4px 11px 4px 5px;border-radius:999px;border:1px solid var(--th-line);font-size:12px;color:var(--th-text-3)}
.rulejob-steps li.done{color:var(--th-text-2)}.rulejob-steps li.current{color:var(--th-text);border-color:rgba(77,148,240,.5);background:var(--th-accent-soft)}
.rulejob-step-mark{display:inline-grid;place-items:center;width:18px;height:18px;border-radius:50%;font-size:10.5px;font-weight:600;background:var(--th-s3);color:var(--th-text-3)}
.rulejob-steps li.done .rulejob-step-mark{background:var(--th-ok-soft);color:#7fe0b6}.rulejob-steps li.current .rulejob-step-mark{background:var(--th-accent);color:#fff}
.rulejob-stage{font-size:13px;color:var(--th-text)}
.rulejob-final{display:grid;gap:2px;padding:9px 12px;border-radius:8px;border:1px solid var(--th-line);font-size:13px;color:var(--th-text)}.rulejob-final span{font-size:12px;color:var(--th-text-2)}
.rulejob-final.draft{border-color:rgba(230,173,85,.45);background:var(--th-warn-soft)}.rulejob-final.locked{border-color:rgba(62,194,143,.45);background:var(--th-ok-soft)}.rulejob-actions{align-items:center}.rulejob-elapsed{font-size:12px;margin-left:4px;font-variant-numeric:tabular-nums}
@media(max-width:760px){.cls-cols{grid-template-columns:minmax(0,1fr)}.cov-row{grid-template-columns:40px minmax(0,1fr) auto}.cov-progress{grid-column:2/4}}
`;document.head.append(style)}
function initLanguageLayout(){if($('language-layout'))return;let style=document.createElement('style');style.id='language-layout';style.textContent=`.context-shortcut{display:none}@media(max-width:1180px){.context-shortcut{display:inline-grid}}html[lang="zh"] body,html[lang="zh"] button,html[lang="zh"] input,html[lang="zh"] select{font-family:"Microsoft YaHei UI","Microsoft YaHei","Noto Sans SC","Segoe UI",sans-serif;letter-spacing:0}html[lang="en"] body,html[lang="en"] button,html[lang="en"] input,html[lang="en"] select,html[lang="de"] body,html[lang="de"] button,html[lang="de"] input,html[lang="de"] select{font-family:Inter,"Segoe UI",Arial,sans-serif}html[lang="zh"] .chat-subtitle,html[lang="zh"] .muted{line-height:1.55}html[lang="de"] .context-card strong,html[lang="de"] .context-drawer-head h2{letter-spacing:0}html[lang="de"] .context-card strong{padding-right:42px}.row{flex-wrap:wrap;align-items:center}.row input{min-width:min(100%,185px)}.row button{white-space:normal;line-height:1.25;min-height:34px}.context-card{min-height:78px}.context-card strong{position:relative;line-height:1.3;padding-right:50px;overflow-wrap:anywhere}.context-card em{position:absolute;right:0;top:0;float:none;white-space:nowrap}.context-card span{white-space:normal;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}.context-drawer-head h2,.context-drawer-body label,.classification-card h3{overflow-wrap:anywhere}.context-drawer-body button,.workspace-actions button{max-width:100%;overflow-wrap:anywhere}.composer-tools{flex-wrap:wrap;row-gap:5px}.composer-tools .spacer{min-width:0}.composer-tools select{min-width:170px;max-width:min(330px,100%)}html[lang="de"] .composer-tools select{max-width:285px}@media(max-width:1180px){.shell{grid-template-columns:minmax(220px,var(--left-panel-width)) 8px minmax(360px,1fr) 260px}.right{padding:13px 10px}.context-drawer{right:260px;width:min(640px,calc(100vw - 300px))}.chat-header{padding:0 20px}.composer-wrap{padding-left:20px;padding-right:20px}}@media(max-width:760px){.topbar{gap:8px;padding:0 10px}.app-brand{font-size:13px}.topbar-workspace{max-width:145px}.shell{grid-template-columns:minmax(180px,42vw) 7px minmax(0,1fr)}.chat{padding:20px 14px}.chat-header{padding:0 14px}.composer-wrap{padding:0 14px 14px}.welcome h1{font-size:26px}.composer-tools .spacer{display:none}.composer-tools select{width:100%;max-width:none}.composer-tools #custommodelrow{width:100%;flex-wrap:wrap}.composer-tools #custommodelrow input{width:100%}.context-drawer{left:0;right:0;width:auto;max-width:100vw;border-radius:0;transform:none!important;transition:opacity .18s}.context-drawer-body{min-width:0;overflow-x:hidden}.context-drawer-body input{min-width:0;max-width:100%}#scanbackdrop.open .scan-drawer{left:0!important;right:0;width:auto;max-width:100vw;transform:none}.main{min-width:0}.composer{grid-template-columns:minmax(0,1fr) auto}.composer #cancelchat{grid-column:2}.composer input{min-width:0}.composer-tools{grid-column:1/-1}.context-card{min-height:0}}@media(max-width:900px){.shell{grid-template-columns:minmax(220px,var(--left-panel-width)) 8px minmax(0,1fr)}}@media(max-width:650px){.shell{grid-template-columns:minmax(0,1fr)}.chat-header{gap:6px}.chat-subtitle{display:none}.chat-title{font-size:13px}}`;document.head.append(style)}
function initComposerControls(){if($('composertools'))return;let composer=$('composer');if(!composer)return;let tools=document.createElement('div');tools.id='composertools';tools.className='composer-tools';let note=document.createElement('span');note.id='composermodelnote';note.className='muted';let spacer=document.createElement('span');spacer.className='spacer';let model=$('model'),custom=$('custommodelrow'),modelmsg=$('modelmsg'),test=document.querySelector('button[onclick="testModel()"]');if(model)tools.append(note,model);if(custom)tools.append(custom);if(test){test.id='modeltestbutton';test.className='model-test';tools.append(test)}if(modelmsg)tools.append(modelmsg);tools.append(spacer);composer.append(tools);let style=document.createElement('style');style.textContent='.scope-bar{width:100%;display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:9px 12px 2px}.scope-bar[hidden]{display:none}.scope-label{font-size:12px;color:#94a3b8;margin-right:2px}.scope-chip{border-radius:999px;padding:4px 11px;font-size:12.5px;background:transparent;border:1px solid #3b4960;color:#cbd5e1;display:inline-flex;gap:6px;align-items:center;max-width:340px;cursor:pointer}.scope-chip span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.scope-chip.on{background:#16324f;border-color:#38bdf8;color:#e0f2fe}.scope-chip b{font-weight:400;padding:0 2px;color:#7dd3fc}.scope-menu{width:100%;margin-top:4px;padding:4px;background:#111c30;border:1px solid #33435e;border-radius:10px;max-height:240px;overflow:auto}.scope-menu button{display:flex;width:100%;justify-content:space-between;gap:10px;background:transparent;color:#e5e7eb;text-align:left;padding:7px 9px;border-radius:7px}.scope-menu button:hover,.scope-menu button.on{background:#263244}.scope-tag{font-size:12px;color:#94a3b8;margin:10px 0 -4px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}.scope-tag .chip{border:1px solid #3b4960;border-radius:6px;padding:1px 7px}.scope-tag button{font-size:12px;padding:2px 8px}.classify-control{margin-left:auto;display:inline-flex;align-items:center;gap:8px;min-width:0}.classify-result{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:#cbd5e1;min-width:0}.classify-result b{color:#f8fafc;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:260px}.classify-result.stale{opacity:.55;text-decoration:line-through}.classify-arrow{color:#64748b}.classify-confidence{font-size:11.5px;padding:2px 8px;border-radius:999px;background:rgba(62,194,143,.14);color:#86efac;white-space:nowrap}.classify-button{display:inline-flex;align-items:center;gap:6px;height:30px;padding:0 12px;border-radius:8px;font-size:12.5px;font-weight:500;cursor:pointer;white-space:nowrap}.classify-button.start{background:#3b82f6;color:#fff;border:1px solid #3b82f6;box-shadow:0 2px 10px rgba(59,130,246,.35)}.classify-button.again{background:transparent;color:#cbd5e1;border:1px solid #3b4960}.classify-button.again:hover{border-color:#38bdf8;color:#fff}.classify-button.warn{background:#c98a2e;color:#fff;border:1px solid #c98a2e}.classify-button:disabled{opacity:.5;cursor:not-allowed;box-shadow:none}.classify-request{display:flex;justify-content:center;margin:0 auto 14px}.classify-request span{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:#bfdbfe;background:rgba(59,130,246,.14);border:1px solid rgba(59,130,246,.3);border-radius:999px;padding:4px 12px}.ready-card{max-width:920px;margin:8px auto 18px;display:flex;gap:16px;align-items:flex-start;padding:18px 20px;border:1px dashed #3b4960;border-radius:14px;background:#111c30}.ready-icon{color:#60a5fa;flex:none;margin-top:2px}.ready-body{min-width:0}.ready-body h3{margin:0 0 6px;font-size:15px;color:#f8fafc}.ready-body p{margin:0 0 4px;font-size:13px;color:#cbd5e1;line-height:1.6}.ready-classify{display:inline-flex;align-items:center;gap:4px;height:22px;padding:0 8px;margin:0 2px;border-radius:6px;border:0;background:#3b82f6;color:#fff;font-size:12px;vertical-align:1px;cursor:pointer}.ready-questions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.ready-question{font-size:12.5px;color:#cbd5e1;background:transparent;border:1px solid #3b4960;border-radius:12px;padding:5px 12px;cursor:pointer;text-align:left;line-height:1.45}.ready-question:hover{border-color:#38bdf8;color:#fff}';document.head.append(style);let bar=document.createElement('div');bar.id='scopebar';bar.className='scope-bar';bar.hidden=true;composer.prepend(bar);localizeComposerControls()}
function localizeComposerControls(){setI18nText($('composermodelnote'),'model.current');setI18nText($('modeltestbutton'),'model.test');renderAnswerMode()}
// There is no answer-mode switch: the server decides from the question whether
// a classification is needed. The only choice is the scope of the question:
// all confirmed materials (default) or one of them.
let scopeFocusId='',scopeDocs=[],scopeRevision=null,scopeOpen=false;
function renderAnswerMode(){renderScopeBar()}
async function ensureScopeDocs(){let rev=(lastStatusSnapshot?.context_revision||'')+'|'+(lastStatusSnapshot?.documents||0);if(rev===scopeRevision)return;scopeRevision=rev;scopeFocusId='';scopeOpen=false;scopeDocs=[];if(lastStatusSnapshot?.documents){try{scopeDocs=await api('/api/documents')}catch{scopeDocs=[]}}renderScopeBar()}
function scopeFocusDoc(){return (scopeDocs||[]).find(d=>d.id===scopeFocusId)||null}
function renderScopeBar(){
  let bar=$('scopebar');if(!bar)return;ensureScopeDocs();
  let snap=lastStatusSnapshot||{},docs=scopeDocs||[],issue=!!snap.context_issue,bg=!!snap.bg_context;
  let choose=docs.length>1&&!issue,focus=choose?scopeFocusDoc():null,q=$('question');
  if(!focus)scopeFocusId='';
  if(q)q.placeholder=focus?t('scope.placeholder_file',{name:focus.name}):choose?t('scope.placeholder_all',{count:docs.length}):t('chat.placeholder');
  // The bar carries the scope choice (several files) and the classify button
  // (any confirmed assembly, also a single file).
  let show=choose||bg;bar.hidden=!show;if(!show){bar.innerHTML='';return}
  let html='',menu='';
  if(choose){html+='<span class="scope-label">'+esc(t('scope.label'))+'</span><button type="button" class="scope-chip'+(focus?'':' on')+'" aria-pressed="'+!focus+'" onclick="setScopeFocus(\'\')">'+SCOPE_ICONS.all+'<span>'+esc(t('scope.all',{count:docs.length}))+'</span></button>';
  if(focus)html+='<button type="button" class="scope-chip on" aria-pressed="true" title="'+escAttr(focus.name)+'" onclick="toggleScopeMenu()">'+SCOPE_ICONS.file+'<span>'+esc(focus.name)+'</span><b role="button" aria-label="'+escAttr(t('scope.clear'))+'" onclick="event.stopPropagation();setScopeFocus(\'\')">×</b></button>';
  html+='<button type="button" class="scope-chip" aria-expanded="'+scopeOpen+'" onclick="toggleScopeMenu()">'+SCOPE_ICONS.one+'<span>'+esc(t(focus?'scope.change':'scope.one_file'))+'</span>'+SCOPE_ICONS.caret+'</button>';}
  if(scopeOpen)menu='<div class="scope-menu" role="listbox">'+docs.map(d=>'<button type="button" role="option" class="'+(d.id===scopeFocusId?'on':'')+'" data-id="'+escAttr(d.id)+'" onclick="setScopeFocus(this.dataset.id)"><span>'+SCOPE_ICONS.file+esc(d.name)+'</span><span class="muted">'+esc(roleCopy(d.material_role_label))+'</span></button>').join('')+'</div>';
  if(bg)html+=classifyControlHtml(snap,issue);
  bar.innerHTML=html+menu;
}
// Classification runs only from this button; every typed question is an
// explanation turn (the model still classifies when explicitly asked to).
const SCOPE_ICONS={all:'<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true"><path d="M2 4.5c0-.6.4-1 1-1h3l1.4 1.6H13c.6 0 1 .4 1 1v6c0 .6-.4 1-1 1H3c-.6 0-1-.4-1-1z"/></svg>',file:'<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round" aria-hidden="true"><path d="M4 1.8h5.2L12.5 5v9.2H4z"/><path d="M9 1.8V5h3.5"/></svg>',one:'<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="m10.4 10.4 3.4 3.4" stroke-linecap="round"/></svg>',caret:'<svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m4.5 6.5 3.5 3.5 3.5-3.5"/></svg>'};
const CLASSIFY_ICON='<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="8" cy="8" r="5.6"/><circle cx="8" cy="8" r="2.2"/></svg>';
function classifyControlHtml(snap,issue){
  let last=snap.last_classification,done=!!(last&&last.current&&!issue),result='';
  if(last&&last.current)result='<span class="classify-result'+(issue?' stale':'')+'"><span class="classify-arrow">→</span><b>'+esc(last.label)+'</b>'+(last.confidence&&!issue?'<span class="classify-confidence">'+esc(t('classification.confidence'))+' '+esc(last.confidence)+'</span>':'')+'</span>';
  let kind=issue?'warn':done?'again':'start',label=t(issue?'classify.reconfirm':done?'classify.again':'classify.start');
  let action=issue?"openContextDrawer('materials')":'startClassification()',help=t(issue?'context.reconfirm':'classify.help');
  return '<span class="classify-control">'+result+'<button type="button" id="classifybutton" class="classify-button '+kind+'" title="'+escAttr(help)+'" onclick="'+action+'"'+(busy&&!issue?' disabled':'')+'>'+CLASSIFY_ICON+'<span>'+esc(label)+'</span></button></span>';
}
function startClassification(){if(busy||!lastStatusSnapshot?.bg_context)return;scopeFocusId='';scopeOpen=false;chat({classify:true})}
function isClassifyRequest(text){return Object.values(I18N).some(messages=>messages['classify.request']===text)}
function classifyRequestTag(){let tag=document.createElement('div');tag.className='classify-request';tag.innerHTML='<span>'+CLASSIFY_ICON+esc(t('classify.request_tag'))+'</span>';registerUI(tag,'classify_request',null);$('chat').append(tag);$('chat').scrollTop=1e9;return tag}
// An empty conversation on a confirmed assembly shows a ready card: what is
// prepared, where the classify button is, and a few questions built locally
// from the material types (no model call). Otherwise the new-session hint.
const SUGGEST_ROLE_ORDER={technical_drawing:0,dfc_structure:0,bom:1,datasheet:2,cad_screenshot:3,other:4};
const SUGGEST_KEYS={technical_drawing:'drawing',dfc_structure:'dfc',bom:'bom',datasheet:'datasheet',cad_screenshot:'cad',other:'other'};
function suggestion(doc,number){let key='suggest.'+SUGGEST_KEYS[doc.material_role]+'_'+number;return t(key,{name:doc.name})}
function suggestedQuestions(docs){
  let usable=(docs||[]).filter(d=>SUGGEST_ROLE_ORDER[d.material_role]!==undefined)
    .sort((a,b)=>SUGGEST_ROLE_ORDER[a.material_role]-SUGGEST_ROLE_ORDER[b.material_role]||String(a.name).localeCompare(String(b.name)));
  if(usable.length===1){let d=usable[0];return [suggestion(d,1),suggestion(d,2)]}
  let seen=new Set(),out=[];
  for(let d of usable){if(seen.has(d.material_role)||out.length>=3)continue;seen.add(d.material_role);if(d.material_role!=='other')out.push(suggestion(d,1))}
  if(out.length<3)out.push(t('suggest.generic_function'));
  if(out.length<3&&usable.length)out.push(t('suggest.generic_summary'));
  return out.slice(0,3);
}
function readyCardHtml(data){
  let docs=data.docs||[],single=docs.length===1,name=single?docs[0].name:data.name;
  let chip='<button type="button" class="ready-classify" onclick="startClassification()">'+CLASSIFY_ICON+'<span>'+esc(t('classify.start'))+'</span></button>';
  let summary=single?t('ready.summary_one',{rules:data.rules}):t('ready.summary',{count:docs.length,rules:data.rules});
  let questions=suggestedQuestions(docs).map(q=>'<button type="button" class="ready-question" data-question="'+escAttr(q)+'" onclick="askSuggested(this.dataset.question)">'+esc(q)+'</button>').join('');
  return '<svg class="ready-icon" viewBox="0 0 16 16" width="30" height="30" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round" aria-hidden="true"><path d="M8 1.8 13.6 5v6L8 14.2 2.4 11V5z"/><path d="M2.4 5 8 8.2 13.6 5M8 8.2v6"/></svg>'+
    '<div class="ready-body"><h3>'+esc(t('ready.title',{name}))+'</h3><p>'+esc(summary)+'</p><p>'+esc(t('ready.hint')).replace('{button}',chip)+'</p>'+
    (questions?'<div class="ready-questions">'+questions+'</div>':'')+'</div>';
}
let emptyChatToken=0;
// Only an empty chat (nothing but this placeholder) may be replaced; never the
// rule workspace or a conversation that started while documents were loading.
function chatIsEmpty(chat){return !ruleEditState&&!chat.classList.contains('codebook-workspace')&&[...chat.children].every(node=>node.dataset.emptyChat)}
async function renderEmptyChat(){
  let chat=$('chat'),snap=lastStatusSnapshot,token=++emptyChatToken;if(!chat||!chatIsEmpty(chat))return;
  let bg=snap?.bg_context;
  if(!bg||snap.context_issue){chat.innerHTML='';uiMessageNode({message_key:'session.new_hint'}).dataset.emptyChat='1';return}
  let docs=[];try{docs=await api('/api/documents')}catch{}
  if(token!==emptyChatToken||!chatIsEmpty(chat))return;
  let name=String(bg.folder||'').split(/[\\/]/).filter(Boolean).pop()||'';
  let data={docs:docs.map(d=>({name:d.name,material_role:d.material_role})),rules:bg.codebook_name||'',name};
  let card=document.createElement('section');card.className='ready-card';card.dataset.emptyChat='1';card.innerHTML=readyCardHtml(data);
  registerUI(card,'ready',data);chat.innerHTML='';chat.append(card);
}
// Status arrives after the history on confirm/reload: refresh an empty chat only.
function refreshEmptyChat(){let chat=$('chat');if(chat&&chat.children.length===1&&chat.firstElementChild.dataset.emptyChat&&chatIsEmpty(chat))renderEmptyChat()}
function askSuggested(question){if(busy||!question)return;let input=$('question');if(!input||input.disabled)return;input.value=question;chat()}
function setScopeFocus(id){scopeFocusId=id||'';scopeOpen=false;renderScopeBar();$('question')?.focus()}
function toggleScopeMenu(){scopeOpen=!scopeOpen;renderScopeBar()}
function scopeTag(scope,classified){
  if(!scope||!lastStatusSnapshot?.bg_context)return null;let tag=document.createElement('div');tag.className='scope-tag';
  let range=scope.kind==='file'?t('scope.tag_file',{name:scope.name}):t('scope.tag_all',{count:scope.count});
  tag.innerHTML='<span class="chip">'+esc(range)+'</span><span class="chip">'+esc(t(classified?'scope.kind_classification':'scope.kind_answer'))+'</span>';
  if(scope.kind==='file'&&scopeDocs.length>1){let again=document.createElement('button');again.className='ghost';again.textContent=t('scope.reask_all');again.onclick=()=>{setScopeFocus('');$('question').value=lastQuestion;chat()};tag.append(again)}
  return tag;
}
async function contextPickWorkspace(){try{let path=(await api('/api/pick/folder')).path||'';if(!path)return;$('workspace').value=path;$('contextworkspacepath').value=path;if(await setup()){refreshAppChrome();closeContextDrawer()}}catch(e){setUIMessage($('contextworkspacemsg'),e.uiMessage||{text:e.message},'error')}}
async function contextOpenWorkspace(){let path=$('contextworkspacepath').value.trim();if(!path){setUIMessage($('contextworkspacemsg'),{message_key:'workspace.path_required'},'error');return}$('workspace').value=path;if(await setup()){refreshAppChrome();closeContextDrawer()}}
let contextMoved=[];
// The source elements are hidden, where innerText has no line breaks; join text
// nodes with spaces so "label<br>value" does not run together in the summary.
function contextText(id,fallback){let el=$(id);if(!el)return fallback;let parts=[],walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT),node;while(node=walker.nextNode())parts.push(node.nodeValue);let text=parts.join(' ').replace(/\s+/g,' ').replace(/\s+([:;,)：；，）])/g,'$1').replace(/([(：（])\s+/g,'$1').trim();return text||fallback}
function refreshContextPanel(){
  let rule=codebookCardSummary();
  let path=$('targetpath')?.value.trim();let selected=treeFileCount?.()||0;
  let material=path?(selected?t('material.selected_path',{count:selected,path}):path):t('materials.no_selection');
  let scan=contextText('coveragestatus',path?t('coverage.selection_changed'):t('materials.waiting'));
  let audit=contextText('usagedetail',t('audit.no_cache'));
  if($('context-rule-summary'))$('context-rule-summary').textContent=rule;
  if($('context-material-summary'))$('context-material-summary').textContent=material;
  if($('context-scan-summary'))$('context-scan-summary').textContent=scan;
  if($('context-audit-summary'))$('context-audit-summary').textContent=audit;
  renderContextGuard();
}
function renderContextGuard(){
  let issue=!!lastStatusSnapshot?.context_issue,host=$('contextguard');
  if(!host&&$('composer')){host=document.createElement('div');host.id='contextguard';host.className='muted';$('composer').before(host)}
  if(host)host.textContent=issue?t('context.reconfirm'):'';
  if($('question'))$('question').disabled=issue;
  renderScopeBar();
  document.querySelectorAll('button[onclick="chat()"],button[onclick="compareModels()"]').forEach(button=>button.disabled=issue);
  let draft=$('contextcodebookpath')?.value.trim(),prepared=lastCodebookProfile?.source_path||'';
  let rulemsg=$('contextrulemsg');if(rulemsg&&!rulemsg.querySelector('.error')&&!(rulemsg.querySelector('.ok')&&!draft))rulemsg.textContent=draft&&prepared&&draft!==prepared&&!codebookRunning()?t('rules.pending_path',{path:prepared}):'';
}
function initContextPanel(){
  if($('contextbackdrop'))return;
  for(let [kind,label] of [['materials','▣'],['rules','▤']]){
    let button=document.createElement('button');button.className='header-icon context-shortcut';button.id='contextshortcut-'+kind;
    button.textContent=label;button.title=t(kind==='materials'?'context.materials':'rules.title');button.setAttribute('aria-label',button.title);
    button.setAttribute('onclick',"openContextDrawer('"+kind+"')");document.querySelector('.chat-header').append(button);
  }
  let backdrop=document.createElement('div');backdrop.id='contextbackdrop';backdrop.className='context-backdrop';
  backdrop.innerHTML='<section class="context-drawer" role="dialog" aria-modal="true" aria-label="'+t('context.detail')+'"><div class="context-drawer-head"><h2 id="contextdrawertitle">'+t('context.title')+'</h2><button class="ghost" onclick="dismissContextDrawer()">×</button></div><div id="contextdrawerbody" class="context-drawer-body"></div></section>';
  backdrop.addEventListener('click',e=>{if(e.target===backdrop)dismissContextDrawer()});document.body.append(backdrop);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('appconfirm'))dismissContextDrawer()});
  for(let id of ['codebookstatus','targetpath','targettree','treestatus','coveragestatus','usagedetail','status']){let el=$(id);if(el)new MutationObserver(refreshContextPanel).observe(el,{subtree:true,childList:true,characterData:true,attributes:true})}
  $('targetpath')?.addEventListener('input',refreshContextPanel);refreshContextPanel();
}
function moveContextElements(ids,host){
  ids.forEach(id=>{let el=$(id);if(!el)return;let marker=document.createComment('context:'+id);el.parentNode.insertBefore(marker,el);contextMoved.push({el,marker});host.append(el)});
}
// The rule review and the rule editor belong to the rules drawer: closing the
// drawer closes them too (unsaved edits are confirmed first).
async function dismissContextDrawer(){let review=activeContextDrawer==='rules'&&$('chat').classList.contains('codebook-workspace');if(review&&!await allowRuleDraftTransition())return;closeContextDrawer();if(review)await leaveCodebookWorkspace()}
function closeContextDrawer(){
  for(let item of contextMoved){if(item.marker.parentNode)item.marker.parentNode.replaceChild(item.el,item.marker)}
  contextMoved=[];activeContextDrawer=null;$('contextbackdrop')?.classList.remove('open');syncRuleReviewLayout();refreshContextPanel();
}
async function contextPickTarget(kind){try{let path=(await api('/api/pick/'+kind)).path||'';if(!path)return;materialDraftDirty=true;$('targetpath').value=path;$('contexttargetpath').value=path;if(kind==='folder')await loadTargetTree();else showSingleFileTarget();refreshContextPanel()}catch(e){setUIMessage($('contexttargetmsg'),e.uiMessage||{text:e.message},'error')}}
function singleFileTarget(){let path=$('targetpath').value.trim();return !!path&&!lastTargetTreePayload&&/\.[A-Za-z0-9]{2,5}$/.test(path)}
function showSingleFileTarget(){clearTargetTree();let path=$('targetpath').value.trim();if(!path)return;let host=$('targettree');host.classList.remove('muted');host.textContent=t('materials.single_file',{name:path.split(/[\\/]/).pop()});updateMaterialFlowButtons()}
async function contextAutoLoadTarget(){contextSyncTarget();if(!$('targetpath').value.trim())return;if(singleFileTarget()){showSingleFileTarget();return}if(!lastTargetTreePayload)await loadTargetTree()}
function contextSyncTarget(){let value=$('contexttargetpath').value.trim();if(value!==$('targetpath').value.trim()){materialDraftDirty=true;$('targetpath').value=value;clearTargetTree()}refreshContextPanel()}
function contextSyncRule(){let value=$('contextcodebookpath').value.trim();$('codebook').value=value;refreshContextPanel()}
async function contextPickRule(){try{let path=(await api('/api/pick/file')).path||'';if(!path)return;$('codebook').value=path;$('contextcodebookpath').value=path;refreshContextPanel()}catch(e){setUIMessage($('contextrulemsg'),e.uiMessage||{text:e.message},'error')}}
function renderDiagnostics(report){
  let host=$('diagnosticsresult');if(!host)return;
  let ready=report.overall==='ready';
  let rows=(report.checks||[]).map(check=>{
    let marker=check.ok===true?'<span class="ok">✓</span>':check.required===false?'<span class="muted">△</span>':'<span class="error">×</span>';
    let key='diagnostic.'+String(check.id||''),label=(I18N[uiLanguage]||I18N.zh)[key]?t(key):String(check.label||'—');
    // The endpoint deliberately remains language-neutral.  Convert its stable
    // status fields at presentation time; raw details stay visible only in ZH
    // or as a technical fallback for unknown future checks.
    let detail=check.detail_message?uiCopy(check.detail_message):uiLanguage==='zh'?String(check.detail||'—'):check.ok===true?t('diagnostic.available'):check.ok===null?t('diagnostic.not_tested'):t('diagnostic.not_available');if(check.path)detail+=' · '+check.path;
    return '<div class="card"><b>'+marker+' '+esc(label)+'</b><br><span class="muted">'+esc(detail)+'</span></div>';
  }).join('');
  host.innerHTML='<div class="'+(ready?'ok':'error')+'"><b>'+t(ready?'audit.diagnostics_ready':'audit.diagnostics_attention')+'</b></div>'+rows;
}
async function runDiagnostics(){
  let host=$('diagnosticsresult');if(!host)return;
  host.textContent=t('audit.diagnostics_loading');
  try{renderDiagnostics(await api('/api/diagnostics'))}
  catch(e){setUIMessage(host,[{message_key:'audit.diagnostics_failed'},{text:e.message}],'error')}
}
function openContextDrawer(kind){
  closeScanReport();closeContextDrawer();activeContextDrawer=kind;let title=$('contextdrawertitle'),body=$('contextdrawerbody');
  if(kind==='workspace'){
    title.textContent=t('workspace.title');body.innerHTML='<div class="muted">'+t('workspace.description')+'</div><div class="field"><label>'+t('workspace.path_label')+'</label><div class="row"><input id="contextworkspacepath" placeholder="'+t('workspace.path_label')+'" value="'+escAttr($('workspace').value)+'"><button class="ghost" onclick="contextPickWorkspace()">'+t('workspace.choose')+'</button></div></div><div class="row"><button onclick="contextOpenWorkspace()">'+t('workspace.open')+'</button></div><div id="contextworkspacemsg" class="muted" style="margin-top:10px"></div>';
  }else if(kind==='rules'){
    title.textContent=t('rules.title');
    body.innerHTML='<div class="muted">'+t('rules.description')+'</div><section id="rulejobpanel" class="card rulejob" aria-live="polite"></section><div class="field"><label for="contextcodebookpath">'+t('rules.file_label')+'</label><div class="row"><input id="contextcodebookpath" placeholder="'+t('rules.choose')+'" value="'+escAttr($('codebook').value)+'" oninput="contextSyncRule()"><button class="ghost" id="rulefilepick" onclick="contextPickRule()">'+t('workspace.choose')+'</button></div></div><div class="field"><label for="rulemodel">'+t('rulejob.model_label')+'</label><select id="rulemodelselect" onchange="ruleModelPicked(this.value)">'+ruleModelOptions()+'</select><div class="row" id="rulemodelcustomrow" style="display:none;margin-top:7px"><input id="rulemodel" autocomplete="off" spellcheck="false" placeholder="'+escAttr(t('model.id_placeholder'))+'" value="'+escAttr(ruleModelValue())+'" oninput="ruleModelDraft=this.value;ruleModelPending=true;renderRuleModelHint()" onkeydown="if(event.key===\'Enter\'){event.preventDefault();confirmRuleModel()}"><button class="ghost" id="rulemodelconfirm" onclick="confirmRuleModel()">'+t('actions.confirm')+'</button></div><div class="muted">'+t('rulejob.model_hint')+'</div><div id="rulemodelhint" class="muted"></div></div><div class="row"><button id="ruleprepare" onclick="contextSyncRule();prepareCodebook()">'+t('rules.prepare')+'</button></div><div id="contextrulemsg" class="muted" style="margin-top:10px"></div>';
    syncRuleModelSelect();renderRuleJobPanel();renderRuleModelHint();
  }else if(kind==='materials'){
    title.textContent=t('materials.title');body.innerHTML='<div class="muted">'+t('materials.description')+'</div><div class="field"><label>'+t('materials.target_label')+'</label><div class="row"><input id="contexttargetpath" placeholder="'+t('materials.target_placeholder')+'" value="'+escAttr($('targetpath').value)+'" oninput="contextSyncTarget()" onchange="contextAutoLoadTarget()" onkeydown="if(event.key===\'Enter\')contextAutoLoadTarget()"><button class="ghost" onclick="contextPickTarget(\'file\')">'+t('materials.file')+'</button><button class="ghost" onclick="contextPickTarget(\'folder\')">'+t('materials.folder')+'</button></div></div><div id="contexttargetmsg" class="muted" style="margin:8px 0"></div><div id="contextmaterialmount"></div>';
    moveContextElements(['treestatus','targettree','materialactions','bgstatus','coveragestatus'], $('contextmaterialmount'));
    if($('targetpath').value.trim()&&!lastTargetTreePayload&&!singleFileTarget())contextAutoLoadTarget();
  }else if(kind==='scan'){
    title.textContent=t('scan.title');body.innerHTML='<div class="muted">'+t('scan.description')+'</div><div class="card" id="contextcoveragestatus">'+$('coveragestatus').innerHTML+'</div><div class="row"><button class="ghost" onclick="openScanReport()">'+t('scan.report')+'</button><button class="ghost" id="contextreadall" onclick="prepareCoverage(true)">'+t('scan.extend')+'</button></div>';
  }else if(kind==='compare'){
    title.textContent=t('compare.title');body.innerHTML='<div class="muted">'+t('compare.description')+'</div><div id="contextcomparemount"></div>';
    let host=$('contextcomparemount');moveContextElements(['comparemodels'],host);let row=$('addcompare')?.parentNode;if(row){let marker=document.createComment('context:compare-actions');row.parentNode.insertBefore(marker,row);contextMoved.push({el:row,marker});host.append(row)}moveContextElements(['comparestatus'],host);
  }else{
    title.textContent=t('audit.title');body.innerHTML='<div class="muted">'+t('audit.description')+'</div><div class="card">'+$('usagedetail').innerHTML+'</div><div class="card">'+$('status').innerHTML+'</div><div class="row"><button class="ghost" onclick="openAuditDetail()">'+t('audit.open')+'</button><button class="ghost" onclick="runDiagnostics()">'+t('audit.diagnostics')+'</button></div><div id="diagnosticsresult" class="list muted" style="margin-top:12px">'+t('audit.diagnostics_idle')+'</div>';
  }
  $('contextbackdrop').classList.add('open');applyLanguage();refreshContextPanel();syncRuleReviewLayout();if(kind==='audit')runDiagnostics();
}
function openCompareDrawer(){openContextDrawer('compare')}
function message(text,kind='assistant'){let e=document.createElement('div');e.className='message '+kind;e.textContent=text;$('chat').append(e);$('chat').scrollTop=1e9;return e}
function confidenceTone(value){let v=String(value||'').toLowerCase();return /high|hoch|高/.test(v)?'ok':/low|niedrig|gering|低/.test(v)?'warn':'info'}
function cardTags(items,className='card-tag'){return (items||[]).map(item=>'<span class="'+className+'">'+esc(item)+'</span>').join('')}
function classificationCard(c){let card=document.createElement('section');card.className='classification-card result-card';
  let none=esc(t('classification.not_returned'));
  let evidence=(c.evidence_labels||[]).map(item=>'<li>'+esc(item)+'</li>').join('')||'<li class="empty">'+t('classification.none')+'</li>';
  let uncertainty=(c.uncertainties||[]).filter(Boolean).map(item=>'<li>'+esc(item)+'</li>').join('')||'<li class="empty">'+t('classification.not_reported')+'</li>';
  let rules=cardTags(c.codebook_rule_ids,'card-tag mono')||none;
  let rulePages=(c.codebook_rule_pages||[]).length?t('classification.rule_pages')+' '+c.codebook_rule_pages.map(esc).join(P('、')):t('classification.rule_refs')+' '+((c.codebook_rule_refs||[]).map(esc).join(P('、'))||none);
  let bgPages=cardTags(c.bg_evidence_pages)||none;
  let confidence=c.confidence?'<span class="card-badge '+confidenceTone(c.confidence)+'"><i></i>'+t('classification.confidence')+' '+esc(c.confidence)+'</span>':'';
  let alternative=c.alternative_label?'<div class="cls-alt">'+t('classification.alternative')+' <b>'+esc(c.alternative_label)+'</b></div>':'';
  card.innerHTML='<div class="card-head"><h3>'+t('classification.title')+'</h3></div><div class="card-body">'+
    '<div class="cls-result"><span class="cls-caption">'+t('classification.label')+'</span><span class="cls-label">'+esc(c.label||'—')+'</span>'+confidence+'</div>'+alternative+
    '<dl class="cls-kv"><dt>'+t('classification.rules')+'</dt><dd>'+rules+'<span class="cls-note">'+rulePages+'</span></dd>'+
    '<dt>'+t('classification.evidence_pages')+'</dt><dd>'+bgPages+'</dd></dl>'+
    '<div class="cls-cols"><div><h4>'+t('classification.evidence')+'</h4><ul class="cls-list">'+evidence+'</ul></div>'+
    '<div><h4>'+t('classification.uncertainty')+'</h4><ul class="cls-list uncertain">'+uncertainty+'</ul></div></div></div>';
  return registerUI(card,'classification',c)}
function fileExtension(name){let match=/\.([a-z0-9]{1,5})$/i.exec(String(name||''));return match?match[1].toUpperCase():''}
function coverageSummaryCard(summary){if(!summary?.files?.length)return null;let card=document.createElement('section');card.className='classification-card coverage-card';
  let rows=summary.files.map(f=>{let read=Array.isArray(f.pages_read)?f.pages_read.length:0,unread=Array.isArray(f.pages_unread)?f.pages_unread.length:0;
    let ext=fileExtension(f.name),kind=ext==='PDF'?'pdf':/^XLS|CSV/.test(ext)?'sheet':/^(PNG|JPE?G|WEBP)$/.test(ext)?'image':'other';
    let pages=f.pages_total?'<div class="cov-bar'+(unread?' part':'')+'"><span style="width:'+Math.max(0,Math.min(100,Math.round(read/f.pages_total*100)))+'%"></span></div><div class="cov-pages">'+t('coverage.read')+' '+read+'/'+f.pages_total+' '+t('coverage.pages')+(unread?P('；')+t('coverage.unread')+' '+unread+' '+t('coverage.pages'):'')+'</div>':'';
    let reused=f.cache_status==='reused',cache=reused?t('coverage.reused'):t('coverage.created');
    return '<div class="cov-row"><span class="cov-ext '+kind+'">'+esc(ext||'—')+'</span><div class="cov-name"><b>'+esc(f.name)+'</b><small>'+esc(scopeCopy(f)||t('coverage.default_scope'))+'</small></div><div class="cov-progress">'+pages+'</div><span class="card-badge '+(unread?'warn':reused?'mute':'info')+'"><i></i>'+cache+'</span></div>'}).join('');
  card.innerHTML='<div class="card-head"><h3>'+t('coverage.title')+'</h3><span class="card-head-note">'+t('coverage.summary',{files:summary.files.length,reused:summary.reused_files||0,created:summary.created_files||0,calls:summary.model_calls||0})+'</span></div><div class="cov-rows">'+rows+'</div>';
  return registerUI(card,'coverage',summary)}
function usageNumber(value){return value==null?t('usage.unknown'):esc(value)}
function unpricedText(d){if(!d)return '';let parts=[];if(d.cache_write)parts.push(t('usage.unpriced_cache_write',{count:d.cache_write}));if(d.cache_read)parts.push(t('usage.unpriced_cache_read',{count:d.cache_read}));if(d.model_requests)parts.push(t('usage.unpriced_model',{count:d.model_requests}));if(d.usage_missing_requests)parts.push(t('usage.unpriced_usage_missing',{count:d.usage_missing_requests}));return parts.length?' · '+t('usage.unpriced')+''+P('：')+''+parts.join(''+P('、')+''):''}
function usageCost(u){return u.cost_usd==null?t('usage.unknown')+(u.known_cost_usd!=null?' · '+t('usage.known_subtotal')+': $'+Number(u.known_cost_usd).toFixed(6):'')+unpricedText(u.unpriced_detail):'$'+Number(u.cost_usd).toFixed(6)}
function toggleCustomModel(){let custom=$('model').value==='__custom__';$('custommodelrow').style.display=custom?'flex':'none';if(custom)$('custommodel').focus()}
function setSelectedModel(model){let known=[...$('model').options].some(option=>option.value===model);$('model').value=known?model:'__custom__';$('custommodel').value=known?'':model;toggleCustomModel();loadModelStatus()}
function selectedModel(){let selected=$('model').value;return selected==='__custom__' ? $('custommodel').value.trim() : selected}
async function modelChanged(){toggleCustomModel();loadModelStatus();if($('model').value!=='__custom__'&&$('workspace').value.trim())await switchModel()}
async function confirmCustomModel(){if(!selectedModel()){ setUIMessage($('modelmsg'),{message_key:'model.id_required'},'error');return}if($('workspace').value.trim())await switchModel();else setUIMessage($('modelmsg'),{message_key:'model.custom_saved'})}
function codebookList(items){let values=Array.isArray(items)?items.filter(Boolean):[];return values.length?'<ul>'+values.map(item=>{if(item&&typeof item==='object'){let text=esc(item.text||item.title||JSON.stringify(item));let id=item.id?' <span class="muted">['+esc(item.id)+']</span>':'';let pages=Array.isArray(item.pages)&&item.pages.length?' <span class="muted">('+t('rulews.evidence_pages')+' '+esc(item.pages.join(''+P('、')+''))+')</span>':'';let blocks=Array.isArray(item.blocks)&&item.blocks.length?' <span class="muted">('+t('rulews.evidence_blocks')+' '+esc(item.blocks.join(''+P('、')+''))+')</span>':'';return '<li>'+text+id+pages+blocks+'</li>'}return '<li>'+esc(String(item))+'</li>'}).join('')+'</ul>':'<div class="muted">'+t('classification.none')+'</div>'}
function renderCodebookStatus(profile){lastCodebookProfile=profile;let host=$('codebookstatus');if(!profile||profile.status==='none'||!profile.status){host.textContent=t('rulews.not_prepared');let effective=$('ruleeffective');if(effective)effective.innerHTML='<b>'+t('rulejob.effective_title')+'</b><br>'+esc(t('rulews.not_prepared'));applyCodebookLockState();return}let lock=profile.status==='locked';host.innerHTML=(lock?'<span class="ok">'+t('rulews.locked')+'</span>':'<span class="error">'+t('rulews.draft')+'</span>')+''+P('：')+'<b>'+esc(profile.source_path||profile.source_name||'—')+'</b><br>'+(profile.unit_kind==='block'?esc(profile.block_count||profile.page_count||0)+' '+t('rulews.blocks'):esc(profile.page_count||0)+' '+t('rulews.pages'))+' · '+esc(profile.parser_model||'—')+(lock?'<br>'+t('rulews.reused'):'<br>'+t('rulews.confirm'));let effective=$('ruleeffective');if(effective)effective.innerHTML='<b>'+t('rulejob.effective_title')+'</b><br>'+host.innerHTML;applyCodebookLockState()}
async function loadCodebookStatus(){try{renderCodebookStatus(await api('/api/codebook'))}catch(e){setUIMessage($('codebookstatus'),e.uiMessage||{text:e.message},'error')}await loadCodebookTask()}
// After locking from beside the rules drawer the review has done its job:
// slide it back into the drawer and leave only the rules drawer open.
async function closeRuleReview(){let chat=$('chat');if(document.body.classList.contains('rules-side-by-side')&&!matchMedia('(prefers-reduced-motion: reduce)').matches){chat.classList.add('rule-review-leaving');await new Promise(resolve=>setTimeout(resolve,180))}chat.classList.remove('rule-review-leaving');await leaveCodebookWorkspace()}
async function leaveCodebookWorkspace(){if(!await allowRuleDraftTransition())return;lastCodebookWorkspaceProfile=null;let composer=$('composer');composer.style.display='flex';$('chat').classList.remove('codebook-workspace');loadHistory()}
async function showCodebookWorkspace(profile){if(activeContextDrawer!=='rules'||!$('contextbackdrop')?.classList.contains('open'))openContextDrawer('rules');if(ruleEditState){captureRuleEditor();if(ruleEditState.binding===ruleEditorBinding(profile)){renderRuleEditor();return}if(!await allowRuleDraftTransition())return}lastCodebookWorkspaceProfile=profile;let draft=profile.draft||{};$('composer').style.display='none';let classes=(draft.classes||[]).map(item=>'<article class="card codebook-class"><h3>'+esc(item.name||t('rulews.untitled'))+'</h3><div>'+esc(item.definition||t('rulews.no_definition'))+'</div><b>'+t('rulews.decision_rules')+'</b>'+codebookList(item.decision_rules)+'<b>'+t('rulews.boundaries')+'</b>'+codebookList(item.boundaries)+'<div class="muted">'+(Array.isArray(item.evidence_blocks)?t('rulews.evidence_blocks')+''+P('：')+''+esc(item.evidence_blocks.join(''+P('、')+'')||'—'):t('rulews.evidence_pages')+''+P('：')+''+esc((item.evidence_pages||[]).join(''+P('、')+'')||'—'))+'</div></article>').join('')||'<div class="card error">'+t('rulews.no_class')+'</div>';let usage=profile.usage||{},ocr=profile.ocr_runtime||{},locked=profile.status==='locked';let ocrText=ocr.status==='not applicable to DOCX'?t('rulews.ocr_docx'):ocr.status==='not applicable to TXT'?t('rulews.ocr_txt'):(ocr.available?(t('rulews.ocr_enabled')+' · '+esc(ocr.command||'Tesseract')+(ocr.german_available?' · deu':' · eng')):(t('rulews.ocr_disabled')+' · '+esc(ocr.status||'Tesseract')));$('chat').className='chat codebook-workspace';$('chat').innerHTML='<section class="workspace-inner"><h1>'+t('rulews.title')+'</h1><div class="muted">'+(locked?t('rulews.locked_intro'):t('rulews.draft_intro'))+'</div><div class="card"><b>'+t('rulews.source')+''+P('：')+'</b>'+esc(profile.source_name||'—')+'<br><span class="muted">'+t('rulews.parser_model')+''+P('：')+''+esc(profile.parser_model||'—')+' · '+(profile.unit_kind==='block'?t('rulews.blocks')+''+P('：')+''+esc(profile.block_count||profile.page_count||0):t('rulews.pages')+''+P('：')+''+esc(profile.page_count||0))+' · '+t('rulews.groups')+''+P('：')+''+esc(profile.page_groups||0)+' · Token'+P('：')+''+usageNumber(usage.input)+' / '+usageNumber(usage.output)+(' · '+usageCost(usage))+'<br>'+ocrText+'</span></div><h2>'+t('rulews.classes')+'</h2>'+((profile.unparsed_units||[]).length?'<div class="card error">'+esc(t('rulews.unparsed_units',{units:profile.unparsed_units.map(codebookUnitText).join(''+P('、')+'')}))+'</div>':'')+classes+'<h2>'+t('rulews.global_rules')+'</h2><div class="card">'+codebookList(draft.global_rules)+'</div><h2>'+t('rulews.table_rules')+'</h2><div class="card">'+codebookList(draft.table_rules)+'</div><h2>'+t('rulews.uncertainties')+'</h2><div class="card">'+codebookList(draft.uncertainties)+'</div><div class="workspace-actions"><button class="ghost" onclick="editCodebookDraft()">'+t('rules.edit')+'</button>'+ (locked?'<button class="ghost" onclick="leaveCodebookWorkspace()">'+t('rulews.back')+'</button>':'<button onclick="lockCodebook()">'+t('rulews.lock_action')+'</button><button class="ghost" onclick="leaveCodebookWorkspace()">'+t('rulews.defer')+'</button>')+'</div></section>';$('chat').scrollTop=0}
// ---- Codebook preparation: an observable background job --------------------
// The server runs the job and keeps its state (stage, page/block, log, final
// result or classified failure).  The page only renders that record, so a
// reload or a reopened drawer shows the same, continuously updated status.
let codebookPollTimer=null,codebookPollFailures=0,codebookOperation=null,codebookStopRequested=false,codebookModelDefaults={default_model:'',recommended_model:'claude-haiku-5-5'},ruleModelDraft=null,codebookStatusError=null;
function codebookRunning(){return lastCodebookTask?.state==='running'}
function jobCopy(group,name,params={}){let key=['rulejob',group,name].join('.');return t(key,params)}
function codebookUnitText(unit){if(!unit)return '';if(unit.kind==='page')return t('rulejob.unit.page',{number:unit.number});return unit.first===unit.last?t('rulejob.unit.block',{number:unit.first}):t('rulejob.unit.blocks',{first:unit.first,last:unit.last})}
function codebookProgressText(task){let p=task?.progress||{};if(p.total&&(task.stage==='parsing'||task.stage==='extracting')){if(task.unit_kind==='page')return t('rulejob.progress.page',{current:p.current,total:p.total});if(task.stage==='parsing')return t('rulejob.progress.blocks',{current:p.current,total:p.total})}if(p.total&&task?.stage==='merging')return t('rulejob.progress.merge',{current:p.current,total:p.total});return jobCopy('where',(task?.stage||'reading'))}
function codebookStageText(task){let entries=(task?.log||[]).filter(entry=>/^rulejob\.(stage\.|log\.merge_(section|outline)$)/.test(String(entry.message?.message_key||'')));return entries.length?uiCopy(entries[entries.length-1].message):jobCopy('where',(task?.stage||'reading'))}
// Three user-facing steps over the server stages; the current one is highlighted.
const RULE_STEPS=[['read',['reading','extracting']],['parse',['parsing']],['merge',['merging','saving']]];
function ruleStepsHtml(task){let current=RULE_STEPS.findIndex(([,stages])=>stages.includes(task?.stage));if(current<0)current=0;
  return '<ol class="rulejob-steps">'+RULE_STEPS.map(([name],index)=>{let key='rulejob.step.'+name;return '<li class="'+(index<current?'done':index===current?'current':'')+'"><span class="rulejob-step-mark">'+(index<current?'✓':index+1)+'</span>'+esc(t(key))+'</li>'}).join('')+'</ol>'}
function codebookLatestWarning(task){let log=task?.log||[],last=log[log.length-1];return last&&last.level==='warning'?uiCopy(last.message):''}
function codebookTime(value){if(!value)return '—';let date=new Date(value);return isNaN(date)?String(value):date.toLocaleString(uiLanguage==='zh'?'zh-CN':uiLanguage==='de'?'de-DE':'en-GB')}
function codebookElapsed(task){let start=Date.parse(task?.started_at),end=task?.finished_at?Date.parse(task.finished_at):Date.now();if(isNaN(start)||isNaN(end))return '—';let seconds=Math.max(0,Math.round((end-start)/1000));return seconds<60?seconds+' s':Math.floor(seconds/60)+' min '+String(seconds%60).padStart(2,'0')+' s'}
function codebookEffectiveProfile(){let profile=lastCodebookProfile;return profile&&profile.status&&profile.status!=='none'?profile:null}
function codebookCardSummary(){
  let task=lastCodebookTask,profile=codebookEffectiveProfile(),lines=[];
  if(task?.state==='running')return t('rulejob.card.running',{progress:codebookProgressText(task)});
  if(task?.state==='failed')lines.push(t('rulejob.card.failed',{reason:uiCopy(task.failure?.short)||t('rulejob.short.internal')}));
  else if(task?.state==='cancelled')lines.push(t('rulejob.card.cancelled'));
  if(profile){let state=t(profile.status==='locked'?'rulejob.card.locked':'rulejob.card.draft');lines.push(lines.length?t('rulejob.card.effective',{name:profile.source_name||'—',status:state}):state+' · '+(profile.source_name||'—'))}
  else if(lines.length)lines.push(t('rulejob.card.no_effective'));
  return lines.join('\n')||t('rules.no_file');
}
function ruleModelValue(){return ruleModelDraft??(codebookModelDefaults.default_model||codebookModelDefaults.recommended_model||selectedModel())}
function currentRuleModel(){let input=$('rulemodel');return String(input?input.value:ruleModelValue()).trim().toLowerCase()}
function validRuleModelId(model){return !!model&&!/[\s?#\\]/.test(model)&&/(gemini|claude)|^(gpt|o1|o3|llama|glm|deepseek)|openai-/.test(model)}
// A typed model ID counts only after "Confirm" (or Enter); a listed model at once.
let ruleModelPending=false;
// Confirming never moves focus: an Enter that confirms must not also start preparing.
function confirmRuleModel(){ruleModelPending=false;ruleModelDraft=$('rulemodel')?.value??ruleModelDraft;renderRuleModelHint()}
function renderRuleModelHint(){let host=$('rulemodelhint');if(!host)return;if(codebookLocked()){setUIMessage(host,{message_key:'rulejob.model_locked',params:{model:lastCodebookProfile.parser_model||'—'}},'muted');return}let model=currentRuleModel();if(ruleModelPending){setUIMessage(host,{message_key:'rulejob.model_confirm_needed'},'muted');return}if(!model){setUIMessage(host,{message_key:'rulejob.model_required'},'error');return}if(!validRuleModelId(model)){setUIMessage(host,{message_key:'rulejob.model_invalid',params:{model}},'error');return}setUIMessage(host,{message_key:'rulejob.model_this_run',params:{model}},'ok')}
// Rule-parsing model: the same list as the chat model, the recommended one
// marked, plus "other" for a typed Farm model ID (no connection test here:
// a model that cannot be reached is reported when preparation starts).
function ruleModelOptions(){let recommended=codebookModelDefaults.recommended_model;let options=[...$('model').options].filter(option=>option.value&&option.value!=='__custom__');return options.map(option=>'<option value="'+escAttr(option.value)+'">'+esc(option.textContent.trim())+(option.value===recommended?' — '+esc(t('rulejob.recommended_tag')):'')+'</option>').join('')+'<option value="__custom__">'+esc(t('rulejob.model_custom'))+'</option>'}
function syncRuleModelSelect(){let select=$('rulemodelselect'),input=$('rulemodel'),row=$('rulemodelcustomrow');if(!select||!input)return;let value=String(input.value||'').trim().toLowerCase();let preset=[...select.options].some(option=>option.value===value&&option.value!=='__custom__');select.value=preset?value:'__custom__';if(row)row.style.display=preset?'none':'flex'}
function ruleModelPicked(value){let input=$('rulemodel'),row=$('rulemodelcustomrow');if(!input)return;if(value==='__custom__'){if(row)row.style.display='flex';if([...$('rulemodelselect').options].some(option=>option.value===input.value))input.value='';ruleModelDraft=input.value;ruleModelPending=true;input.focus()}else{input.value=value;ruleModelDraft=value;ruleModelPending=false;if(row)row.style.display='none'}renderRuleModelHint()}
function useRecommendedRuleModel(){ruleModelDraft=codebookModelDefaults.recommended_model;let input=$('rulemodel');if(input)input.value=ruleModelDraft;syncRuleModelSelect();renderRuleModelHint()}
async function copyText(value,host){try{if(!navigator.clipboard)throw Error('clipboard');await navigator.clipboard.writeText(value);if(host)setUIMessage(host,{message_key:'rulejob.action.copied'},'ok')}catch{if(host)setUIMessage(host,{message_key:'rulejob.action.copy_failed'},'error')}}
function copyCodebookPath(){copyText(lastCodebookTask?.source?.path||'',$('rulejobcopymsg'))}
// View / replace / delete belong to prepared rules, so they live in the
// preparation status card and only appear once rules exist.
function ruleProfileActions(){if(!codebookEffectiveProfile())return '';return '<div class="rulejob-actions"><button class="'+(codebookLocked()?'ghost':'')+'" id="ruleview" onclick="viewCodebook()">'+t('rules.view')+'</button><button class="ghost" id="rulereplace" onclick="replaceCodebook()">'+t('rules.replace')+'</button><button class="ghost danger" id="ruledelete" onclick="deleteCodebook()">'+t('rules.delete')+'</button></div>'}
function ruleProfileSummary(profile){return '<div class="muted">'+(profile.unit_kind==='block'?esc(profile.block_count||profile.page_count||0)+' '+t('rulews.blocks'):esc(profile.page_count||0)+' '+t('rulews.pages'))+' · '+esc(profile.parser_model||'—')+'</div>'}
function ruleRow(label,value,raw=false){return '<dt>'+esc(label)+'</dt><dd>'+(raw?value:esc(value==null||value===''?'—':String(value)))+'</dd>'}
function renderRuleJobPanel(){
  let host=$('rulejobpanel');if(host){
  let task=lastCodebookTask,details=host.querySelector('details'),open=!!details?.open;
  let profileNow=codebookEffectiveProfile();host.hidden=false;
  if(!task){host.innerHTML='<div class="rulejob-head"><b>'+t('rulejob.panel.title')+'</b></div>'+(profileNow?'<div class="'+(codebookLocked()?'ok':'muted')+'">'+esc(t(codebookLocked()?'rulejob.panel.locked_ready':'rulejob.panel.draft_ready',{name:profileNow.source_name||profileNow.source_path||'—'}))+'</div>'+ruleProfileSummary(profileNow)+ruleProfileActions():'<div class="muted">'+esc(t('rulews.not_prepared'))+'</div>');if(codebookStatusError)host.innerHTML+='<div class="error">'+esc(uiCopy(codebookStatusError))+'</div>'}
  else{
    let state=task.state==='succeeded'||task.state==='failed'||task.state==='cancelled'?task.state:'running',source=task.source||{},result=task.result||{},failure=task.failure||{};
    let chip='<span class="rulejob-chip '+state+'">'+(state==='running'?'<span class="rulejob-spinner" aria-hidden="true"></span>':'')+esc(jobCopy('state',state))+'</span>';
    let rows='',body='',meta='<div class="rulejob-file"><b>'+esc(source.name||'—')+'</b><span class="muted">'+esc(String(source.type||'').toUpperCase())+' · '+esc(t('rulejob.model_label'))+P('：')+esc(task.model||'—')+'</span></div>';
    if(state==='running'){
      // While running only what a user follows: file, steps, current step,
      // elapsed time and stop. Start time and call counts stay in the log.
      let warning=codebookLatestWarning(task);
      body='<div class="rulejob-file"><b>'+esc(source.name||'—')+'</b><span class="muted">'+esc(t('rulejob.model_label'))+P('：')+esc(task.model||'—')+'</span></div>'+ruleStepsHtml(task)+
        '<div class="rulejob-stage">'+esc(codebookStageText(task))+'</div>'+(warning?'<div class="rulejob-note warning">'+esc(warning)+'</div>':'')+
        (codebookStopRequested?'<div class="rulejob-note">'+t('rulejob.stopping')+'</div>':'')+
        '<div class="rulejob-actions"><button class="ghost" id="rulejobstop" onclick="stopCodebookPreparation()"'+(codebookStopRequested?' disabled':'')+'>'+t('rulejob.action.stop')+'</button><span class="rulejob-elapsed muted">'+esc(t('rulejob.panel.elapsed'))+' '+esc(codebookElapsed(task))+'</span></div>';
    }else if(state==='succeeded'){
      let profile=codebookEffectiveProfile(),current=profile&&(profile.version===result.profile_version||(!!source.path&&profile.source_path===source.path));
      let final=current?t(profile.status==='locked'?'rulejob.card.locked':'rulejob.card.draft'):t('rulejob.state.succeeded');
      // Finished: what was prepared and the one next step; finish time, parse
      // units and call counts are in the log.
      rows+=ruleRow(t('rulejob.panel.path'),'<code>'+esc(source.path||'—')+'</code> <button class="ghost" onclick="copyCodebookPath()">'+t('rulejob.action.copy_path')+'</button><span id="rulejobcopymsg" class="muted"></span>',true)+(task.unit_kind==='page'?ruleRow(t('rulejob.panel.pages'),result.page_count):ruleRow(t('rulejob.panel.blocks'),result.block_count))+(result.encoding?ruleRow(t('rulejob.panel.encoding'),result.encoding):'');
      let locked=current&&profile.status==='locked';
      body+='<div class="rulejob-final '+(locked?'locked':current?'draft':'')+'">'+esc(final)+(current&&!locked?'<span>'+esc(t('rulews.confirm'))+'</span>':'')+'</div>'+ruleProfileActions();
    }else{
      rows+=ruleRow(t('rulejob.panel.path'),'<code>'+esc(source.path||'—')+'</code> <button class="ghost" onclick="copyCodebookPath()">'+t('rulejob.action.copy_path')+'</button><span id="rulejobcopymsg" class="muted"></span>',true)+ruleRow(t('rulejob.panel.failed_stage'),jobCopy('where',(failure.stage||task.stage||'reading')))+(failure.unit?ruleRow(t('rulejob.panel.failed_unit'),codebookUnitText(failure.unit)):'')+ruleRow(t('rulejob.panel.finished'),codebookTime(task.finished_at));
      body+='<div class="rulejob-reason">'+esc(uiCopy(failure.message)||t('rulejob.reason.internal'))+'</div>'+(task.previous_profile?'<div class="rulejob-note">'+esc(t('rulejob.panel.kept_rules'))+'</div>':'')+(profileNow?'<div class="rulejob-note">'+esc(t('rulejob.card.effective',{name:profileNow.source_name||'—',status:t(profileNow.status==='locked'?'rulejob.card.locked':'rulejob.card.draft')}))+'</div>':'')+'<div class="rulejob-actions"><button id="rulejobretry" onclick="retryCodebookPreparation()">'+t('rulejob.action.retry')+'</button></div>'+ruleProfileActions();
    }
    let log=(task.log||[]).map(entry=>'<li class="'+escAttr(entry.level||'info')+'"><time>'+esc(codebookTime(entry.at))+'</time>'+esc(uiCopy(entry.message))+'</li>').join('');
    let technical=failure.technical?'<b>'+t('rulejob.details.technical')+'</b><pre>'+esc(failure.technical)+'</pre>':'';
    body+='<details id="rulejobdetails"'+(open?' open':'')+'><summary>'+t('rulejob.details.title')+'</summary><ol class="rulejob-log">'+log+'</ol>'+technical+'</details>';
    if(codebookStatusError)body+='<div class="error">'+esc(uiCopy(codebookStatusError))+'</div>';
    // Each refresh replaces the panel; keep where the reader is in the log and
    // the diagnostics: at the bottom it follows new entries, elsewhere it stays.
    let keep=['.rulejob-log'].map(selector=>{let node=host.querySelector(selector);return node?{selector,top:node.scrollTop,bottom:node.scrollHeight-node.scrollTop-node.clientHeight<8}:null}).filter(Boolean);
    let drawer=$('contextdrawerbody'),drawerTop=drawer?drawer.scrollTop:0;
    host.innerHTML='<div class="rulejob-head"><b>'+t('rulejob.panel.title')+'</b>'+chip+'</div>'+(state==='running'?'':meta)+(rows?'<dl>'+rows+'</dl>':'')+body;
    for(let item of keep){let node=host.querySelector(item.selector);if(node)node.scrollTop=item.bottom?node.scrollHeight:item.top}
    if(drawer)drawer.scrollTop=drawerTop;
  }}
  applyCodebookBusyState();refreshContextPanel();
}
// While a job runs nothing may change its file, start a second job or open a
// draft that is not complete yet; the server enforces the same rule.
function codebookLocked(){return lastCodebookProfile?.status==='locked'}
function applyCodebookLockState(){let locked=codebookLocked(),running=codebookRunning(),profile=lastCodebookProfile||{};for(let id of ['rulefilepick','contextcodebookpath','rulemodel','rulemodelselect','codebook']){let node=$(id);if(node)node.disabled=running||locked}for(let node of document.querySelectorAll('button[onclick="pick(\'file\',\'codebook\')"]'))node.disabled=running||locked;if(locked){let path=profile.source_path||profile.source_name||'';for(let id of ['contextcodebookpath','codebook']){let node=$(id);if(node&&path)node.value=path}let model=$('rulemodel');if(model&&profile.parser_model)model.value=profile.parser_model}syncRuleModelSelect();renderRuleModelHint()}
function applyCodebookBusyState(){let running=codebookRunning(),reason=running?t('rulejob.busy_controls'):'';for(let id of ['ruleprepare','rulefilepick','contextcodebookpath','rulemodel','rulemodelselect','ruleview','rulereplace','ruledelete','codebook']){let node=$(id);if(node){node.disabled=running;if(running)node.title=reason;else if(node.title===t('rulejob.busy_controls'))node.removeAttribute('title')}}for(let node of document.querySelectorAll('button[onclick="prepareCodebook()"],button[onclick="viewCodebook()"],button[onclick="viewPreparedCodebook()"],button[onclick="changeCodebook()"],button[onclick="replaceCodebook()"],button[onclick="deleteCodebook()"],button[onclick="lockCodebook()"],button[onclick="editCodebookDraft()"],button[onclick="pick(\'file\',\'codebook\')"]'))node.disabled=running;applyCodebookLockState()}
async function loadCodebookTask(){try{let x=await api('/api/codebook/task');codebookStatusError=null;codebookModelDefaults={default_model:x.default_model||'',recommended_model:x.recommended_model||codebookModelDefaults.recommended_model};let input=$('rulemodel');if(input&&ruleModelDraft==null&&!input.value)input.value=ruleModelValue();setCodebookTask(x.task)}catch(e){codebookStatusError={message_key:'rulejob.status_unavailable',params:{detail:e.uiMessage||{text:e.message}}};renderRuleJobPanel()}}
function setCodebookTask(task){let wasRunning=codebookRunning();lastCodebookTask=task||null;renderRuleJobPanel();if(codebookRunning())startCodebookPolling();else{stopCodebookPolling();if(wasRunning||codebookOperation)finishCodebookPreparation()}}
function startCodebookPolling(){if(codebookPollTimer)return;codebookPollFailures=0;codebookPollTimer=setInterval(pollCodebookTask,1000)}
function stopCodebookPolling(){if(codebookPollTimer)clearInterval(codebookPollTimer);codebookPollTimer=null}
async function pollCodebookTask(){try{let x=await api('/api/codebook/task');codebookPollFailures=0;codebookStatusError=null;setCodebookTask(x.task)}catch(e){codebookPollFailures+=1;codebookStatusError={message_key:'rulejob.status_unavailable',params:{detail:e.uiMessage||{text:e.message}}};if(codebookPollFailures>=5){stopCodebookPolling();if(lastCodebookTask?.state==='running')lastCodebookTask=null;if(codebookOperation){endOperation(codebookOperation);codebookOperation=null}}renderRuleJobPanel()}}
async function finishCodebookPreparation(){
  let operation=codebookOperation,task=lastCodebookTask;codebookOperation=null;codebookStopRequested=false;if(operation)endOperation(operation);
  let ownJob=(operation&&task?.request_id===operation.id)||(codebookAttachedTaskId&&task?.task_id===codebookAttachedTaskId);codebookAttachedTaskId=null;
  if(ownJob&&task.context_after&&!pageContextStale&&workbenchContext===task.context_before)workbenchContext=task.context_after;
  try{let profile=await api('/api/codebook');renderCodebookStatus(profile);renderStatus(await api('/api/status'));if(operation&&task?.state==='succeeded'&&profile?.version===task.result?.profile_version)showCodebookWorkspace(profile)}catch(e){setUIMessage($('codebookstatus'),e.uiMessage||{text:e.message},'error')}
  renderRuleJobPanel();
}
async function prepareCodebook(){
  if(codebookRunning())return;
  if(!await allowRuleDraftTransition())return;
  let host=$('contextrulemsg')||$('codebookstatus'),path=$('codebook').value.trim();
  if(codebookLocked()){setUIMessage(host,{message_key:'rulews.already_prepared',params:{name:lastCodebookProfile.source_name||lastCodebookProfile.source_path||'—',model:lastCodebookProfile.parser_model||'—'}},'ok');return}
  if(!path){setUIMessage(host,{message_key:'rulews.choose_file'},'error');return}
  let model=currentRuleModel();
  if(!model){setUIMessage(host,{message_key:'rulejob.model_required'},'error');$('rulemodel')?.focus();return}
  if(!validRuleModelId(model)){setUIMessage(host,{message_key:'rulejob.model_invalid',params:{model}},'error');$('rulemodel')?.focus();return}
  if(ruleModelPending){setUIMessage(host,{message_key:'rulejob.model_confirm_first'},'error');$('rulemodelconfirm')?.focus();return}
  if(host)host.textContent='';
  let previous=lastCodebookTask,operation=beginOperation();codebookOperation=operation;codebookStopRequested=false;
  lastCodebookTask={state:'running',stage:'reading',model,request_id:operation.id,unit_kind:/\.pdf$/i.test(path)?'page':'block',source:{path,name:path.split(/[\\/]/).pop(),type:(path.split('.').pop()||'').toLowerCase()},progress:{},log:[],calls:0,started_at:new Date().toISOString()};
  renderRuleJobPanel();
  try{let x=await api('/api/codebook/prepare',{method:'POST',body:JSON.stringify({path,model,request_id:operation.id,background:true})});codebookModelDefaults.default_model=model;ruleModelDraft=null;setCodebookTask(x.task);if(codebookRunning())startCodebookPolling()}
  catch(e){codebookOperation=null;endOperation(operation);lastCodebookTask=previous;renderRuleJobPanel();setUIMessage($('contextrulemsg')||host,{message_key:'rulejob.start_failed',params:{detail:e.uiMessage||{text:e.message}}},'error')}
}
function retryCodebookPreparation(){let source=lastCodebookTask?.source;if(source?.path&&!$('codebook').value.trim()){$('codebook').value=source.path;let input=$('contextcodebookpath');if(input)input.value=source.path}if(lastCodebookTask?.model&&ruleModelDraft==null){ruleModelDraft=lastCodebookTask.model;let input=$('rulemodel');if(input)input.value=ruleModelDraft}prepareCodebook()}
async function stopCodebookPreparation(){let task=lastCodebookTask;if(!codebookRunning()||!task.request_id||codebookStopRequested)return;codebookStopRequested=true;if(activeOperation&&activeOperation.id===task.request_id)activeOperation.stopping=true;renderRuleJobPanel();try{await api('/api/operation/cancel',{method:'POST',body:JSON.stringify({request_id:task.request_id})})}catch(e){codebookStopRequested=false;codebookStatusError=e.uiMessage||{text:e.message};renderRuleJobPanel()}}
async function viewCodebook(){if(codebookRunning())return;if(!await allowRuleDraftTransition())return;try{let profile=await api('/api/codebook');if(!profile||!profile.status)throw Error(t('rulews.not_prepared'));renderCodebookStatus(profile);showCodebookWorkspace(profile)}catch(e){setUIMessage($('contextrulemsg')||$('codebookstatus'),e.uiMessage||{text:e.message},'error')}}
// In-page confirmation; replaces the browser's native confirm() for rule actions.
function appDialog(text,{kind='confirm',value=''}={}){return new Promise(resolve=>{$('appconfirm')?.remove();let backdrop=document.createElement('div');backdrop.id='appconfirm';backdrop.className='app-confirm-backdrop';backdrop.innerHTML='<section class="app-confirm" role="alertdialog" aria-modal="true" aria-labelledby="appconfirmtext"><p id="appconfirmtext"></p>'+(kind==='prompt'?'<input id="appconfirminput" style="width:100%;margin:0 0 16px">':'')+'<div class="row">'+(kind==='notice'?'':'<button class="ghost" id="appconfirmcancel">'+t('confirm.cancel')+'</button>')+'<button id="appconfirmok">'+t('confirm.ok')+'</button></div></section>';backdrop.querySelector('#appconfirmtext').textContent=text;let input=backdrop.querySelector('#appconfirminput');if(input)input.value=value;let done=ok=>{window.removeEventListener('keydown',key,true);backdrop.remove();resolve(kind==='prompt'?(ok?input.value:null):kind==='notice'?true:ok)},key=event=>{if(event.key==='Escape'){event.stopImmediatePropagation();event.preventDefault();done(false)}else if(event.key==='Enter'&&input&&document.activeElement===input){event.preventDefault();done(true)}};backdrop.querySelector('#appconfirmok').onclick=()=>done(true);let cancel=backdrop.querySelector('#appconfirmcancel');if(cancel)cancel.onclick=()=>done(false);backdrop.addEventListener('click',event=>{if(event.target===backdrop)done(false)});window.addEventListener('keydown',key,true);document.body.append(backdrop);(input||backdrop.querySelector('#appconfirmok')).focus();if(input)input.select()})}
function appConfirm(text){return appDialog(text)}
function appNotice(text){return appDialog(String(text||''),{kind:'notice'})}
function appPrompt(text,value=''){return appDialog(text,{kind:'prompt',value})}
async function lockCodebook(){if(codebookRunning())return;if(!await allowRuleDraftTransition())return;if(!await appConfirm(t('rulews.lock_confirm')))return;try{let profile=await api('/api/codebook/lock',{method:'POST'});renderCodebookStatus(profile);renderStatus(await api('/api/status'));await closeRuleReview();setUIMessage($('setupmsg'),{message_key:'rulews.lock_success'},'ok');renderRuleJobPanel()}catch(e){setUIMessage($('codebookstatus'),e.uiMessage||{text:e.message},'error')}}
// Replace and delete both remove the prepared rules (the status card
// disappears with them); replace then asks for the new rule file.
async function removeCodebook(confirmKey,successKey){if(codebookRunning())return false;if(!await allowRuleDraftTransition())return false;if(!await appConfirm(t(confirmKey)))return false;try{await api('/api/codebook',{method:'DELETE'});$('codebook').value='';let input=$('contextcodebookpath');if(input)input.value='';lastCodebookTask=null;renderCodebookStatus({status:'none'});if($('chat').classList.contains('codebook-workspace'))await leaveCodebookWorkspace();renderRuleJobPanel();setUIMessage($('contextrulemsg')||$('setupmsg'),{message_key:successKey},'ok');return true}catch(e){setUIMessage($('contextrulemsg')||$('codebookstatus'),e.uiMessage||{text:e.message},'error');return false}}
async function replaceCodebook(){if(await removeCodebook('rulews.replace_confirm','rulews.replace_success')&&activeContextDrawer==='rules')contextPickRule()}
async function deleteCodebook(){await removeCodebook('rulews.delete_confirm','rulews.delete_success')}
const changeCodebook=replaceCodebook;
let sessionOffset=0,sessionHasMore=false,sessionLoading=false,currentSessionName='';
function initSessionSidebar(){if($('sessionpanel'))return;let left=document.querySelector('.shell > .side');if(!left)return;let style=document.createElement('style');style.textContent='.side.left{display:flex;flex-direction:column;overflow:hidden;padding-bottom:10px}.left-content{overflow:auto;min-height:0;padding-right:2px}.session-panel{border-top:1px solid #334155;margin-top:10px;padding-top:10px;display:flex;flex-direction:column;min-height:155px;max-height:42vh}.session-new{width:100%;margin-bottom:8px;text-align:left}.session-list{overflow:auto;min-height:0}.session-row{display:flex;align-items:center;gap:4px;border-radius:7px;margin:2px 0;padding:6px 5px;cursor:pointer;color:#dbeafe}.session-row:hover,.session-row.active{background:#263244}.session-title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}.session-more{visibility:hidden;width:25px;padding:2px 3px;background:transparent;color:#cbd5e1}.session-row:hover .session-more,.session-row.active .session-more{visibility:visible}.session-pin{font-size:10px;color:#7dd3fc}.session-loading{text-align:center;padding:8px;color:#94a3b8}.session-menu{position:fixed;z-index:100;min-width:130px;padding:5px;background:#1e293b;border:1px solid #475569;border-radius:8px;box-shadow:0 12px 30px rgba(0,0,0,.4)}.session-menu button{display:block;width:100%;text-align:left;background:transparent;color:#e5e7eb;padding:7px 9px}.session-menu button:hover{background:#334155}.session-menu button.delete{color:#fca5a5}';document.head.append(style);left.classList.add('left');let content=document.createElement('div');content.className='left-content';while(left.firstChild)content.append(left.firstChild);left.append(content);let old=$('session')?.closest('.field');if(old)old.style.display='none';let panel=document.createElement('section');panel.id='sessionpanel';panel.className='session-panel';panel.innerHTML='<button id="newsessionbutton" class="ghost session-new" onclick="newSession()"></button><div id="sessionlist" class="session-list"></div>';left.append(panel);localizeSessionChrome();$('sessionlist').addEventListener('scroll',()=>{let el=$('sessionlist');if(sessionHasMore&&!sessionLoading&&el.scrollTop+el.clientHeight>=el.scrollHeight-18)loadSessions(false)});document.addEventListener('click',event=>{if(!event.target.closest('.session-more')&&!event.target.closest('#sessionmenu'))closeSessionMenu()})}
function localizeSessionChrome(){setI18nText($('newsessionbutton'),'session.new')}
function closeSessionMenu(){$('sessionmenu')?.remove()}
async function loadSessions(reset=true){if(sessionLoading)return;if(reset){sessionOffset=0;sessionHasMore=false;renderSessionRows([],true)}sessionLoading=true;try{let x=await api('/api/sessions?offset='+sessionOffset+'&limit=10');currentSessionName=x.current;let existingCount=$('sessionlist').querySelectorAll('.session-row').length,items=x.sessions;renderSessionRows(items,!reset);let rows=[...$('sessionlist').querySelectorAll('.session-row')];items.forEach((item,index)=>rows[existingCount+index].dataset.name=item.name);sessionOffset+=items.length;sessionHasMore=!!x.has_more}catch(e){$('sessionmsg').textContent=e.message}finally{sessionLoading=false;$('sessionloading')?.remove()}}
async function restoreSessionTree(target,paths){$('treestatus').textContent=rt('session.restoring');let x=await api('/api/target-tree?target='+encodeURIComponent(target));savedTargetSelection=new Set(paths||[]);treeRestoreNote=rt('session.restored');let host=$('targettree');host.classList.remove('muted');host.innerHTML='';host.append(makeTreeNode(x.tree));refreshAllFolderStates()}
async function restoreSessionContext(){try{let x=await api('/api/session/context');setSelectedModel(x.model);let target=x.target||{};$('targetpath').value=target.path||'';$('codebook').value=x.codebook_path||'';if(target.path&&target.kind==='文件夹'){await restoreSessionTree(target.path,target.selected_paths)}else{clearTargetTree()}materialDraftDirty=false;await loadCodebookStatus();loadDocs();loadCoverage()}catch(e){console.warn('Could not restore session context',e);setUIMessage($('treestatus'),[{message_key:'session.restore_failed'},{text:e.message}],'error')}}
async function openSessionByName(name){if(!await allowRuleDraftTransition())return;try{closeSessionMenu();let s=await api('/api/session/open',{method:'POST',body:JSON.stringify({name})});renderStatus(s);await restoreSessionContext();await loadHistory();await loadSessions(true)}catch(e){setUIMessage($('sessionmsg'),e.uiMessage||{text:e.message},'error')}}
async function newSession(){if(!await allowRuleDraftTransition())return;try{let s=await api('/api/session/new',{method:'POST'});renderStatus(s);$('targetpath').value='';$('codebook').value='';clearTargetTree();await loadHistory();await loadSessions(true);loadDocs();loadCodebookStatus()}catch(e){setUIMessage($('sessionmsg'),e.uiMessage||{text:e.message},'error')}}
async function renameSession(name){let value=await appPrompt(t('session.rename_prompt'),name);if(!value?.trim())return;try{let s=await api('/api/session/rename',{method:'POST',body:JSON.stringify({name:value.trim(),source:name})});renderStatus(s);await loadSessions(true)}catch(e){appNotice(e.message)}}
async function pinSession(item){try{await api('/api/session/pin',{method:'POST',body:JSON.stringify({name:item.name,pinned:!item.pinned})});await loadSessions(true)}catch(e){appNotice(e.message)}}
async function deleteSession(name){if(name===currentSessionName&&!await allowRuleDraftTransition())return;if(!await appConfirm(t('session.delete_confirm')))return;try{let wasCurrent=name===currentSessionName;let s=await api('/api/session/delete',{method:'POST',body:JSON.stringify({confirmed:true,name})});renderStatus(s);if(wasCurrent){await restoreSessionContext();await loadHistory()}await loadSessions(true)}catch(e){appNotice(e.message)}}
// A history reload that returns after a new question was sent must not wipe it.
let chatGeneration=0;
async function loadHistory(){if(ruleEditState)return;let generation=chatGeneration;try{let x=await api('/api/history');if(ruleEditState||busy||generation!==chatGeneration)return;$('chat').innerHTML='';if(!x.history.length){renderEmptyChat();return}for(let item of x.history){if(item.role==='user'&&isClassifyRequest(item.content))classifyRequestTag();else message(item.content,item.role==='user'?'user':'assistant')}}catch{}}
async function setup(){if(!await allowRuleDraftTransition())return false;try{let model=selectedModel();if(!model)throw Error(t('model.id_required'));let s=await api('/api/setup',{method:'POST',body:JSON.stringify({workspace:'',state_dir:'',env_file:'',model:model,session:$('session').value.trim()||'default',language:uiLanguage})});if($('workspace'))$('workspace').value=s.workspace||'';renderStatus(s);await restoreSessionContext();await Promise.all([loadDocs(),loadSessions(),loadHistory(),loadCodebookStatus()]);setUIMessage($('setupmsg'),{message_key:'workspace.opened'});refreshAppChrome();$('startupnotice')?.remove();return true}catch(e){let detail=e.uiMessage||{text:e.message};setUIMessage($('setupmsg'),detail,'error');setUIMessage($('contextworkspacemsg'),detail,'error');showStartupNotice(detail);return false}}
async function openLegacySession(){if(!$('session').value)return;await setup()}
async function switchModel(){if(!await allowRuleDraftTransition())return;try{let model=selectedModel();if(!model)throw Error(t('model.id_required'));let s=await api('/api/model',{method:'POST',body:JSON.stringify({model})});renderStatus(s);clearResultPanels();await loadHistory();setUIMessage($('modelmsg'),[{message_key:'model.switched_prefix'},{text:model},{message_key:'model.context_unchanged'}],'ok')}catch(e){setUIMessage($('modelmsg'),e.uiMessage||{text:e.message},'error')}}
async function loadModelStatus(){try{
  let x=await api('/api/model-tests'),r=x.tests[selectedModel()];
  let button=$('modeltestbutton');if(button)button.dataset.state=!r?'untested':r.ok?'ok':'failed';
  if(!r){setUIMessage($('modelstatus'),{message_key:'model.untested'});return}
  setUIMessage($('modelstatus'),[{message_key:r.ok?'model.last_available':'model.last_failed'},r.tested_at,
    ...(r.ok?['; ',r.streaming_message||{text:r.streaming||''},'; ',{message_key:'model.usage_label'},' ',
      {message_key:r.usage_available===false?'model.usage_missing':'model.usage_returned'}]:[])],r.ok?'ok':'error');
}catch{}}
async function testModel(){try{
  let model=selectedModel();if(!model)throw Error(t('model.id_required'));
  setUIMessage($('modelmsg'),{message_key:'model.testing'});
  let x=await api('/api/model-test',{method:'POST',body:JSON.stringify({model})});$('startupnotice')?.remove();
  setUIMessage($('modelmsg'),x.ok?[{message_key:'model.available'},x.model,'; ',x.streaming_message||{text:x.streaming||''},
    {message_key:'usage.input_fragment'},String(x.input_tokens),{message_key:'usage.output_fragment'},String(x.output_tokens),
    {message_key:'usage.token_suffix'},' ',...(x.usage_available===false?[{message_key:'usage.unavailable'}]:[])]:
    [{message_key:'model.test_failed'},x.message_key?x:{text:x.message}],x.ok?'ok':'error');
  loadModelStatus();
}catch(e){let detail=e.uiMessage||{text:e.message};setUIMessage($('modelmsg'),detail,'error');showStartupNotice(detail)}}
function renderDocuments(documents){lastDocumentsSnapshot=documents;$('docs').innerHTML=documents.map(d=>`<div class="card">${esc(d.name)}<br><span class="muted">${esc(roleCopy(d.material_role_label))} · ${t('scan.report.chunks',{count:d.chunks})}</span></div>`).join('')||t('materials.empty')}
async function loadDocs(){try{renderDocuments(await api('/api/documents'))}catch{}}
async function addDoc(){try{let d=await api('/api/document',{method:'POST',body:JSON.stringify({path:$('docpath').value})});$('docpath').value='';loadDocs();$('setupmsg').textContent=`已索引 ${d.name}${P('（')}${d.chunks} chunks${P('）')}`}catch(e){setUIMessage($('setupmsg'),e.uiMessage||{text:e.message},'error')}}
function renderScanReport(x){setScanReportAvailable(x);renderScanDrawer(x)}
async function loadCoverage(){try{renderCoverageReport(await api('/api/coverage'))}catch{}}
function createMaterialFlow(){if($('materialactions'))return;let style=document.createElement('style');style.textContent='#materialactions{display:flex;gap:7px;margin:8px 0}.scan-backdrop{position:fixed;inset:0;background:rgba(2,6,23,.28);z-index:60;opacity:0;pointer-events:none;transition:opacity .18s}.scan-backdrop.open{opacity:1;pointer-events:auto}.scan-drawer{position:absolute;left:270px;top:72px;bottom:20px;width:min(680px,calc(100vw - 310px));background:#172033;border:1px solid #3b4960;border-left:3px solid #38bdf8;border-radius:0 12px 12px 0;box-shadow:12px 16px 45px rgba(0,0,0,.45);transform:translateX(-34px);opacity:0;transition:transform .22s ease,opacity .18s;display:flex;flex-direction:column}.scan-backdrop.open .scan-drawer{transform:translateX(0);opacity:1}.scan-drawer-head{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid #334155}.scan-drawer-body{overflow:auto;padding:12px 16px}.scan-drawer .file-card{border:1px solid #334155;border-radius:8px;padding:10px;margin:9px 0;background:#111827;line-height:1.5}.scan-drawer .file-card b{word-break:break-word}@media(max-width:760px){.scan-drawer{left:0;top:0;bottom:0;width:min(94vw,680px);border-radius:0 12px 12px 0}}';document.head.append(style);let tree=$('targettree'),confirm=document.querySelector('button[onclick="analyzeTarget()"]');let actions=document.createElement('div');actions.id='materialactions';confirm.id='confirmmaterials';confirm.textContent=t('materials.confirm_selected');let report=document.createElement('button');report.id='viewscanreport';report.className='ghost';report.disabled=true;report.textContent=t('scan.report');report.onclick=openScanReport;actions.append(confirm,report);tree.insertAdjacentElement('afterend',actions);$('scanreport').style.display='none';let backdrop=document.createElement('div');backdrop.id='scanbackdrop';backdrop.className='scan-backdrop';backdrop.innerHTML='<section class="scan-drawer" role="dialog" aria-modal="true" aria-label="'+escAttr(t('scan.report.title'))+'"><div class="scan-drawer-head"><div><b>'+esc(t('scan.report.title'))+'</b><div class="muted">'+esc(t('scan.report.local'))+'</div></div><button class="ghost" onclick="closeScanReport()">×</button></div><div id="scanreportbody" class="scan-drawer-body"></div></section>';backdrop.addEventListener('click',e=>{if(e.target===backdrop)closeScanReport()});document.body.append(backdrop);document.addEventListener('keydown',e=>{if(e.key==='Escape')closeScanReport()});updateMaterialFlowButtons();localizeMaterialFlowControls()}
async function openScanReport(){ensureMaterialFlow();
  // The report of the last scan lives only in this page; after a reload rebuild it from the local index.
  if(!lastScanReport){try{let x=await api('/api/scan/report');if(x?.files?.length)setScanReportAvailable(x)}catch(e){}}
  if(lastScanReport)renderScanDrawer(lastScanReport);else $('scanreportbody').innerHTML='<div class="muted">'+t('scan.report.none')+'</div>'+cacheAuditSection(true);
  $('scanbackdrop').classList.add('open');loadCacheAudit()}
function closeScanReport(){$('scanbackdrop')?.classList.remove('open')}
async function loadCacheAudit(){let host=$('cacheaudit');if(!host)return;try{renderCacheAudit(await api('/api/cache/audit'))}catch(e){setUIMessage(host,e.uiMessage||{text:e.message},'error')}}
async function rebuildCachedFile(id){if(!await appConfirm(t('cache.rebuild_file_confirm')))return;try{let x=await api('/api/cache/file/rebuild',{method:'POST',body:JSON.stringify({document_id:id,confirmed:true})});setUIMessage($('coveragestatus'),x);renderCacheAudit(x.audit)}catch(e){setUIMessage($('cacheaudit'),e.uiMessage||{text:e.message},'error')}}
async function rebuildDossier(){if(!await appConfirm(rt('dossier.confirm')))return;let host=$('cacheaudit');let button=host?.querySelector('button[onclick="rebuildDossier()"]');if(button)button.disabled=true;let operation=beginOperation();setUIMessage($('coveragestatus'),{message_key:'dossier.working'});try{let x=await api('/api/cache/dossier/rebuild',{method:'POST',body:JSON.stringify({confirmed:true,request_id:operation.id})});setUIMessage($('coveragestatus'),x);renderCacheAudit(x.audit);renderStatus(await api('/api/status'))}catch(e){setUIMessage($('coveragestatus'),[{message_key:'dossier.failed'},{text:e.message}],'error');if(host)setUIMessage(host,[{message_key:'dossier.failed'},{text:e.message}],'error')}finally{endOperation(operation);if(button)button.disabled=false}}
async function clearSummaryCaches(){if(!await appConfirm(t('cache.clear_confirm')))return;try{let x=await api('/api/cache/clear',{method:'POST',body:JSON.stringify({confirmed:true})});setUIMessage($('coveragestatus'),x);renderCacheAudit(x.audit)}catch(e){setUIMessage($('cacheaudit'),e.uiMessage||{text:e.message},'error')}}
// These renderers deliberately receive data, never pre-rendered text.  This
// makes a language switch deterministic even after a scan or cache view is open.
function renderStatusForLanguage(s){let tokens=usageNumber(s.input_tokens)+' / '+usageNumber(s.output_tokens);if(s.usage_complete===false)tokens+=' · '+t('usage.known_subtotal')+': '+usageNumber(s.known_input_tokens)+' / '+usageNumber(s.known_output_tokens);let cost=usageCost({cost_usd:s.cost,known_cost_usd:s.known_cost_usd,unpriced_detail:s.unpriced_detail});$('status').innerHTML=`<b>${t('status.section_title')}</b><br>${t('status.model')}${P('：')}<b>${esc(s.model)}</b><br>${t('status.session')}${P('：')}${esc(s.session_name||'default')}<br>${t('status.documents')}${P('：')}${t('status.items',{count:s.documents})}<br>${t('status.requests')}${P('：')}${esc(s.requests)}<br>${t('status.tokens')}${P('：')}${tokens}<br>${t('status.cost')}${P('：')}${cost}${s.unpriced_requests?' · '+t('usage.partial',{count:s.unpriced_requests}):''}<br>${pricingSourceText(s.pricing_source)}<br>${s.data_folder?'<span class="muted">'+t('status.data_folder')+P('：')+'<span class="ui-path">'+esc(s.data_folder)+'</span></span><br>':''}${s.bg_context?'<span class="ok">'+t('status.assembly_mode')+''+P('：')+''+esc(s.bg_context.codebook_name)+'</span>':t('status.normal_mode')}`;refreshAppChrome();refreshContextPanel()}
function renderUsageDetailForLanguage(u,model){if(!u)return;let gemini=/gemini/i.test(model||'')||Number(u.gemini_thinking)>0;$('usagedetail').innerHTML=`<b>${t('usage.section_title')}</b><br>${t('usage.actual_model')}${P('：')}<b>${esc(model||'—')}</b><br>${t('usage.input_output_total')}${P('：')}${usageNumber(u.input)} / ${usageNumber(u.output)} / ${usageNumber(u.total)}${u.usage_complete===false?' · '+t('usage.known_subtotal')+': '+usageNumber(u.known_input)+' / '+usageNumber(u.known_output):''}<br>${t('usage.reasoning')}${P('：')}${usageNumber(u.reasoning)}${gemini?' '+P('｜')+' '+t('usage.gemini_thinking')+''+P('：')+''+usageNumber(u.gemini_thinking):''}<br>${t('usage.claude_cache')}${P('：')}${usageNumber(u.cache_read)} / ${usageNumber(u.cache_write)}<br>${t('usage.estimate')}${P('：')}${usageCost(u)}`}
function renderEvidenceSourcesForLanguage(sources,dfcEvidence){let normal=(sources||[]).map(s=>`<div class="card"><b>${esc(s.label||s.name||t('model.unknown_source'))}</b><br>${s.visual?'<span class="chip">'+t('evidence.visual')+'</span>':''}</div>`).join('');let dfc=(dfcEvidence||[]).map(d=>{let parts=(d.segments_used||[]).join(''+P('、')+'')||'—';return `<div class="card"><b>DFC Struktur</b><br>${esc(d.name||'—')}<br><span class="chip">OCR${P('：')}${esc(stateCopy(d.ocr_status))}</span><span class="chip">${t('dfc.segment_info',{segments:esc(parts),total:esc(d.segments_total||0)})}</span></div>`}).join('');$('sources').innerHTML=(dfc+normal)||t('evidence.none')}
function renderCompareSlotsForLanguage(){let host=$('comparemodels');host.innerHTML=compareSlots.map((slot,index)=>{let options='<option value="">'+t('compare.select_model')+'</option>'+compareOptions.map(([value,label])=>'<option value="'+escAttr(value)+'" '+(slot.value===value?'selected':'')+'>'+esc(label)+'</option>').join('')+'<option value="__custom__" '+(slot.value==='__custom__'?'selected':'')+'>'+t('model.other')+'</option>';return '<div class="field"><label>'+t('compare.model_number',{index:index+1})+'</label><div class="row"><select id="cmpsel'+index+'" onchange="changeCompareModel('+index+')">'+options+'</select>'+(index>0?'<button class="ghost" onclick="removeCompareModel('+index+')">×</button>':'')+'</div>'+(slot.value==='__custom__'?'<input id="cmpcustom'+index+'" value="'+escAttr(slot.custom||'')+'" placeholder="'+t('model.id_placeholder')+'" oninput="compareSlots['+index+'].custom=this.value">':'')+'</div>'}).join('');let add=$('addcompare');add.disabled=compareSlots.length>=4;add.textContent=compareSlots.length>=4?t('compare.maximum'):t('compare.add');if(compareSlots.length>=4)setUIMessage($('comparestatus'),{message_key:'compare.maximum'})}
function renderSessionRowsForLanguage(items,append){let list=$('sessionlist');if(!list)return;if(!append)list.innerHTML='';for(let item of items){let row=document.createElement('div');row.className='session-row'+(item.name===currentSessionName?' active':'');row.onclick=()=>openSessionByName(item.name);let title=document.createElement('span');title.className='session-title';title.textContent=item.title_key?t(item.title_key):item.title;row.append(title);if(item.pinned){let pin=document.createElement('span');pin.className='session-pin';pin.textContent='●';pin.title=t('session.pin_title');row.append(pin)}let more=document.createElement('button');more.className='session-more';more.textContent='•••';more.title=t('session.more_title');more.onclick=e=>{e.stopPropagation();openSessionMenu(e,item)};row.append(more);list.append(row)}if(sessionLoading){let loading=document.createElement('div');loading.id='sessionloading';loading.className='session-loading';loading.textContent=t('session.loading');list.append(loading)}}
function openSessionMenuForLanguage(event,item){closeSessionMenu();let menu=document.createElement('div');menu.id='sessionmenu';menu.className='session-menu';let rect=event.currentTarget.getBoundingClientRect();menu.style.left=Math.min(window.innerWidth-145,rect.right+6)+'px';menu.style.top=rect.top+'px';menu.innerHTML='<button data-action="rename">'+t('actions.rename_full')+'</button><button data-action="pin">'+t(item.pinned?'session.unpin':'session.pin')+'</button><button class="delete" data-action="delete">'+t('actions.delete')+'</button>';menu.onclick=async e=>{let action=e.target.dataset.action;if(!action)return;if(action==='rename')await renameSession(item.name);if(action==='pin')await pinSession(item);if(action==='delete')await deleteSession(item.name);closeSessionMenu()};document.body.append(menu)}
function renderCoverageReportForLanguage(x){
  if(!x||!x.files){setUIMessage($('coveragestatus'),{message_key:'coverage.auto_hint'});return}
  if(x.current_selection===false){setUIMessage($('coveragestatus'),{message_key:'coverage.selection_changed'},'muted');return}
  let done=x.files.filter(f=>f.complete).length;
  let details=x.files.map(f=>{let pages=f.pages_total?t('coverage.pages')+P(''+P('：')+'')+t('coverage.read_pages',{pages:(f.pages_read||[]).join(P(''+P('、')+''))||'—'})+((f.pages_unread||[]).length?P(''+P('；')+'')+t('coverage.unread_pages',{pages:f.pages_unread.join(P(''+P('、')+''))}):''):t('coverage.no_pages');let dfc=f.dfc_structure?' · <span class="chip">'+t('coverage.dfc',{status:esc(stateCopy(f.dfc_structure.ocr_status)),count:esc(f.dfc_structure.segments_total||0)})+'</span>':'';let kind=f.kind_model||f.kind_guess?' · <span class="chip">'+t('coverage.kind',{kind:kindCopy(f.kind_model||f.kind_guess)})+' '+t(f.kind_model?'coverage.kind_model':'coverage.kind_local')+'</span>':'';let reasons=Object.keys(f.page_reasons||{}).length?'<br><span class="muted">'+t('coverage.page_reasons')+P('：')+esc(reasonsCopy(f.page_reasons))+(f.bom_found===false?' · '+t('coverage.no_bom'):'')+'</span>':'';let images=(f.images_read||[]).length?' · <span class="chip">'+t('coverage.images',{count:f.images_read.length})+'</span>':'';if(f.images_fallback)images+=' · <span class="chip">'+t('coverage.images_fallback')+'</span>';if((f.images_skipped||[]).length)images+=' · <span class="chip">'+t('coverage.images_skipped',{count:f.images_skipped.length})+'</span>';let cache=f.cache_status==='reused'?' · <span class="chip">'+t('coverage.reused_summary')+'</span>':f.cache_status==='created'?' · <span class="chip">'+t('coverage.new_pre_read')+'</span>':'';return `<br>${f.complete?'✓':'✕'} ${esc(f.name)}${P(''+P('：')+'')}${t('coverage.text_groups',{done:f.text_groups_processed,total:f.text_groups_total})} · ${esc(scopeCopy(f))} · ${esc(pages)}${kind}${images}${cache}${dfc}${f.failures?.length?P(''+P('（')+'')+esc((f.failure_messages||f.failures).map(uiCopy).join('; '))+P(''+P('）')+''):''}${reasons}`}).join('');
  let dossier=x.bg_dossier?.ready?' · <span class="chip">'+t('coverage.dossier_ready')+'</span>':' · <span class="chip">'+t('coverage.dossier_pending')+'</span>';
  $('coveragestatus').innerHTML=(x.complete?'<span class="ok">'+t('coverage.ready')+P(''+P('：')+'').trimEnd()+'</span>':'<span class="error">'+t('coverage.incomplete')+P(''+P('：')+'').trimEnd()+'</span>')+' '+t('coverage.overview',{done,total:x.files.length,reused:x.reused_files||0,created:x.created_files||0,calls:x.model_calls||0})+(x.retry_calls?' · <span class="chip">'+t('coverage.retries',{calls:x.retry_calls,limit:x.retry_limit})+'</span>':'')+dossier+details;
}
function renderScanDrawerForLanguage(x){
  let files=(x.files||[]).map(f=>{let index=f.index_cache_status==='reused'?t('scan.index.reused'):f.index_cache_status==='changed'?t('scan.index.changed'):f.index_cache_status==='new'?t('scan.index.created'):'—';return `<article class="file-card"><b>${esc(f.name)}</b><br><span class="muted">${esc(roleCopy(f.material_role_label))} · ${(Number(f.bytes)/1024/1024).toFixed(1)} MB<br>${t('scan.report.chunks',{count:f.chunks})} · ${index}${f.pages_total?'<br>'+t('scan.report.pages',{pages:f.pages_total,no_text:f.pages_no_text||0})+' · '+(f.plan_scope==='长文件挑页预读'?t('scan.report.plan_selected',{read:f.plan_read,total:f.pages_total})+(f.bom_found?'':' · '+t('coverage.no_bom')):t('scan.report.plan_full')):''}${f.kind_guess?'<br>'+t('coverage.kind',{kind:kindCopy(f.kind_guess)})+' '+t('coverage.kind_local'):''}${f.chunk_limit_reached?'<br><span class="error">'+t('scan.report.chunk_limit')+'</span>':''}</span></article>`}).join('')||'<div class="muted">'+t('scan.report.none')+'</div>';
  let skipped=x.skipped_count?`<article class="file-card error"><b>${t('scan.report.skipped',{count:x.skipped_count})}</b><br><span class="muted">${x.skipped.map(esc).join('<br>')}${x.skipped_count>x.skipped.length?'<br>'+t('scan.report.more_failures'):''}</span></article>`:'';
  $('scanreportbody').innerHTML='<div class="muted">'+t('scan.report.added',{count:x.sources||0})+'</div>'+files+skipped+cacheAuditSection();
}
function cacheAuditSection(open){return '<details id="cacheauditpanel" class="file-card"'+(open?' open':'')+' ontoggle="if(this.open)loadCacheAudit()"><summary><b>'+t('scan.report.cache')+'</b></summary><div class="muted" style="margin:7px 0">'+t('scan.report.cache_detail')+'</div><div id="cacheaudit" class="list muted">'+t('scan.report.cache_loading')+'</div></details>'}
// "Open detailed cache audit": works without a scan report from this page session.
function openAuditDetail(){closeContextDrawer();ensureMaterialFlow();if(lastScanReport)renderScanDrawer(lastScanReport);else $('scanreportbody').innerHTML=cacheAuditSection(true);let panel=$('cacheauditpanel');if(panel)panel.open=true;$('scanbackdrop').classList.add('open');loadCacheAudit()}
function renderCacheAuditForLanguage(x){
  let host=$('cacheaudit');if(!host)return;
  if(!x.files?.length){host.textContent=t('material.none');return}
  if(!x.files.some(f=>(f.summary_entries||[]).length)){host.innerHTML='<div class="muted">'+t('material.cache_empty')+'</div>';return}
  let dossier=x.dossier?.ready?t('cache.dossier_ready',{model:esc(x.dossier.model||'—')}):t('cache.dossier_missing');
  let files=x.files.map(f=>{let summaries=(f.summary_entries||[]).map(s=>`${esc(s.model||'—')} · ${t(s.full?'cache.full':'cache.default_scope')} · ${t(s.complete?'cache.complete':'cache.incomplete')}`).join('<br>')||t('cache.no_summary');let read=(f.summary_entries||[]).length?'<br><button class="ghost" data-document-id="'+escAttr(f.id)+'" onclick="rebuildCachedFile(this.dataset.documentId)">'+t('cache.rebuild_file')+'</button>':'';return `<div class="card"><b>${esc(f.name)}</b><br><span class="muted">${t('cache.index')}${P('：')}${esc(({reused:t('scan.index.reused'),changed:t('scan.index.changed'),new:t('scan.index.created')})[f.index_status]||stateCopy(f.index_status))} · OCR${P('：')}${esc(stateCopy(f.ocr_status))}<br>${t('cache.summary')}${P('：')}${summaries}</span>${read}</div>`}).join('');
  host.innerHTML='<div class="muted">'+dossier+(x.selection_current?'':''+P('；')+''+t('cache.scope_changed'))+'</div><div class="row"><button class="ghost" onclick="rebuildDossier()">'+t('cache.rebuild_dossier')+'</button><button class="ghost" onclick="clearSummaryCaches()">'+t('cache.clear')+'</button></div>'+files;
}
// Keep the last data payload, then redraw it with the active language.  The
// renderers remain the single source of HTML for both fresh API data and a UI
// language switch.
function renderCoverageReport(x){lastCoverageReport=x;return renderCoverageReportForLanguage(x)}
function renderScanDrawer(x){return renderScanDrawerForLanguage(x)}
function renderCacheAudit(x){lastCacheAudit=x;return renderCacheAuditForLanguage(x)}
function renderStatus(s){lastStatusSnapshot=s;let result=renderStatusForLanguage(s);renderScopeBar();refreshEmptyChat();return result}
function renderUsageDetail(u,model){if(u)lastUsageSnapshot={usage:u,model};return renderUsageDetailForLanguage(u,model)}
let lastSourcesSnapshot=null;
function renderEvidenceSources(sources,dfcEvidence){lastSourcesSnapshot={sources,dfc:dfcEvidence};return renderEvidenceSourcesForLanguage(sources,dfcEvidence)}
function renderCompareSlots(){return renderCompareSlotsForLanguage()}
function renderSessionRows(items,append){if(!append)lastSessionRows=[];lastSessionRows.push(...items);return renderSessionRowsForLanguage(items,append)}
function openSessionMenu(event,item){return openSessionMenuForLanguage(event,item)}
async function pickFolderForTree(){await pick('folder','targetpath');if($('targetpath').value)loadTargetTree()}
function treeFileCount(){return [...$('targettree').querySelectorAll('input.tree-file:checked')].length}
function refreshFolderState(folder){let files=[...folder.querySelectorAll('input.tree-file:not(:disabled)')];let box=folder.querySelector(':scope > summary input.tree-folder');if(!box||!files.length)return;let checked=files.filter(x=>x.checked).length;box.checked=checked===files.length;box.indeterminate=checked>0&&checked<files.length}
function refreshAllFolderStates(){[...$('targettree').querySelectorAll('details')].reverse().forEach(refreshFolderState);updateTreeStatus()}
function recommendedTreePaths(node,paths=[]){if(node.type==='file'){if(node.recommended)paths.push(node.relative);return paths}(node.children||[]).forEach(child=>recommendedTreePaths(child,paths));return paths}
// The server returns data and stable identifiers; the browser owns localized
// presentation.  Keeping the payload lets a language switch redraw the same
// selection without another folder read or a change to selection semantics.
function localizeMaterialFlowControls(){
  let confirm=$('confirmmaterials'),report=$('viewscanreport'),backdrop=$('scanbackdrop');
  if(confirm&&!busy)confirm.textContent=t('materials.confirm_selected');
  if(report)report.textContent=t('scan.report');
  if(backdrop){
    backdrop.setAttribute('aria-label',t('scan.report.title'));
    backdrop.querySelector('.scan-drawer')?.setAttribute('aria-label',t('scan.report.title'));
    let title=backdrop.querySelector('.scan-drawer-head b'),note=backdrop.querySelector('.scan-drawer-head .muted');
    if(title)title.textContent=t('scan.report.title');
    if(note)note.textContent=t('scan.report.local');
  }
}
function updateMaterialFlowButtonsForLanguage(){
  let confirm=$('confirmmaterials'),report=$('viewscanreport');
  if(confirm)confirm.disabled=treeFileCount()===0&&!singleFileTarget();
  if(report){report.disabled=!lastScanReport&&!lastDocumentsSnapshot?.length;report.textContent=t('scan.report')}
}
function setScanReportAvailableForLanguage(report){lastScanReport=report||null;updateMaterialFlowButtonsForLanguage()}
function clearTargetTreeForLanguage(){
  savedTargetSelection=new Set();treeRestoreNote='';scannedSelection='';lastTargetTreePayload=null;setScanReportAvailableForLanguage(null);
  setUIMessage($('targettree'),{message_key:'tree.placeholder'});$('targettree').classList.add('muted');$('treestatus').textContent='';updateMaterialFlowButtonsForLanguage();
}
function updateTreeStatusForLanguage(){
  let count=treeFileCount(),signature=selectedTargetPaths().sort().join('|');
  if(scannedSelection&&signature!==scannedSelection)setScanReportAvailableForLanguage(null);
  $('treestatus').textContent=(count?t('tree.selected',{count}):t('tree.none'))+(treeRestoreNote?' '+treeRestoreNote:'');
  updateMaterialFlowButtonsForLanguage();
}
function makeTreeNodeForLanguage(node,depth=0){
  if(node.type==='folder'){
    let details=document.createElement('details');details.open=depth<1;let summary=document.createElement('summary');let box=document.createElement('input');
    box.type='checkbox';box.className='tree-folder';box.addEventListener('click',e=>e.stopPropagation());box.addEventListener('change',()=>{materialDraftDirty=true;details.querySelectorAll('input.tree-file:not(:disabled)').forEach(x=>x.checked=box.checked);refreshAllFolderStates()});
    let label=document.createElement('label');label.textContent='📁 '+node.name;summary.append(box,label);details.append(summary);
    let children=document.createElement('div');children.className='tree-children';(node.children||[]).forEach(child=>children.append(makeTreeNodeForLanguage(child,depth+1)));details.append(children);return details;
  }
  let row=document.createElement('div');row.className='tree-file'+(node.supported?'':' unsupported');let box=document.createElement('input');
  box.type='checkbox';box.className='tree-file';box.dataset.path=node.path;box.checked=!!node.supported&&savedTargetSelection.has(node.relative);box.disabled=!node.supported;box.addEventListener('change',()=>{materialDraftDirty=true;refreshAllFolderStates()});
  let label=document.createElement('label'),role=node.material_role_label?` · ${roleCopy(node.material_role_label)}`:'',size=(node.bytes/1024/1024).toFixed(node.bytes<1024*1024?2:1);
  label.textContent='📄 '+node.name+(node.supported?` · ${size} MB${role}${node.recommended?'':' · '+t('tree.not_recommended')}`:` · ${t('tree.unsupported')}${role}`);row.append(box,label);return row;
}
function renderTargetTreeForLanguage(x){
  lastTargetTreePayload=x;let host=$('targettree');host.classList.remove('muted');host.innerHTML='';host.append(makeTreeNodeForLanguage(x.tree));refreshAllFolderStates();
  if(x.truncated)setUIMessage($('treestatus'),{message_key:'tree.truncated'},'error');
}
function captureTargetTreeSelection(){
  if(!lastTargetTreePayload?.tree)return;
  let selected=new Set(selectedTargetPaths()),relative=new Set();
  (function visit(node){if(node.type==='file'){if(selected.has(node.path))relative.add(node.relative);return}(node.children||[]).forEach(visit)})(lastTargetTreePayload.tree);
  savedTargetSelection=relative;
}
async function loadTargetTreeForLanguage(){
  let target=$('targetpath').value.trim();
  if(!target){setUIMessage($('treestatus'),{message_key:'tree.path_required'},'error');return}
  try{
    setUIMessage($('treestatus'),{message_key:'tree.loading'});let x=await api('/api/target-tree?target='+encodeURIComponent(target));savedTargetSelection=new Set(x.saved_selection||[]);
    let notes=[];
    if(savedTargetSelection.size)notes.push(t('tree.restored',{count:savedTargetSelection.size}));
    else{savedTargetSelection=new Set(recommendedTreePaths(x.tree));notes.push(t('tree.default_selection',{count:savedTargetSelection.size}));}
    if(x.changed_saved_files)notes.push(t('tree.changed',{count:x.changed_saved_files}));
    if(x.missing_saved_files)notes.push(t('tree.missing',{count:x.missing_saved_files}));
    treeRestoreNote=notes.join(' ');renderTargetTreeForLanguage(x);
  }catch(e){setUIMessage($('treestatus'),e.uiMessage||{text:e.message},'error')}
}
// Compatibility assignments ensure every old event handler uses the localized
// renderers while preserving the original public function names.
function updateMaterialFlowButtons(...args){return updateMaterialFlowButtonsForLanguage(...args)}
function setScanReportAvailable(...args){return setScanReportAvailableForLanguage(...args)}
function clearTargetTree(...args){return clearTargetTreeForLanguage(...args)}
function updateTreeStatus(...args){return updateTreeStatusForLanguage(...args)}
function makeTreeNode(...args){return makeTreeNodeForLanguage(...args)}
function loadTargetTree(...args){return loadTargetTreeForLanguage(...args)}
function ensureMaterialFlow(){createMaterialFlow();localizeMaterialFlowControls()}
function selectedTargetPaths(){return [...$('targettree').querySelectorAll('input.tree-file:checked')].map(x=>x.dataset.path)}
async function analyzeTarget(){if(!await allowRuleDraftTransition())return;if($('contexttargetpath'))contextSyncTarget();if($('chat').querySelector('.message.user')&&!await appConfirm(t('materials.replace_confirm')))return;let confirm=$('confirmmaterials');if(confirm){confirm.disabled=true;confirm.textContent=rt('scan.reading')}try{let target=$('targetpath').value.trim();let selected=selectedTargetPaths();if($('targettree').querySelector('.tree-file')&&!selected.length)throw Error(t('materials.selection_required'));setUIMessage($('bgstatus'),{message_key:'materials.scan_started',params:{count:selected.length||1}});let x=await api('/api/target',{method:'POST',body:JSON.stringify({target,codebook:$('codebook').value,selected_paths:selected})});scannedSelection=selected.slice().sort().join('|');materialDraftDirty=false;clearResultPanels();await loadHistory();renderStatus(x.status);setUIMessage($('bgstatus'),[{message_key:'materials.scan_done'},{message_key:x.classification?'materials.confirmed_bg':'materials.confirmed_normal',params:{kind:tr(x.target_kind),count:x.sources}}],'ok');renderScanReport(x);setUIMessage($('coveragestatus'),{message_key:'material.updated'});loadDocs();openScanReport()}catch(e){setUIMessage($('bgstatus'),e.uiMessage||{text:e.message},'error')}finally{if(confirm)confirm.textContent=t('materials.confirm_selected');updateMaterialFlowButtons()}}
async function prepareCoverage(full=false){if(busy){setUIMessage($('coveragestatus'),{message_key:'coverage.busy'},'error');return}busy=true;let readAll=$('contextreadall');if(readAll)readAll.disabled=true;let operation=beginOperation();setUIMessage($('coveragestatus'),{message_key:full?'coverage.preparing_full':'coverage.preparing'});try{let x=await api('/api/coverage',{method:'POST',body:JSON.stringify({full,request_id:operation.id})});renderCoverageReport(x);renderStatus(await api('/api/status'))}catch(e){setUIMessage($('coveragestatus'),{message_key:'error.operation_failed',params:{detail:e.uiMessage||{text:e.message}}},'error')}finally{endOperation(operation);busy=false;if(readAll)readAll.disabled=false}}
async function clearBg(){if(!await allowRuleDraftTransition())return;try{renderStatus(await api('/api/bg',{method:'DELETE'}));setUIMessage($('bgstatus'),{message_key:'bg.exited'})}catch(e){$('bgstatus').textContent=e.message}}
const compareOptions=[['claude-haiku-5-5','Claude Haiku 5.5'],['claude-sonnet-5-5','Claude Sonnet 5.5'],['claude-opus-5','Claude Opus 5'],['gemini-3.5-flash-lite','Gemini 3.5 Flash-Lite'],['gemini-2.5-pro','Gemini 2.5 Pro'],['gemini-2.5-flash','Gemini 2.5 Flash'],['deepseek-r1-0528-maas','DeepSeek R1 (0528)'],['llama-3.3-70b-instruct-maas','Llama 3.3 70B'],['glm-5-maas','GLM-5']];
function changeCompareModel(index){let select=$('cmpsel'+index);compareSlots[index].value=select.value;if(select.value!=='__custom__')compareSlots[index].custom='';renderCompareSlots();if(select.value==='__custom__')setTimeout(()=>$('cmpcustom'+index).focus(),0)}
function addCompareModel(){if(compareSlots.length>=4){setUIMessage($('comparestatus'),{message_key:'compare.maximum'});return}compareSlots.push({value:'',custom:''});renderCompareSlots();$('cmpsel'+(compareSlots.length-1)).focus()}
function removeCompareModel(index){compareSlots.splice(index,1);renderCompareSlots();$('comparestatus').textContent=''}
function selectedCompareModels(){return compareSlots.map((slot,index)=>slot.value==='__custom__'?$('cmpcustom'+index).value.trim():slot.value).filter(Boolean)}
function renderComparisonForLanguage(record){
  $('comparison-result')?.remove();let x=record.data,box=document.createElement('section');box.id='comparison-result';box.className='comparison';
  box.innerHTML='<div class="message assistant"><b>'+t('compare.title')+'</b><br>'+t('compare.question')+''+P('：')+''+esc(record.question)+'<br><span class="muted">'+t('compare.same_evidence')+''+P('：')+''+(x.sources||[]).map(esc).join(' · ')+'</span></div><div class="comparison-grid"></div>';
  let grid=box.querySelector('.comparison-grid');for(let r of x.results||[]){let card=document.createElement('article');card.className='card';if(!r.ok){card.innerHTML='<b>'+esc(r.requested_model)+'</b><p class="error">'+t('compare.request_failed')+'</p><div class="muted">'+esc(r.error_message?uiCopy(r.error_message):r.error||t('compare.unknown_error'))+'</div>';grid.append(card);continue}let u=r.usage||{},cost=usageCost(u),classification=r.classification?'<div class="chip">'+t('classification.verified')+''+P('：')+''+esc(r.classification.label)+' · '+esc(r.classification.confidence)+'</div>':'';card.innerHTML='<b>'+esc(r.model_response)+'</b>'+(r.model_response!==r.requested_model?'<div class="muted">'+t('compare.requested_model')+''+P('：')+''+esc(r.requested_model)+'</div>':'')+'<div class="muted ok">'+t('compare.success')+' · Token '+usageNumber(u.input)+' / '+usageNumber(u.output)+' · '+cost+'</div>'+classification+'<hr><div class="answer"></div>'+(r.notices?.length?'<div class="muted">'+(r.notice_messages||r.notices).map(value=>esc(uiCopy(value))).join('<br>')+'</div>':'');card.querySelector('.answer').textContent=r.answer;grid.append(card)}$('chat').append(box);
}
async function compareModels(){if(busy)return;if(lastStatusSnapshot?.context_issue){uiMessageNode({message_key:'context.reconfirm'});return;}if(materialDraftDirty){uiMessageNode({message_key:'materials.reconfirm'});return;}let q=$('question').value.trim()||lastQuestion;if(!q){setUIMessage($('comparestatus'),{message_key:'compare.question_required'},'error');return}let models=selectedCompareModels();if(models.length<2||models.length>4||new Set(models).size!==models.length){setUIMessage($('comparestatus'),{message_key:'compare.models_required'},'error');return}busy=true;lastQuestion=q;let operation=beginOperation();setUIMessage($('comparestatus'),{message_key:'compare.running',params:{count:models.length}});let wait=uiMessageNode({message_key:'compare.in_progress',params:{models:models.join(' · ')}});try{let x=await api('/api/compare',{method:'POST',body:JSON.stringify({question:q,models,request_id:operation.id})});wait.remove();lastComparison={question:q,data:x};renderComparisonForLanguage(lastComparison);renderStatus(x.usage);setUIMessage($('comparestatus'),{message_key:'compare.complete'},'ok')}catch(e){wait.uiData={message_key:'error.operation_failed',params:{detail:e.uiMessage||{text:e.message}}};wait.textContent=uiCopy(wait.uiData);wait.classList.add('error');setUIMessage($('comparestatus'),e.uiMessage||{text:e.message},'error')}finally{endOperation(operation);busy=false;$('chat').scrollTop=1e9}}
function processingCard(){let card=document.createElement('section');card.className='message assistant';card.style.border='1px solid #334155';card.innerHTML='<b data-process-title>'+rt('model.processing')+'</b><div class="muted" data-process-text>'+rt('model.connecting')+'</div><div style="height:7px;background:#0b1220;border-radius:8px;overflow:hidden;margin-top:9px"><div data-process-bar style="height:100%;width:4%;background:#38bdf8;transition:width .25s ease"></div></div>';$('chat').append(card);return registerUI(card,'processing',null)}
function updateProcessing(card,event){let text=card.querySelector('[data-process-text]'),bar=card.querySelector('[data-process-bar]');card.uiData=event;text.textContent=uiCopy(event)||rt('model.waiting');if(typeof event.percent==='number')bar.style.width=Math.max(4,Math.min(100,event.percent))+'%';if(event.phase==='complete'){card.style.borderColor='#22c55e';bar.style.background='#22c55e'}}
function showChatResult(x){let tag=scopeTag(x.scope,!!x.classification);if(tag)$('chat').append(tag);message(x.answer);if(x.classification)$('chat').append(classificationCard(x.classification));let summary=coverageSummaryCard(x.coverage_summary);if(summary)$('chat').append(summary);if(x.reasoning){let d=document.createElement('details');d.className='reason';d.innerHTML='<summary>'+t('model.reasoning')+'</summary><pre></pre>';d.querySelector('pre').textContent=x.reasoning;registerUI(d,'reasoning',x.reasoning);$('chat').append(d)}if(x.notices?.length){let data=x.notice_messages||x.notices;registerUI(message(data.map(uiCopy).join('\n'),'assistant'),'notices',data)}renderEvidenceSources(x.sources,x.dfc_evidence);$('changes').innerHTML=x.changes?.length?x.changes.map(c=>`<div class="card"><b>${esc(c.path)}</b><br>${esc(c.reason)}<pre class="diff">${esc(c.diff)}</pre></div>`).join('')+'<button data-plan-id="'+escAttr(x.plan_id||'')+'" onclick="apply(this.dataset.planId,this)">'+t('changes.apply')+'</button>':t('changes.none');if(!x.changes?.length)setUIMessage($('changes'),{message_key:'changes.none'});if(x.changes?.length){let review=$('changes').cloneNode(true);review.removeAttribute('id');review.className='message assistant change-plan';$('chat').append(review)}$('analysisexport').innerHTML=x.can_export_bg?'<button class="ghost" onclick="exportBgAnalysis()">'+t('export.assembly')+'</button>':t('export.assembly_unavailable');if(!x.can_export_bg)setUIMessage($('analysisexport'),{message_key:'export.assembly_unavailable'});renderUsageDetail(x.turn_usage,x.model_response);renderStatus(x.usage)}
let activeChat=null;
let activeOperation=null;
function beginOperation(){let operation={id:crypto.randomUUID().replaceAll('-',''),stopping:false};activeOperation=operation;$('cancelchat').disabled=false;return operation}
function endOperation(operation){if(activeOperation!==operation)return;activeOperation=null;if(!activeChat)$('cancelchat').disabled=true}
async function stopChat(){
  if(!activeChat&&activeOperation&&!activeOperation.stopping){
    activeOperation.stopping=true;$('cancelchat').disabled=true;
    try{await api('/api/operation/cancel',{method:'POST',body:JSON.stringify({request_id:activeOperation.id})})}catch{}
    return;
  }
  if(!activeChat||activeChat.stopping)return;
  activeChat.stopping=true;$('cancelchat').disabled=true;
  activeChat.controller.abort();
  if(activeChat.id)try{await api('/api/chat/cancel',{method:'POST',body:JSON.stringify({request_id:activeChat.id})})}catch{}
}
async function settleChat(task,wait){
  if(!task.id)return null;
  let failures=0;
  while(true){
    try{
      let response=await fetch('/api/chat/task/'+encodeURIComponent(task.id));
      if(response.status===404)return null;
      let status=await readApiResponse(response);
      if(status.done)return status;
      failures=0;
      updateProcessing(wait,{message_key:'stream.stopping'});
    }catch{if(++failures>=3)return null}
    await new Promise(resolve=>setTimeout(resolve,100));
  }
}
async function chat(options={}){
  let classify=!!options.classify&&!!lastStatusSnapshot?.bg_context;
  if(busy||(!classify&&!$('question').value.trim()))return;
  if(lastStatusSnapshot?.context_issue){message(t('context.reconfirm'));return}
  if(materialDraftDirty){message(t('materials.reconfirm'));return}
  busy=true;chatGeneration++;let task={controller:new AbortController(),id:crypto.randomUUID().replaceAll('-',''),stopping:false};activeChat=task;$('cancelchat').disabled=false;
  // The classify button sends a fixed request and keeps any draft in the input.
  let q;if(classify){q=t('classify.request');classifyRequestTag()}else{q=$('question').value;lastQuestion=q;$('question').value='';message(q,'user')}
  renderScopeBar();
  let wait=processingCard(),buffer='',result=null,error=null,preview=null,previewText=null,failureText='';
  function resetPreview(){preview?.remove();preview=null;previewText=null}
  function appendPreview(text){
    if(!preview){preview=message('');preview.classList.add('answer-preview');registerUI(preview,'preview',null);let label=document.createElement('div');label.className='muted';label.textContent=t('stream.preview');let body=document.createElement('div');body.className='preview-text';body.style.whiteSpace='pre-wrap';previewText=document.createTextNode('');body.append(previewText);preview.append(label,body)}
    previewText.appendData(text);
  }
  try{
    let response=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json','X-Workbench-Language':uiLanguage,...contextHeaders()},signal:task.controller.signal,body:JSON.stringify({question:q,request_id:task.id,require_classification:classify,focus_source_id:classify?'':scopeFocusDoc()?.id||''})});
    learnPageContext('/api/chat/stream','POST',response);
    if(!response.ok)await readApiResponse(response);
    let reader=response.body.getReader(),decoder=new TextDecoder();
    while(true){
      let part=await reader.read();if(part.done)break;
      buffer+=decoder.decode(part.value,{stream:true});
      let blocks=buffer.split('\n\n');buffer=blocks.pop();
      for(let block of blocks){
        let line=block.split('\n').find(item=>item.startsWith('data: '));if(!line)continue;
        let event=JSON.parse(line.slice(6));
        if(event.type==='start')task.id=event.request_id;
        else if(event.type==='progress')updateProcessing(wait,event);
        else if(event.type==='answer_reset')resetPreview();
        else if(event.type==='answer_delta')appendPreview(event.text);
        else if(event.type==='result')result=event.data;
        else if(event.type==='error'){error=event;throw Error(uiCopy(event)||event.message||t('model.failed'))}
      }
    }
    if(!result)throw Error(t('api.no_result'));
    resetPreview();updateProcessing(wait,{phase:'complete',message_key:'model.complete',percent:100});showChatResult(result);
  }catch(e){
    resetPreview();task.controller.abort();
    if(task.id)try{await api('/api/chat/cancel',{method:'POST',body:JSON.stringify({request_id:task.id})})}catch{}
    let code=task.stopping?'cancelled':error?.code;
    wait.uiData={message_key:code==='cancelled'?'stream.cancelled':code==='timeout'?'stream.timeout':code==='limit'?'stream.limit':'error.operation_failed',params:{detail:error?.message_key?error:e.uiMessage||{text:e.message}}};
    failureText=uiCopy(wait.uiData);
    wait.querySelector('[data-process-text]').textContent=failureText;
    if(code!=='cancelled')wait.classList.add('error');
  }finally{
    resetPreview();let status=await settleChat(task,wait);
    if(task.stopping)updateProcessing(wait,{message_key:status?.state==='completed'?'stream.completed':'stream.cancelled'});
    else if(failureText)wait.querySelector('[data-process-text]').textContent=failureText;
    activeChat=null;busy=false;$('cancelchat').disabled=true;renderScopeBar();$('chat').scrollTop=1e9;
  }
}
async function exportSession(){try{let x=await api('/api/export/session',{method:'POST'});setUIMessage($('sessionexport'),{message_key:'export.complete',params:{path:x.path}},'ok')}catch(e){setUIMessage($('sessionexport'),e.uiMessage||{text:e.message},'error')}}
async function exportBgAnalysis(){try{let x=await api('/api/export/bg-analysis',{method:'POST'});setUIMessage($('analysisexport'),{message_key:'export.complete',params:{path:x.path}},'ok')}catch(e){setUIMessage($('analysisexport'),e.uiMessage||{text:e.message},'error')}}
function esc(s){let e=document.createElement('div');e.textContent=s;return e.innerHTML}function escAttr(s){return esc(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;')}async function apply(planId,button){let review=button?.closest('.change-plan')||$('changes');if(!await appConfirm(t('changes.confirm')))return;try{let x=await api('/api/apply',{method:'POST',body:JSON.stringify({confirmed:true,plan_id:planId})});setUIMessage(review,{message_key:'apply.complete',params:{count:x.applied}},'ok');message(t('apply.message',{count:x.applied}))}catch(e){setUIMessage(review,e.uiMessage||{text:e.message},'error')}}

let materialDraftDirty=false;
function clearResultPanels(){lastSourcesSnapshot=null;lastUsageSnapshot=null;lastComparison=null;lastCoverageReport=null;lastCacheAudit=null;setUIMessage($('sources'),{message_key:'evidence.none'});setUIMessage($('changes'),{message_key:'changes.none'});setUIMessage($('analysisexport'),{message_key:'export.assembly_unavailable'});setUIMessage($('usagedetail'),{message_key:'usage.unavailable'});setUIMessage($('coveragestatus'),{message_key:'material.updated'});}
let ruleEditState=null;
function ruleEditorBinding(profile=lastCodebookWorkspaceProfile){
  return JSON.stringify([lastStatusSnapshot?.workspace,lastStatusSnapshot?.session_name,profile?.source_path,profile?.sha256,profile?.version]);
}
function captureRuleEditor(){
  let field=$('ruleeditor');if(!ruleEditState||!field)return;
  Object.assign(ruleEditState,{text:field.value,dirty:field.value!==ruleEditState.initialText,start:field.selectionStart,end:field.selectionEnd,direction:field.selectionDirection,scroll:field.scrollTop});
}
async function allowRuleDraftTransition(){
  captureRuleEditor();
  if(!ruleEditState)return true;
  if(ruleEditState.saving)return false;
  if(ruleEditState.dirty&&!await appConfirm(t('rules.discard_confirm')))return false;
  ruleEditState=null;return true;
}
function renderRuleEditor(){
  if(!ruleEditState)return;
  captureRuleEditor();
  if(!$('ruleeditor')){
    $('chat').className='chat codebook-workspace';$('composer').style.display='none';
    $('chat').innerHTML='<section class="workspace-inner"><h1 data-rule-copy="rules.edit"></h1><p data-rule-copy="rules.edit_help"></p><textarea id="ruleeditor" style="width:100%;min-height:380px"></textarea><div class="row"><button id="rulesave" onclick="saveCodebookDraft()" data-rule-copy="rules.save_draft"></button><button class="ghost" onclick="cancelRuleDraft()" data-rule-copy="rules.cancel"></button></div><div id="ruledirty" class="muted"></div><div id="ruleediterror" class="error"></div></section>';
    let field=$('ruleeditor');field.value=ruleEditState.text;field.setSelectionRange(ruleEditState.start,ruleEditState.end,ruleEditState.direction);field.scrollTop=ruleEditState.scroll;
    for(let event of ['input','select','keyup','click','blur','scroll'])field.addEventListener(event,()=>{captureRuleEditor();updateRuleEditorCopy()});
  }
  updateRuleEditorCopy();
}
function updateRuleEditorCopy(){
  if(!ruleEditState||!$('ruleeditor'))return;
  for(let node of $('chat').querySelectorAll('[data-rule-copy]'))node.textContent=t(node.dataset.ruleCopy);
  $('ruleeditor').setAttribute('aria-label',t('rules.edit'));
  $('ruledirty').textContent=t(ruleEditState.saving?'rules.saving':ruleEditState.dirty?'rules.unsaved':'rules.saved_copy');
  $('rulesave').disabled=!!ruleEditState.saving;
  $('ruleeditor').readOnly=!!ruleEditState.saving;
  $('ruleediterror').textContent=ruleEditState.error?uiCopy(ruleEditState.error):'';
}
function editCodebookDraft(){
  if(ruleEditState){renderRuleEditor();return}
  let profile=lastCodebookWorkspaceProfile;if(!profile)return;
  let text=JSON.stringify(profile.draft,null,2);
  ruleEditState={text,initialText:text,dirty:false,binding:ruleEditorBinding(profile),start:0,end:0,direction:'none',scroll:0,error:null,saving:false};
  renderRuleEditor();
}
async function cancelRuleDraft(){
  if(ruleEditState?.saving)return;
  if(!await allowRuleDraftTransition())return;
  showCodebookWorkspace(lastCodebookWorkspaceProfile);
}
async function saveCodebookDraft(){
  captureRuleEditor();let editing=ruleEditState;if(!editing||editing.saving)return;
  if(editing.binding!==ruleEditorBinding()){editing.error={message_key:'rules.context_changed'};updateRuleEditorCopy();return}
  let draft;try{draft=JSON.parse(editing.text)}catch(e){editing.error={message_key:'rules.invalid_json',params:{detail:e.message}};updateRuleEditorCopy();return}
  if(!await appConfirm(t('rules.save_confirm')))return;
  editing.saving=true;editing.error=null;updateRuleEditorCopy();
  try{
    let profile=await api('/api/codebook/edit',{method:'POST',body:JSON.stringify({draft,confirmed:true,profile_version:lastCodebookWorkspaceProfile?.version})});
    ruleEditState=null;renderCodebookStatus(profile);showCodebookWorkspace(profile);renderStatus(await api('/api/status'));
  }catch(e){editing.error=e.uiMessage||{message_key:'rules.save_failed',params:{detail:e.message}}}
  finally{editing.saving=false;updateRuleEditorCopy()}
}
window.addEventListener('beforeunload',event=>{captureRuleEditor();if(ruleEditState?.dirty){event.preventDefault();event.returnValue=''}});

