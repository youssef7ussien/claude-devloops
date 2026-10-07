(function(){
'use strict';
var doc=document,root=doc.documentElement;
root.classList.remove('no-js');root.classList.add('js');
function $(s,c){return (c||doc).querySelector(s)}
function $$(s,c){return Array.prototype.slice.call((c||doc).querySelectorAll(s))}
function el(tag,cls,text){var n=doc.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n}
function store(k,v){try{if(v===undefined)return localStorage.getItem('devloops-'+k);localStorage.setItem('devloops-'+k,v)}catch(e){return null}}
function icon(name){var s=doc.createElementNS('http://www.w3.org/2000/svg','svg');s.setAttribute('class','ic');
  s.setAttribute('aria-hidden','true');var u=doc.createElementNS('http://www.w3.org/2000/svg','use');
  u.setAttribute('href','#i-'+name);s.appendChild(u);return s}
function btn(label,opts){opts=opts||{};var b=el('button','btn'+(opts.cls?' '+opts.cls:''));b.type='button';
  if(opts.icon)b.appendChild(icon(opts.icon));if(label){if(opts.iconOnly){b.setAttribute('aria-label',label);b.title=label+(opts.key?' ('+opts.key+')':'')}
  else b.appendChild(doc.createTextNode(label))}if(opts.on)b.addEventListener('click',opts.on);return b}

/* --- theme ------------------------------------------------------------------------------------- */
function applyTheme(t){if(t)root.setAttribute('data-theme',t);else root.removeAttribute('data-theme')}
if(store('theme'))applyTheme(store('theme'));
$$('[data-action="theme"]').forEach(function(b){b.addEventListener('click',function(){
  var dark=root.getAttribute('data-theme')==='dark'||(!root.getAttribute('data-theme')&&
    window.matchMedia('(prefers-color-scheme: dark)').matches);
  var next=dark?'light':'dark';applyTheme(next);store('theme',next)})});

/* --- chart tooltips (unchanged behaviour) ------------------------------------------------------ */
var tip=$('#tip');
function showTip(n,x,y){tip.textContent=n.getAttribute('data-tip');tip.style.display='block';
  var w=tip.offsetWidth,h=tip.offsetHeight;tip.style.left=Math.min(x+14,innerWidth-w-8)+'px';
  tip.style.top=Math.max(8,y-h-10)+'px'}
function hideTip(){tip.style.display='none'}
function bindTips(scope){$$('[data-tip]',scope).forEach(function(n){
  n.addEventListener('mousemove',function(ev){showTip(n,ev.clientX,ev.clientY)});n.addEventListener('mouseleave',hideTip);
  n.addEventListener('focus',function(){var r=n.getBoundingClientRect();showTip(n,r.left,r.top)});n.addEventListener('blur',hideTip)})}

/* --- views and navigation ---------------------------------------------------------------------- */
var app=$('.app'),views=$$('.view'),crumb=$('[data-crumb]');
function showView(v,keepNav){views.forEach(function(x){x.classList.toggle('active',x===v)});
  $$('.nav a[data-view]').forEach(function(a){if(a.dataset.view===v.id)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')});
  if(crumb)crumb.textContent=v.dataset.title||v.id;if(!keepNav)app.classList.remove('nav-open')}
function route(id,push){
  var t=id&&doc.getElementById(id);
  if(!t){showView(views[0]);return}
  var src=t.closest('.call-src');if(src&&src!==t)t=src;
  if(t.classList.contains('file')||t.classList.contains('call-src')){
    var v0=$('.view.active')||views[0];showView(v0);openTarget(t);return}
  var v=t.classList.contains('view')?t:t.closest('.view');if(!v)return;
  showView(v);
  if(t!==v){var d=t.closest('details');while(d){d.open=true;d=d.parentElement.closest('details')}
    t.scrollIntoView({block:'start'})}else scrollTo(0,0);
  if(push)history.pushState(null,'','#'+id)}
doc.addEventListener('click',function(ev){
  var a=ev.target.closest('a[href^="#"]');if(!a||ev.defaultPrevented||ev.button||ev.metaKey||ev.ctrlKey)return;
  var id=decodeURIComponent(a.getAttribute('href').slice(1));if(!id||!doc.getElementById(id))return;
  ev.preventDefault();route(id,!isTarget(doc.getElementById(id)))});
addEventListener('popstate',function(){route(location.hash.slice(1))});
$$('[data-action="menu"]').forEach(function(b){b.addEventListener('click',function(){app.classList.toggle('nav-open')})});
app.addEventListener('click',function(ev){if(ev.target===app)app.classList.remove('nav-open')});

/* --- syntax highlighting ----------------------------------------------------------------------- */
var STR2=/"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'/y,NUM=/\b-?(?:0x[\da-f]+|\d+(?:\.\d+)?(?:e[+-]?\d+)?)\b/iy,WORD=/[A-Za-z_$][\w$]*/y;
function kw(words){return new RegExp('\\b(?:'+words.split(' ').join('|')+')\\b','y')}
var LANGS={
  json:[[/"(?:[^"\\\n]|\\.)*"(?=\s*:)/y,'key'],[/"(?:[^"\\\n]|\\.)*"/y,'str'],[/-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/y,'num'],
    [/\b(?:true|false|null)\b/y,'lit'],[/[{}\[\],:]/y,'pun']],
  python:[[/#.*/y,'com'],[/[rbfu]{0,2}("""[\s\S]*?"""|'''[\s\S]*?''')/iy,'str'],[/[rbfu]{0,2}(?:"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')/iy,'str'],
    [kw('def class return if elif else for while in import from as with try except finally raise pass break continue lambda yield not and or is global nonlocal async await assert del'),'kw'],
    [kw('True False None self cls'),'lit'],[/@[\w.]+/y,'kw'],[NUM,'num'],[WORD,null]],
  js:[[/\/\/.*/y,'com'],[/\/\*[\s\S]*?\*\//y,'com'],[/`(?:[^`\\]|\\[\s\S])*`/y,'str'],[STR2,'str'],
    [kw('const let var function return if else for while do switch case break continue new class extends import from export default try catch finally throw await async typeof instanceof in of yield this'),'kw'],
    [kw('true false null undefined NaN'),'lit'],[NUM,'num'],[WORD,null]],
  shell:[[/#.*/y,'com'],[STR2,'str'],[/\$\{?[\w@#?*!-]+\}?/y,'key'],[/(?:^|(?<=\s))--?[\w-]+/y,'kw'],
    [kw('if then else elif fi for in do done while case esac function export local return sudo cd'),'kw'],[NUM,'num'],[WORD,null]],
  yaml:[[/#.*/y,'com'],[/[\w.\/-]+(?=:(?:\s|$))/y,'key'],[STR2,'str'],[kw('true false null yes no on off'),'lit'],
    [NUM,'num'],[/^\s*-(?=\s)/my,'pun'],[WORD,null]],
  http:[[/^HTTP\/[\d.]+ \d+.*$/my,'head'],[/^(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) .*$/my,'head'],
    [/^[\w-]+(?=:)/my,'key'],[NUM,'num'],[WORD,null]],
  html:[[/<!--[\s\S]*?-->/y,'com'],[/<\/?[\w-]+/y,'kw'],[/\/?>/y,'kw'],[/[\w-]+(?==)/y,'key'],[STR2,'str'],[WORD,null]],
  css:[[/\/\*[\s\S]*?\*\//y,'com'],[/[\w-]+(?=\s*:[^{]*[;}])/y,'key'],[/#[\da-f]{3,8}\b/iy,'num'],[NUM,'num'],[STR2,'str'],[WORD,null]],
  markdown:[[/^#{1,6} .*$/my,'head'],[/^```.*$/my,'com'],[/`[^`\n]+`/y,'str'],[/\*\*[^*\n]+\*\*/y,'kw'],
    [/^\s*(?:[-*+]|\d+\.)(?=\s)/my,'pun'],[/\[[^\]\n]*\]\([^)\n]*\)/y,'key'],[WORD,null]],
  log:[[/\b\d{4}-\d\d-\d\dT[\d:.]+Z?\b/y,'com'],[/\b(?:ERROR|Error|FAIL(?:ED)?|Traceback|Exception|exit [1-9]\d*)\b/y,'err'],
    [/\b(?:WARN(?:ING)?|Warning)\b/y,'warn'],[/"(?:[^"\\\n]|\\.)*"/y,'str'],[/\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b/y,'kw'],[NUM,'num'],[WORD,null]],
  text:[]
};
LANGS.ts=LANGS.js;LANGS.diff=[[/^\+.*$/my,'str'],[/^-.*$/my,'lit'],[/^@@.*$/my,'kw']];
var MAX_HL=400000;
function tokenize(text,lang){
  var rules=LANGS[lang]||[],out=[],plain='',i=0,n=text.length;
  if(!rules.length||n>MAX_HL)return [[null,text]];
  outer:while(i<n){for(var r=0;r<rules.length;r++){var re=rules[r][0];re.lastIndex=i;var m=re.exec(text);
      if(m&&m[0].length){if(rules[r][1]){if(plain){out.push([null,plain]);plain=''}out.push([rules[r][1],m[0]])}else plain+=m[0];
        i+=m[0].length;continue outer}}
    plain+=text[i++]}
  if(plain)out.push([null,plain]);return out}
function codeView(text,lang,opts){
  opts=opts||{};var box=el('div','code'+(prefs.wrap?' wrap':'')+(prefs.ln&&opts.ln!==false?'':' no-ln'));
  var line=el('span','l');box.appendChild(line);var count=1;
  tokenize(text.replace(/\n$/,''),lang).forEach(function(t){var parts=t[1].split('\n');
    parts.forEach(function(p,k){if(k){line=el('span','l');box.appendChild(line);count++}
      if(!p)return;if(t[0]){line.appendChild(el('span','t-'+t[0],p))}else line.appendChild(doc.createTextNode(p))})});
  $$('.l',box).forEach(function(l){if(!l.firstChild)l.appendChild(doc.createTextNode('​'))});
  box.style.setProperty('--gw',String(count).length+'ch');return box}

/* --- markdown (built as DOM nodes: model-written text never becomes HTML) ---------------------- */
var INLINE=/(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)|\*\*(?=\S)([\s\S]*?\S)\*\*|__(?=\S)([\s\S]*?\S)__|\*(?=[^\s*])([\s\S]*?[^\s*])\*|(?<![\w])_(?=[^\s_])([\s\S]*?[^\s_])_(?![\w])|~~([\s\S]+?)~~|!\[([^\]]*)\]\(([^)\s]*)[^)]*\)|\[([^\]]+)\]\(([^)\s]*)[^)]*\)|<(https?:\/\/[^>\s]+)>/g;
function inline(text,parent){
  var last=0,m,re=new RegExp(INLINE.source,'g');
  while((m=re.exec(text))){
    if(m.index>last)parent.appendChild(doc.createTextNode(text.slice(last,m.index)));
    if(m[1])parent.appendChild(el('code',null,m[2]));
    else if(m[3]||m[4])inline(m[3]||m[4],parent.appendChild(el('strong')));
    else if(m[5]||m[6])inline(m[5]||m[6],parent.appendChild(el('em')));
    else if(m[7])inline(m[7],parent.appendChild(el('del')));
    else if(m[9]!==undefined)parent.appendChild(el('span','muted','[image: '+(m[8]||m[9])+']'));
    else if(m[10])parent.appendChild(linkNode(m[10],m[11]));
    else if(m[12])parent.appendChild(linkNode(m[12],m[12]));
    last=re.lastIndex}
  if(last<text.length)parent.appendChild(doc.createTextNode(text.slice(last)))}
function linkNode(label,url){
  var f=url&&findFile(url);
  if(f){var a=el('a');a.href='#'+f.id;inline(label,a);return a}
  if(/^#/.test(url)&&doc.getElementById(url.slice(1))){var b=el('a');b.href=url;inline(label,b);return b}
  var s=el('span','link');s.title=url+' (links are not followed from the dashboard)';inline(label,s);return s}
var RE={fence:/^\s{0,3}(`{3,}|~{3,})\s*([\w+#.-]*)/,head:/^\s{0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/,
  hr:/^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/,quote:/^\s{0,3}>\s?/,item:/^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/,
  tsep:/^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$/};
function cells(line){return line.trim().replace(/^\||\|$/g,'').split(/(?<!\\)\|/).map(function(c){return c.trim().replace(/\\\|/g,'|')})}
function isBlockStart(l,next){return RE.fence.test(l)||RE.head.test(l)||RE.hr.test(l)||RE.quote.test(l)||RE.item.test(l)||
  (l.indexOf('|')>=0&&next!==undefined&&RE.tsep.test(next))}
function markdown(src,cls){var box=el('div',cls===undefined?'md':cls);blocks(src.replace(/\r\n?/g,'\n').split('\n'),box);return box}
function blocks(lines,box){
  var i=0;
  while(i<lines.length){
    var l=lines[i],m;
    if(!l.trim()){i++;continue}
    if((m=RE.fence.exec(l))){var fence=m[1],body=[];i++;
      while(i<lines.length&&lines[i].trim().indexOf(fence)!==0)body.push(lines[i++]);i++;
      var pre=el('pre');pre.appendChild(codeView(body.join('\n'),langOf(m[2]),{ln:false}));box.appendChild(pre);continue}
    if((m=RE.head.exec(l))){inline(m[2],box.appendChild(el('h'+m[1].length)));i++;continue}
    if(RE.hr.test(l)){box.appendChild(el('hr'));i++;continue}
    if(RE.quote.test(l)){var q=[];while(i<lines.length&&lines[i].trim()&&(RE.quote.test(lines[i])||q.length))q.push(lines[i++].replace(RE.quote,''));
      var bq=el('blockquote');blocks(q,bq);box.appendChild(bq);continue}
    if(l.indexOf('|')>=0&&RE.tsep.test(lines[i+1]||'')){
      var t=el('table'),th=el('thead'),tr=el('tr'),aligns=cells(lines[i+1]).map(function(c){return /:$/.test(c)?(/^:/.test(c)?'center':'right'):''});
      cells(l).forEach(function(c,k){var x=el('th');if(aligns[k])x.style.textAlign=aligns[k];inline(c,x);tr.appendChild(x)});
      th.appendChild(tr);t.appendChild(th);var tb=el('tbody');i+=2;
      while(i<lines.length&&lines[i].trim()&&lines[i].indexOf('|')>=0){var r=el('tr');
        cells(lines[i++]).forEach(function(c,k){var x=el('td');if(aligns[k])x.style.textAlign=aligns[k];inline(c,x);r.appendChild(x)});tb.appendChild(r)}
      t.appendChild(tb);box.appendChild(t);continue}
    if((m=RE.item.exec(l))){i=list(lines,i,box);continue}
    var para=[];
    while(i<lines.length&&lines[i].trim()&&!(para.length&&isBlockStart(lines[i],lines[i+1])))para.push(lines[i++].trim());
    var p=el('p');para.forEach(function(x,k){if(k)p.appendChild(doc.createTextNode(' '));inline(x,p)});box.appendChild(p)}}
function list(lines,i,box){
  var first=RE.item.exec(lines[i]),indent=first[1].length,ordered=/\d/.test(first[2]);
  var ul=el(ordered?'ol':'ul');if(ordered&&parseInt(first[2],10)!==1)ul.start=parseInt(first[2],10);
  while(i<lines.length){var m=RE.item.exec(lines[i]);
    if(!m||m[1].length!==indent||/\d/.test(m[2])!==ordered)break;
    var body=[m[3]];i++;
    while(i<lines.length){var l=lines[i];
      if(!l.trim()){if(i+1<lines.length&&/^\s/.test(lines[i+1])&&(lines[i+1].match(/^\s*/)[0].length>indent)){body.push('');i++;continue}break}
      var lead=l.match(/^\s*/)[0].length;if(lead<=indent&&(RE.item.test(l)||isBlockStart(l)))break;
      body.push(lead>indent?l.slice(Math.min(lead,indent+2)):l.trim());i++}
    var li=el('li'),task=/^\[([ xX])\]\s+/.exec(body[0]);
    if(task){li.className='task';var cb=el('input');cb.type='checkbox';cb.disabled=true;cb.checked=task[1]!==' ';
      li.appendChild(cb);body[0]=body[0].slice(task[0].length)}
    if(body.length===1)inline(body[0],li);else blocks(body,li);
    if(li.childNodes.length===1&&li.firstChild.tagName==='P')li.replaceChild(li.firstChild.firstChild||doc.createTextNode(''),li.firstChild);
    ul.appendChild(li)}
  box.appendChild(ul);return i}
function langOf(s){s=(s||'').toLowerCase();return {py:'python',python:'python',js:'js',javascript:'js',ts:'ts',typescript:'ts',
  json:'json',jsonc:'json',sh:'shell',bash:'shell',shell:'shell',zsh:'shell',console:'shell',yml:'yaml',yaml:'yaml',
  html:'html',xml:'html',css:'css',http:'http',md:'markdown',markdown:'markdown',diff:'diff',log:'log'}[s]||'text'}

/* json text is shown indented, whatever its source (a .body file, a tool result) */
function pretty(text){try{var v=JSON.parse(text);return v!==null&&typeof v==='object'?JSON.stringify(v,null,2):text}catch(e){return text}}

/* --- json tree ----------------------------------------------------------------------------------- */
function jval(v){var t=v===null?'lit':typeof v==='string'?'str':typeof v==='number'?'num':'lit';
  return el('span','t-'+t,typeof v==='string'?JSON.stringify(v):String(v))}
function preview(v){if(Array.isArray(v))return '['+v.length+' item'+(v.length===1?'':'s')+']';
  var k=Object.keys(v),hint=['type','id','name','step','status'].filter(function(x){return typeof v[x]==='string'})[0];
  return '{'+(hint?hint+': '+JSON.stringify(v[hint]).slice(0,60)+', ':'')+k.length+' key'+(k.length===1?'':'s')+'}'}
function jnode(key,v,depth){
  if(v&&typeof v==='object'){var d=el('details');d.open=depth<2;var s=el('summary');
    if(key!==null){s.appendChild(el('span','t-key',key));s.appendChild(el('span','t-pun',': '))}
    s.appendChild(el('span','cnt',preview(v)));d.appendChild(s);
    var fill=function(){if(d.dataset.done)return;d.dataset.done=1;
      (Array.isArray(v)?v.map(function(x,k){return [String(k),x]}):Object.keys(v).map(function(k){return [JSON.stringify(k),v[k]]}))
        .forEach(function(kv){d.appendChild(jnode(kv[0],kv[1],depth+1))})};
    if(d.open)fill();else d.addEventListener('toggle',fill);return d}
  var leaf=el('div','leaf');if(key!==null){leaf.appendChild(el('span','t-key',key));leaf.appendChild(el('span','t-pun',': '))}
  leaf.appendChild(jval(v));return leaf}
function jsonTree(text,lines){var box=el('div','jt');
  if(!lines){try{box.appendChild(jnode(null,JSON.parse(text),0))}catch(e){return null}return box}
  var n=0;text.split('\n').forEach(function(l){if(!l.trim())return;n++;var r=el('div','rec');
    try{var node=jnode('#'+n,JSON.parse(l),1);r.appendChild(node)}catch(e){r.appendChild(el('span','t-err','#'+n+' (not JSON) '+l))}
    box.appendChild(r)});return box}

/* --- viewers: one entry per kind; add a kind by adding an entry ---------------------------------- */
var VIEWERS={
  markdown:{modes:['Rendered','Source'],render:function(c,m){return m==='Source'?codeView(c.text,'markdown'):pane(markdown(c.text))}},
  json:{modes:['Code','Tree'],render:function(c,m){return m==='Tree'&&jsonTree(c.text)||codeView(c.text,'json')}},
  jsonl:{modes:['Records','Lines'],render:function(c,m){return m==='Records'?jsonTree(c.text,true):codeView(c.text,'json')}},
  code:{render:function(c){return codeView(c.text,c.lang)}},
  log:{render:function(c){return codeView(c.text,'log')}},
  text:{render:function(c){return codeView(c.text,c.lang||'text')}},
  image:{modes:['Fit','Actual size'],noText:true,render:function(c,m){var b=el('div','img-view'+(m==='Actual size'?' actual':''));
    var img=el('img');img.src=c.src;img.alt=c.name;b.appendChild(img);return b}},
  binary:{noText:true,render:function(c){var p=pane(el('div'));p.appendChild(el('p',null,'This file is not text, so it cannot be shown here.'));
    var a=el('a','btn','Download '+c.name);a.href=c.src;a.download=c.name;p.appendChild(a);return p}},
  missing:{noText:true,render:function(c){var p=pane(el('div'));p.appendChild(el('p','t-err','Missing: '+c.path));return p}},
  large:{noText:true,render:function(c){var p=pane(el('div'));var n=$('.too-large',c.el);
    p.appendChild(el('p',null,n?n.textContent:'Not embedded.'));p.appendChild(el('p','muted',c.path));return p}}
};
function pane(child){var p=el('div','v-pane');p.appendChild(child);return p}

/* --- the viewer dialog --------------------------------------------------------------------------- */
var prefs={wrap:store('wrap')!=='0',ln:store('ln')!=='0'};
var dlg=$('#viewer'),vPath=$('.v-path',dlg),vMeta=$('.v-meta',dlg),vTools=$('.v-tools',dlg),vTabs=$('.tabs',dlg),
  vBody=$('.v-body',dlg),vStatus=$('.v-status',dlg),current=null,lastHash='';
function isTarget(n){return n&&(n.classList.contains('file')||n.classList.contains('call-src'))}
function fileCtx(f){
  if(f.tagName==='A')return {el:f,id:'',kind:'image',path:f.dataset.path||f.getAttribute('href'),
    name:(f.dataset.path||f.getAttribute('href')).split('/').pop(),meta:f.dataset.meta||'',size:'',text:null,src:f.getAttribute('href')};
  var pre=$('pre.src',f),img=$('img',f),a=$('a[download]',f),lz=$('.lazy',f),hit=lz&&cache[f.id];
  var c={el:f,id:f.id,kind:f.dataset.kind||'text',lang:f.dataset.lang,path:f.dataset.path||f.id,
    name:(f.dataset.path||'').split('/').pop(),meta:f.dataset.meta||'',size:f.dataset.size||'',
    text:pre?pre.textContent:null,src:img?img.getAttribute('src'):a?a.getAttribute('href'):null};
  if(lz){c.lazy=true;c.src=lz.dataset.src;c.text=hit&&hit.v===(f.dataset.version||'')?hit.text:null}
  if(c.kind==='json'&&c.text!=null)c.text=pretty(c.text);return c}
/* a served page's files load when opened (and again when they change): `done(text, error)` */
var cache={},bigOk={},BIG=20*1024*1024;
function get(url){return fetch(url,{cache:'no-store',credentials:'same-origin'}).then(function(r){
  if(!r.ok)throw new Error(r.status+' '+r.statusText);return r.text()})}
function load(f,done){var v=f.dataset.version||'',hit=cache[f.id];if(hit&&hit.v===v){done(hit.text);return}
  get($('.lazy',f).dataset.src).then(function(t){cache[f.id]={v:v,text:t};done(t)},function(err){done(null,err.message)})}
function loading(text){vBody.textContent='';vBody.appendChild(pane(el('p','muted loading',text||'Loading…')))}
function failed(text){vBody.textContent='';vBody.appendChild(pane(el('p','t-err',text)))}
function siblings(n){if(n.classList.contains('call-src'))return $$('.call-src');
  if(n.tagName==='A')return $$('a[data-image]',n.closest('.evidence')||doc);
  var ul=n.closest('ul');return ul?$$(':scope>li>.file',ul):[n]}
function flash(msg){vStatus.textContent=msg;vStatus.classList.add('on');setTimeout(function(){vStatus.classList.remove('on')},1400)}
function copy(text){
  function fallback(){var t=el('textarea');t.value=text;t.style.position='fixed';t.style.opacity='0';dlg.appendChild(t);t.select();
    try{doc.execCommand('copy');flash('Copied')}catch(e){flash('Copy failed')}t.remove()}
  if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(text).then(function(){flash('Copied')},fallback);else fallback()}
function download(c){var a=el('a');a.download=c.name||'file.txt';
  if(c.text!=null){a.href=URL.createObjectURL(new Blob([c.text],{type:'text/plain'}));setTimeout(function(){URL.revokeObjectURL(a.href)},5000)}else a.href=c.src;
  dlg.appendChild(a);a.click();a.remove()}
function setPath(p){vPath.textContent='';var parts=p.split('/'),name=parts.pop();
  vPath.appendChild(doc.createTextNode('‎'+(parts.length?parts.join('/')+'/':'')));vPath.appendChild(el('b',null,name));vPath.title=p}
function setMeta(items){vMeta.textContent='';items.filter(Boolean).forEach(function(x){vMeta.appendChild(el('span',null,x))})}
function openTarget(n){if(!n)return;if(!dlg.open){lastHash=location.hash;dlg.showModal()}
  current=n;if(n.id)history.replaceState(null,'','#'+n.id);
  if(n.classList.contains('call-src'))openCall(n);else openFile(n);vBody.scrollTop=0;vBody.focus()}
function closeViewer(){if(dlg.open)dlg.close()}
/* `close` fires after close(): a file opened again since then keeps the viewer */
dlg.addEventListener('close',function(){if(dlg.open)return;var back=current;current=null;
  history.replaceState(null,'',lastHash&&lastHash!=='#'+(back&&back.id)?lastHash:location.pathname+location.search);
  var opener=back&&!back.id?back:back&&$$('[data-open], a').filter(function(x){return x.dataset.open===back.id||x.getAttribute('href')==='#'+back.id})[0];if(opener)opener.focus()});
dlg.addEventListener('click',function(ev){if(ev.target===dlg)closeViewer()});
function step(d){if(!current)return;var s=siblings(current),k=s.indexOf(current);if(s[k+d])openTarget(s[k+d])}
function frame(title,meta,tools){setPath(title);setMeta(meta);vTools.textContent='';vTabs.textContent='';vTabs.hidden=true;
  var nav=$('.v-nav',dlg),s=siblings(current),k=s.indexOf(current);
  nav.querySelector('[data-step="-1"]').disabled=k<=0;nav.querySelector('[data-step="1"]').disabled=k<0||k>=s.length-1;
  nav.querySelector('.pos').textContent=s.length>1?(k+1)+' / '+s.length:'';
  tools.forEach(function(t){vTools.appendChild(t)})}
function toggles(redraw){
  var w=btn('Wrap',{icon:'wrap',on:function(){prefs.wrap=!prefs.wrap;store('wrap',prefs.wrap?'1':'0');w.setAttribute('aria-pressed',prefs.wrap);
    $$('.code',vBody).forEach(function(c){c.classList.toggle('wrap',prefs.wrap)})}});w.setAttribute('aria-pressed',prefs.wrap);
  var n=btn('Line numbers',{icon:'hash',on:function(){prefs.ln=!prefs.ln;store('ln',prefs.ln?'1':'0');n.setAttribute('aria-pressed',prefs.ln);
    $$('.v-body>.code',dlg).forEach(function(c){c.classList.toggle('no-ln',!prefs.ln)})}});n.setAttribute('aria-pressed',prefs.ln);
  return [w,n]}
function modeSwitch(modes,active,on){var s=el('div','seg');s.setAttribute('role','group');s.setAttribute('aria-label','View');
  modes.forEach(function(m){var b=el('button',null,m);b.type='button';b.setAttribute('aria-pressed',m===active);
    b.addEventListener('click',function(){$$('button',s).forEach(function(x){x.setAttribute('aria-pressed',x===b)});on(m)});s.appendChild(b)});return s}
function openFile(f,after){
  var c=fileCtx(f);
  if(c.lazy&&c.text==null&&+(f.dataset.bytes||0)>BIG&&!bigOk[f.id]){
    /* a very large file: loading it all can stall the page, so ask first */
    frame(c.path,[c.kind==='code'?c.lang:c.kind,c.size,c.meta],[]);vBody.textContent='';
    var p=pane(el('div'));p.appendChild(el('p',null,'This file is '+c.size+'. Showing it all may slow this page down.'));
    p.appendChild(btn('Show it',{on:function(){bigOk[f.id]=1;openFile(f)}}));
    var a=el('a','btn','Download');a.href=c.src;a.download=c.name;p.appendChild(a);vBody.appendChild(p);return}
  if(c.lazy&&c.text==null){
    if(!after){frame(c.path,[c.kind==='code'?c.lang:c.kind,c.size,c.meta],[]);loading()}
    load(f,function(t,err){if(!current||current.id!==f.id)return;if(t==null)failed('Could not load '+c.path+': '+err);else openFile(current,after)});return}
  var v=VIEWERS[c.kind]||VIEWERS.text,mode=v.modes?(store('mode-'+c.kind)||v.modes[0]):null;
  if(v.modes&&v.modes.indexOf(mode)<0)mode=v.modes[0];
  var codeTools=[];
  function draw(m){vBody.textContent='';vBody.appendChild(v.render(c,m)||codeView(c.text||'','text'));
    var plain=!!$('.v-body>.code',dlg);codeTools.forEach(function(t){t.hidden=!plain})}
  var tools=[];
  if(v.modes)tools.push(modeSwitch(v.modes,mode,function(m){store('mode-'+c.kind,m);mode=m;draw(m)}));
  tools.push(el('span','spacer'));
  if(!v.noText){codeTools=toggles();tools=tools.concat(codeTools)}
  if(c.text!=null)tools.push(btn('Copy',{icon:'copy',on:function(){copy(c.text)}}));
  if(c.text!=null||c.src)tools.push(btn('Download',{icon:'download',on:function(){download(c)}}));
  frame(c.path,[c.kind==='code'?c.lang:c.kind,c.size,c.meta],tools);draw(mode);if(after)after()}

/* calls: tabs for the conversation, the prompt, and the call's settings */
function openCall(n){
  var tabs=[['Conversation',null]];
  if(n.dataset.prompt)tabs.push(['Prompt',n.dataset.prompt]);if(n.dataset.settings)tabs.push(['Settings',n.dataset.settings]);
  var hide=(store('conv-hide')||'thinking raw').split(' ').filter(Boolean),tab=0;
  function drawConv(){vBody.textContent='';var conv=$('.conv',n),lz=$('.conv-lazy',n);
    if(!conv&&lz){loading('Loading the conversation…');
      get(lz.dataset.src).then(function(html){var home=doc.getElementById(n.id)||n,ph=$('.conv-lazy',home),t=doc.createElement('template');
        t.innerHTML=html;if(ph)ph.replaceWith(t.content);if(current&&current.id===n.id&&tab===0){n=home;drawConv()}},
        function(err){if(current&&current.id===n.id&&tab===0)failed('Could not load the conversation: '+err.message)});return}
    if(!conv){vBody.appendChild(pane(el('p','t-err',$('.unavailable',n)?$('.unavailable',n).textContent:'No conversation.')));return}
    var c=conv.cloneNode(true);c.removeAttribute('id');c.dataset.hide=hide.join(' ');
    $$('pre[data-md]',c).forEach(function(p){p.replaceWith(markdown(p.textContent))});
    $$('pre[data-lang]',c).forEach(function(p){var x=el('pre');x.appendChild(codeView(p.dataset.lang==='json'?pretty(p.textContent):p.textContent,p.dataset.lang,{ln:false}));p.replaceWith(x)});
    var p=pane(c);vBody.appendChild(p)}
  function convTools(){var chips=el('div','chips');
    [['tool','Tool calls'],['result','Results'],['thinking','Thinking'],['raw','System records']].forEach(function(k){
      var b=el('button','chip',k[1]);b.type='button';b.setAttribute('aria-pressed',hide.indexOf(k[0])<0);
      b.addEventListener('click',function(){var at=hide.indexOf(k[0]);if(at<0)hide.push(k[0]);else hide.splice(at,1);
        store('conv-hide',hide.join(' '));b.setAttribute('aria-pressed',hide.indexOf(k[0])<0);
        var cv=$('.conv',vBody);if(cv)cv.dataset.hide=hide.join(' ')});chips.appendChild(b)});
    return [el('span','small muted','Show'),chips,el('span','spacer'),
      btn('Expand all',{on:function(){$$('details',vBody).forEach(function(d){d.open=true})}}),
      btn('Collapse all',{on:function(){$$('details',vBody).forEach(function(d){d.open=false})}})]}
  function select(k){$$('button',vTabs).forEach(function(b,j){b.setAttribute('aria-selected',j===k);b.tabIndex=j===k?0:-1});
    vTools.textContent='';tab=k;
    if(!tabs[k][1]){convTools().forEach(function(t){vTools.appendChild(t)});drawConv();return}
    var f=doc.getElementById(tabs[k][1]),c=fileCtx(f),v=VIEWERS[c.kind]||VIEWERS.text;
    if(c.lazy&&c.text==null){loading();load(f,function(t,err){if(!current||current.id!==n.id||tab!==k)return;
      if(t==null)failed('Could not load '+c.path+': '+err);else select(k)});return}
    var mode=v.modes?v.modes[0]:null;
    var parts=$('.prompt-sources',n);
    var draw=function(m){vBody.textContent='';if(k===1&&parts)vBody.appendChild(pane(parts.cloneNode(true)));vBody.appendChild(v.render(c,m))};
    if(v.modes)vTools.appendChild(modeSwitch(v.modes,mode,draw));vTools.appendChild(el('span','spacer'));
    toggles().forEach(function(t){vTools.appendChild(t)});
    vTools.appendChild(btn('Copy',{icon:'copy',on:function(){copy(c.text)}}));
    vTools.appendChild(btn('Open file',{icon:'file',on:function(){openTarget(f)}}));draw(mode)}
  frame(n.dataset.title,(n.dataset.meta||'').split(' · '),[]);
  vTabs.hidden=false;vTabs.setAttribute('role','tablist');
  tabs.forEach(function(t,k){var b=el('button',null,t[0]);b.type='button';b.setAttribute('role','tab');
    b.addEventListener('click',function(){select(k)});vTabs.appendChild(b)});
  vTabs.onkeydown=function(ev){var bs=$$('button',vTabs),k=bs.indexOf(doc.activeElement);
    if(ev.key==='ArrowRight'||ev.key==='ArrowLeft'){ev.preventDefault();k=(k+(ev.key==='ArrowRight'?1:-1)+bs.length)%bs.length;bs[k].focus();select(k)}};
  select(0)}

$('[data-action="close"]',dlg).addEventListener('click',closeViewer);
$$('[data-step]',dlg).forEach(function(b){b.addEventListener('click',function(){step(+b.dataset.step)})});
var maxBtn=$('[data-action="max"]',dlg);
function setMax(on){dlg.classList.toggle('max',on);maxBtn.setAttribute('aria-pressed',on);store('max',on?'1':'0')}
maxBtn.addEventListener('click',function(){setMax(!dlg.classList.contains('max'))});setMax(store('max')==='1');
dlg.addEventListener('keydown',function(ev){
  if(ev.target.closest('input,textarea'))return;
  if(ev.key==='ArrowLeft'&&ev.altKey||ev.key==='['){ev.preventDefault();step(-1)}
  else if(ev.key==='ArrowRight'&&ev.altKey||ev.key===']'){ev.preventDefault();step(1)}
  else if(ev.key==='f'&&!ev.ctrlKey&&!ev.metaKey){ev.preventDefault();setMax(!dlg.classList.contains('max'))}});

/* --- explorer: clicks open the viewer, filter, kind chips, arrow keys ----------------------------- */
doc.addEventListener('click',function(ev){var a=ev.target.closest('a[data-image]');
  if(!a||ev.button||ev.metaKey||ev.ctrlKey||ev.shiftKey)return;ev.preventDefault();openTarget(a)});
/* what each view's own elements do; run again on a view a served page replaced */
function bind(scope){bindTips(scope);
$$('.explorer .file>summary',scope).forEach(function(s){s.addEventListener('click',function(ev){ev.preventDefault();openTarget(s.parentNode)})});
$$('[data-open]',scope).forEach(function(b){b.addEventListener('click',function(ev){ev.preventDefault();openTarget(doc.getElementById(b.dataset.open))})});
$$('tr[data-open]',scope).forEach(function(r){r.tabIndex=0;r.addEventListener('keydown',function(ev){if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();openTarget(doc.getElementById(r.dataset.open))}})});
$$('img[data-src-of]',scope).forEach(function(img){var f=doc.getElementById(img.dataset.srcOf),s=f&&$('img',f);
  if(s)img.src=s.getAttribute('src');else img.replaceWith(doc.createTextNode(img.alt))});
$$('.explorer',scope).forEach(function(ex){
  var box=ex.parentNode,input=$('input[type="search"]',box),kinds=[];
  function apply(){var q=(input&&input.value||'').toLowerCase().trim();
    $$('li.f',ex).forEach(function(li){var f=$('.file',li),ok=(!q||(f.dataset.path||'').toLowerCase().indexOf(q)>=0)&&(!kinds.length||kinds.indexOf(f.dataset.kind==='jsonl'?'json':f.dataset.kind)>=0);
      li.classList.toggle('hidden-by-filter',!ok)});
    $$('li.d',ex).reverse().forEach(function(li){var any=$('li.f:not(.hidden-by-filter)',li);li.classList.toggle('hidden-by-filter',!any);
      if((q||kinds.length)&&any)$('details',li).open=true});
    var n=$$('li.f:not(.hidden-by-filter)',ex).length,c=$('[data-count]',box);if(c)c.textContent=n+' file'+(n===1?'':'s')}
  if(input)input.addEventListener('input',apply);
  $$('[data-kind-chip]',box).forEach(function(b){b.addEventListener('click',function(){var k=b.dataset.kindChip,at=kinds.indexOf(k);
    if(at<0)kinds.push(k);else kinds.splice(at,1);b.setAttribute('aria-pressed',at<0);apply()})});
  $$('[data-action="expand"],[data-action="collapse"]',box).forEach(function(b){b.addEventListener('click',function(){
    var open=b.dataset.action==='expand';$$('details.dir',ex).forEach(function(d){d.open=open})})});
  ex.addEventListener('keydown',function(ev){var s=ev.target.closest('summary');if(!s)return;
    var vis=$$('summary',ex).filter(function(x){return x.offsetParent!==null}),k=vis.indexOf(s),d=s.parentNode;
    if(ev.key==='ArrowDown'&&vis[k+1]){ev.preventDefault();vis[k+1].focus()}
    else if(ev.key==='ArrowUp'&&vis[k-1]){ev.preventDefault();vis[k-1].focus()}
    else if(ev.key==='ArrowRight'&&d.classList.contains('dir')){ev.preventDefault();if(!d.open)d.open=true;else if(vis[k+1])vis[k+1].focus()}
    else if(ev.key==='ArrowLeft'){ev.preventDefault();if(d.classList.contains('dir')&&d.open)d.open=false;
      else{var up=d.parentNode.closest('details.dir');if(up)$('summary',up).focus()}}});
  apply()});

/* --- simple list filters (calls, events); an empty list has no table, so nothing to filter -------- */
$$('[data-filter-for]',scope).forEach(function(input){var t=doc.getElementById(input.dataset.filterFor);if(!t)return;
  input.addEventListener('input',function(){var q=input.value.toLowerCase();
    $$('tbody tr',t).forEach(function(r){r.classList.toggle('hidden-by-filter',q&&r.textContent.toLowerCase().indexOf(q)<0)})})});
$$('[data-loop-chip]',scope).forEach(function(b){b.addEventListener('click',function(){var t=doc.getElementById(b.dataset.table),on=b.getAttribute('aria-pressed')!=='true';
  if(!t)return;
  $$('[data-loop-chip][data-table="'+b.dataset.table+'"]',doc).forEach(function(x){x.setAttribute('aria-pressed',x===b&&on)});
  $$('tbody tr',t).forEach(function(r){r.style.display=on&&r.dataset.loop!==b.dataset.loopChip?'none':''})})})}
bind(doc);

/* --- go to anything (Ctrl+K or /) ---------------------------------------------------------------- */
var serving=+(root.dataset.serve||0);
var pal=$('#palette'),pin=$('input',pal),plist=$('ul',pal),items=[],sel=0,MIN_TEXT=3,MAX_TEXT=40;
/* Each item can also be searched by its text: a file's content, or a call's conversation. */
function index(){if(items.length)return;
  $$('.view').forEach(function(v){items.push({label:v.dataset.title||v.id,path:'view',icon:'grid',go:function(){route(v.id,true)}})});
  /* a served page searches contents on the server (serveSearch): its files are not in the page */
  $$('.call-src').forEach(function(c){items.push({label:c.dataset.title,path:c.dataset.meta||'',icon:'chat',kind:'call',
    text:serving?null:function(){var v=$('.conv',c);return v?v.textContent:''},go:function(q){openTarget(c);if(q)reveal(q)}})});
  $$('.explorer .file').forEach(function(f){items.push({label:(f.dataset.path||'').split('/').pop(),path:f.dataset.path,icon:f.dataset.icon||'file',
    text:serving?null:function(){return fileCtx(f).text||''},go:function(q,line){openTarget(f);if(q)reveal(q,line)}})})}
function lower(it){if(it._low==null)it._low=it.text?it.text().toLowerCase():'';return it._low}
function score(it,q){if(!q)return 1;var h=(it.label+' '+it.path).toLowerCase(),k=0,s=0,last=-1;
  for(var i=0;i<q.length;i++){k=h.indexOf(q[i],k);if(k<0)return 0;s+=k===last+1?3:1;last=k;k++}
  if(it.label.toLowerCase().indexOf(q)>=0)s+=20;return s}
/* `[line number, line text]` of the first match of `q` in an item's text, or null */
function hit(it,q){var low=lower(it),at=low.indexOf(q);if(at<0)return null;var text=it.text();
  var a=text.lastIndexOf('\n',at)+1,b=text.indexOf('\n',at);if(b<0)b=text.length;
  return [text.slice(0,at).split('\n').length,text.slice(a,b),at-a]}
function snippet(line,col,len){var from=Math.max(0,col-40),p=el('span','p snip');
  if(from)p.appendChild(doc.createTextNode('…'));p.appendChild(doc.createTextNode(line.slice(from,col)));
  p.appendChild(el('mark',null,line.slice(col,col+len)));p.appendChild(doc.createTextNode(line.slice(col+len,col+len+80)));return p}
function option(icn,label,extra,go){var li=el('li');li.setAttribute('role','option');li.appendChild(icon(icn));
  li.appendChild(el('span',null,label));li.appendChild(extra);li._go=go;
  li.addEventListener('click',function(){pal.close();go()});plist.appendChild(li)}
function renderPal(){var raw=pin.value.trim(),q=raw.toLowerCase().replace(/\s+/g,''),text=raw.toLowerCase();plist.textContent='';sel=0;
  var named=items.map(function(it){return [score(it,q),it]}).filter(function(x){return x[0]>0})
    .sort(function(a,b){return b[0]-a[0]}).slice(0,raw.length>=MIN_TEXT?20:60);
  named.forEach(function(x){option(x[1].icon,x[1].label,el('span','p',x[1].path),function(){x[1].go()})});
  if(raw.length>=MIN_TEXT){var n=0;
    items.forEach(function(it){if(n>=MAX_TEXT||!it.text)return;var h=hit(it,text);if(!h)return;n++;
      option(it.icon,it.label+(it.kind==='call'?'':' · line '+h[0]),snippet(h[1],h[2],text.length),function(){it.go(text,h[0])})});
    if(n){var head=el('li','group','In contents');head.setAttribute('role','presentation');
      var first=plist.children[named.length];if(first)plist.insertBefore(head,first)}}
  if(serving&&raw.length>=MIN_TEXT){serveSearch(text);return}
  var opts=$$('li[role="option"]',plist);if(opts[0])opts[0].setAttribute('aria-selected','true');
  if(!opts.length)plist.appendChild(el('li','muted','No match'))}
var searchTimer=null,searchSeq=0;
function serveSearch(q){clearTimeout(searchTimer);var my=++searchSeq,wait=el('li','muted','Searching contents…');
  wait.setAttribute('role','presentation');plist.appendChild(wait);
  function selectFirst(){var opts=$$('li[role="option"]',plist);if(opts[0]&&!$('li[aria-selected="true"]',plist))opts[0].setAttribute('aria-selected','true');
    if(!opts.length)plist.appendChild(el('li','muted','No match'))}
  searchTimer=setTimeout(function(){fetch('search?q='+encodeURIComponent(q),{cache:'no-store',credentials:'same-origin'})
    .then(function(r){if(!r.ok)throw new Error(r.statusText);return r.json()}).then(function(j){
      if(my!==searchSeq||!pal.open)return;wait.remove();
      var hits=(j.results||[]).filter(function(h){return doc.getElementById(h.id)});
      if(hits.length){var head=el('li','group','In contents');head.setAttribute('role','presentation');plist.appendChild(head)}
      hits.forEach(function(h){var node=doc.getElementById(h.id),call=h.kind==='call';
        var snip=el('span','p snip');snip.appendChild(doc.createTextNode((h.before.length>=40?'…':'')+h.before));
        snip.appendChild(el('mark',null,h.match));snip.appendChild(doc.createTextNode(h.after));
        option(call?'chat':(node.dataset.icon||'file'),call?node.dataset.title:(node.dataset.path||'').split('/').pop()+' · line '+h.line,
          snip,function(){openTarget(node);reveal(q,call?null:h.line)})});
      selectFirst()},function(){if(my===searchSeq){wait.textContent='Content search failed';selectFirst()}})},200)}
/* after opening a search result: bring the matching line (or message) into view and mark it */
function reveal(q,line){var tries=0;setTimeout(function go(){var t=null;
  if($('.v-body .loading',dlg)&&tries++<150){setTimeout(go,60);return}
  if(line){var ls=$$('.v-body>.code .l',dlg);t=ls[line-1]||null}
  function has(n){return n.textContent.toLowerCase().indexOf(q)>=0}
  if(!t){var m=$$('.v-body .msg',dlg).filter(has)[0]||$('.v-body',dlg);
    t=$$('p, li, td, .l, h1, h2, h3, h4',m).filter(has)[0]||(m.classList.contains('msg')?m:null)}
  if(!t)return;var d=t.closest('details');while(d){d.open=true;d=d.parentElement.closest('details')}
  t.classList.add('hit');t.scrollIntoView({block:'center'})},0)}
function openPal(){index();pin.value='';renderPal();pal.showModal();pin.focus()}
pin.addEventListener('input',renderPal);
pin.addEventListener('keydown',function(ev){var lis=$$('li[role="option"]',plist);
  if(ev.key==='ArrowDown'||ev.key==='ArrowUp'){ev.preventDefault();sel=Math.max(0,Math.min(lis.length-1,sel+(ev.key==='ArrowDown'?1:-1)));
    lis.forEach(function(l,k){l.setAttribute('aria-selected',k===sel)});if(lis[sel])lis[sel].scrollIntoView({block:'nearest'})}
  else if(ev.key==='Enter'&&lis[sel]){ev.preventDefault();pal.close();lis[sel]._go()}});
pal.addEventListener('click',function(ev){if(ev.target===pal)pal.close()});
$$('[data-action="palette"]').forEach(function(b){b.addEventListener('click',openPal)});
doc.addEventListener('keydown',function(ev){
  if((ev.key==='k'&&(ev.ctrlKey||ev.metaKey))||(ev.key==='/'&&!ev.target.closest('input,textarea,dialog'))){ev.preventDefault();if(!pal.open)openPal()}});

function findFile(url){url=url.replace(/^\.\//,'').split('#')[0];if(!url||/^[a-z]+:/i.test(url))return null;
  return $$('.explorer .file').filter(function(f){var p=f.dataset.path||'';return p===url||p.slice(-url.length-1)==='/'+url})[0]||null}

/* --- served (devloops dashboard --serve): follow the run, replacing only the views that changed - */
var liveBtn=$('[data-action="live"]'),paused=store('live-paused')==='1',busy=false,offline=false;
function setLive(){if(!liveBtn)return;liveBtn.setAttribute('aria-pressed',!paused&&!offline);
  $('[data-live-label]',liveBtn).textContent=offline?'Offline':paused?'Paused':'Live'}
function bindSwitch(){$$('select[data-action="workspace"]').forEach(function(s){
  s.addEventListener('change',function(){location.assign('../'+encodeURIComponent(s.value)+'/')})})}
bindSwitch();
/* the reader's place in a view: open folders and sections, filters typed, chips pressed */
function detailsKey(d){if(d.id)return '#'+d.id;var k=[],x=d;
  while(x){var s=$(':scope>summary',x),n=s&&$('.nm',s);k.unshift((n||s)?(n||s).textContent.trim().slice(0,80):'?');
    x=x.parentElement&&x.parentElement.closest('details')}return k.join('/')}
function keep(v){var st={open:{},inputs:[],chips:[]};
  $$('details',v).forEach(function(d){st.open[detailsKey(d)]=d.open});
  $$('input[type="search"]',v).forEach(function(i){st.inputs.push(i.value)});
  $$('[data-kind-chip],[data-loop-chip]',v).forEach(function(b){if(b.getAttribute('aria-pressed')==='true')st.chips.push(b.dataset.kindChip||b.dataset.loopChip)});
  return st}
function restore(v,st){$$('details',v).forEach(function(d){var k=detailsKey(d);if(k in st.open)d.open=st.open[k]});
  $$('input[type="search"]',v).forEach(function(i,k){if(st.inputs[k]){i.value=st.inputs[k];i.dispatchEvent(new Event('input'))}});
  $$('[data-kind-chip],[data-loop-chip]',v).forEach(function(b){if(st.chips.indexOf(b.dataset.kindChip||b.dataset.loopChip)>=0)b.click()})}
function swap(nd){
  var active=($('.view.active')||views[0]).id,main=$('main.content'),prev=$('.topbar',main),seen={},ae=doc.activeElement,focus=null;
  if(ae&&ae.matches('input')&&ae.closest('.view')){var av=ae.closest('.view');focus=[av.id,$$('input',av).indexOf(ae),ae.selectionStart,ae.selectionEnd]}
  $$('.view',nd).forEach(function(nv){seen[nv.id]=1;var old=doc.getElementById(nv.id),node=old;
    if(!old||!old.classList.contains('view')||old.dataset.hash!==nv.dataset.hash){
      var st=old&&keep(old);node=doc.importNode(nv,true);if(old)old.replaceWith(node);bind(node);if(st)restore(node,st)}
    if(prev.nextElementSibling!==node)prev.after(node);prev=node});
  views.forEach(function(v){if(!seen[v.id])v.remove()});views=$$('.view');
  ['.nav','[data-status]','[data-generated]','.brand'].forEach(function(q){var a=$(q),b=$(q,nd);if(a&&b&&a.innerHTML!==b.innerHTML){a.innerHTML=b.innerHTML;if(q==='.brand')bindSwitch()}});
  root.dataset.version=nd.documentElement.dataset.version||'';items=[];
  showView(doc.getElementById(active)||views[0],true);
  if(focus){var fv=doc.getElementById(focus[0]),fi=fv&&$$('input',fv)[focus[1]];
    if(fi&&fi!==doc.activeElement){fi.focus();try{fi.setSelectionRange(focus[2],focus[3])}catch(e){}}}
  if(dlg.open&&current&&current.id){var again=doc.getElementById(current.id);
    if(again&&again!==current){var was=current;current=again;
      if(again.classList.contains('file')&&again.dataset.version!==was.dataset.version){
        /* the open file changed: show the new text where the reader was, or follow its end */
        var st=vBody.scrollTop,end=st+vBody.clientHeight>=vBody.scrollHeight-24;
        openFile(again,function(){vBody.scrollTop=end?vBody.scrollHeight:st})}}}}
function follow(){if(busy||paused||doc.hidden)return;busy=true;
  fetch('version',{cache:'no-store',credentials:'same-origin'}).then(function(r){if(!r.ok)throw new Error(r.statusText);return r.json()})
    .then(function(j){if(offline){offline=false;setLive()}
      if(j.version===root.dataset.version)return;
      return get('./').then(function(text){swap(new DOMParser().parseFromString(text,'text/html'))})})
    .then(function(){busy=false},function(){busy=false;if(!offline){offline=true;setLive()}})}
if(serving){setLive();setInterval(follow,serving*1000);
  doc.addEventListener('visibilitychange',function(){if(!doc.hidden)follow()});
  if(liveBtn)liveBtn.addEventListener('click',function(){paused=!paused;store('live-paused',paused?'1':'0');setLive();if(!paused)follow()})}

history.scrollRestoration='manual';
route(location.hash.slice(1));
function topIfView(){var t=location.hash&&doc.getElementById(location.hash.slice(1));if(!t||t.classList.contains('view'))scrollTo(0,0)}
setTimeout(topIfView,0);addEventListener('load',function(){setTimeout(topIfView,0)});
})();
