'use strict';
const S = {me:null, projects:[], pid:null, role:'viewer', page:'overview', csrf:'', lastRun:null, checkedRows:null, members:[], mode:'production'};
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const statusText = {open:'待处理',in_progress:'整改中',ready_for_retest:'待复测',closed:'已关闭',not_tested:'未测试',failed:'未通过',passed:'待验收',accepted:'已验收'};
const roleText = {admin:'系统管理员',manager:'项目经理',tester:'测试人员',implementer:'整改负责人',approver:'验收负责人',viewer:'只读访客'};
const can = (...roles) => roles.some(r=>(S.role||'').split(',').includes(r)) || (S.mode==='demo' && S.role==='admin');
const roleLabel = v => (v||'').split(',').map(r=>roleText[r]||r).join(' + ');
const sevText = {critical:'紧急',high:'高',medium:'中',low:'低'};
const pid = p => `/api/projects/${S.pid}${p}`;
function toast(msg, isError=false){const el=$('toast'); el.textContent=msg;el.style.display='block';el.style.background=isError?'#a43944':'#18384f';clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>{el.style.display='none'},4500)}
async function api(url, opts={}){
  const method = opts.method||'GET'; const headers={...(opts.headers||{})};
  if(opts.body && !(opts.body instanceof FormData)) headers['Content-Type']='application/json';
  if(!['GET','HEAD'].includes(method)) headers['X-CSRF-Token']=S.csrf;
  const res=await fetch(url, {credentials:'same-origin',...opts, headers});
  const type=res.headers.get('content-type')||'';
  if(!res.ok){const err=type.includes('json')?await res.json().catch(()=>({})):{};throw new Error(typeof err.detail==='string'?err.detail:`请求失败 (${res.status})`)}
  return type.includes('json')?res.json():res;
}
function error(e){toast(e.message||String(e),true);}
function topActions(){
  $('sidebar').hidden=!S.me;
  $('top-actions').innerHTML=S.me? `<label>项目： <select id="project-choice">${S.projects.map(p=>`<option value="${esc(p.id)}" ${p.id===S.pid?'selected':''}>${esc(p.name)}</option>`).join('')}</select></label><span>${esc(S.me.name)} · ${esc(roleLabel(S.role))}</span><button class="btn ghost small" id="logout">退出</button>` : '';
  if(S.me){$('project-choice').onchange=async e=>{S.pid=e.target.value;S.role=S.projects.find(x=>x.id===S.pid)?.role||'viewer';S.page='overview';await render();};$('logout').onclick=async()=>{try{await api('/api/auth/logout',{method:'POST'});location.reload()}catch(e){error(e)}};}
  const tabs=[['overview','总览'],['issues','问题工单'],['quality','数据质量'],['uat','UAT验收']];
  if(can('manager','approver'))tabs.push(['audit','审计日志']);
  tabs.push(['release','上线审批']);
  if(S.me?.is_admin)tabs.push(['users','用户与权限']);
  $('nav').innerHTML=tabs.map(([key,label])=>`<button data-page="${key}" class="${S.page===key?'active':''}">${label}</button>`).join('');
  document.querySelectorAll('[data-page]').forEach(x=>x.onclick=async()=>{S.page=x.dataset.page;await render()});
}
async function boot(){
  try{const health=await api('/api/health');S.mode=health.mode;S.me=await api('/api/auth/me');S.csrf=S.me.csrf_token;
    if(S.me.must_change_password){showChangePassword();return}await loadProjects();}
  catch(e){showLogin();}
}
function showLogin(){S.me=null;S.csrf='';$('sidebar').hidden=true;$('top-actions').innerHTML='';$('app').innerHTML=`<div class="login-layout"><div class="card"><span class="pill">受控访问 · 业务数据需登录</span><h1 style="margin-top:20px">欢迎使用 VeriFlow</h1><p class="intro">企业信息系统质量、UAT与整改工作台。仅使用模拟数据。</p><form id="login-form"><div class="field"><label for="email">工作邮箱</label><input id="email" type="email" autocomplete="username" required placeholder="name@company.com"></div><div class="field"><label for="pass">登录密码</label><input id="pass" type="password" autocomplete="current-password" required></div><button class="btn" type="submit">登录工作台</button></form><hr class="divider"><p class="muted sm">账号由管理员创建；首次登录须修改临时密码。此演示项目不开放自行注册。</p></div></div>`;
  $('login-form').onsubmit=async e=>{e.preventDefault();try{const result=await api('/api/auth/login',{method:'POST',body:JSON.stringify({email:$('email').value,password:$('pass').value})});S.me=result;S.csrf=result.csrf_token; if(result.must_change_password){showChangePassword();return;}await loadProjects()}catch(err){error(err)}};
}
function showChangePassword(){ $('sidebar').hidden=true;$('app').innerHTML=`<div class="login-layout"><div class="card"><h1>首次登录安全设置</h1><p class="intro">必须修改临时密码后才能访问业务数据。</p><form id="password-form"><div class="field"><label>当前临时密码</label><input id="oldpass" type="password" required></div><div class="field"><label>新密码（至少12位）</label><input id="newpass" type="password" minlength="12" required></div><button class="btn" type="submit">修改密码并重新登录</button></form></div></div>`;
$('password-form').onsubmit=async e=>{e.preventDefault();try{const r=await api('/api/auth/change-password',{method:'POST',body:JSON.stringify({old_password:$('oldpass').value,new_password:$('newpass').value})});toast(r.message);showLogin()}catch(err){error(err)}};
}
async function loadProjects(){S.projects=await api('/api/projects');if(!S.projects.length){$('sidebar').hidden=true;$('app').innerHTML='<div class="empty">当前账号尚未加入任何项目，请联系系统管理员。</div>';return}S.pid=S.projects[0].id;S.role=S.projects[0].role;await render();}
async function render(){topActions();if(!S.pid)return; $('app').innerHTML='<p class="muted">正在载入...</p>';try{
  if(S.page==='overview')await showOverview();if(S.page==='issues')await showIssues();if(S.page==='quality')await showQuality();if(S.page==='uat')await showUat();if(S.page==='users')await showUsers();if(S.page==='audit')await showAudit();if(S.page==='release')await showRelease();
}catch(e){error(e);$('app').innerHTML=`<div class="notice danger">${esc(e.message)}</div>`}}
function pill(v){const tag=v==='closed'||v==='accepted'?'good':v==='failed'?'bad':v==='ready_for_retest'||v==='passed'?'warn':'';return `<span class="pill ${tag}">${esc(statusText[v]||v)}</span>`}
async function showOverview(){const d=await api(pid('/dashboard'));const percentage=d.uat_total?Math.round(d.uat_accepted*100/d.uat_total):0;
$('app').innerHTML=`<h1>质量总览</h1><p class="intro">查看项目运行状态、开放缺陷与上线验收进度。所有业务数据均为模拟样本。</p><div class="stats"><section class="card stat"><em>全部工单</em><b>${d.issues}</b><small>质量与功能缺陷</small></section><section class="card stat"><em>未关闭工单</em><b>${d.open_issues}</b><small>需跟踪整改</small></section><section class="card stat"><em>高风险阻断项</em><b>${d.blocking_issues}</b><small>高 / 紧急且未关闭</small></section><section class="card stat"><em>UAT验收通过</em><b>${d.uat_accepted}<span class="sm muted"> / ${d.uat_total}</span></b><small>完成率 ${percentage}%</small></section></div>
<div class="grid2"><section class="card"><h2>上线准备评估</h2><p>${d.ready_for_release?'<span class="pill good">达到演示验收规则</span>':'<span class="pill warn">尚未达到演示验收规则</span>'}</p><p class="muted sm">判断条件：无未关闭高/紧急缺陷、全部8项UAT独立审核通过，且最新数据质量检查没有异常。实际发布还需要独立的安全复核和审批。</p><div class="progress"><div style="width:${percentage}%"></div></div><p class="muted sm">UAT已验收比例 ${percentage}%</p></section><section class="card"><h2>最近一次数据质量检查</h2>${d.latest_quality?`<p style="font-size:29px"><b>${d.latest_quality.total-d.latest_quality.bad_count}</b><span class="muted sm"> / ${d.latest_quality.total} 条记录通过</span></p><p class="muted sm">异常记录 ${d.latest_quality.bad_count} 条</p>`:'<div class="empty">还没有运行检查。前往“数据质量”导入样本。</div>'}</section></div>
<div class="notice warn">${esc(d.note)}。本工具不保存任何患者资料，也不替代企业风险审批和正式上线决策。</div>`}
async function members(){S.members=await api(pid('/members'));return S.members;}
function assigneeSelect(id='owner'){return `<select id="${id}"><option value="">暂不分配</option>${S.members.filter(x=>S.mode==='demo'||x.role.split(',').includes('implementer')).map(x=>`<option value="${esc(x.id)}">${esc(x.name)} · ${esc(roleLabel(x.role))}</option>`).join('')}</select>`}
async function showIssues(){const [items, attachments]=await Promise.all([api(pid('/issues')),api(pid('/attachments')),members()]);const canCreate=can('manager','tester');
$('app').innerHTML=`<div class="row between"><div><h1>问题与整改工单</h1><p class="intro">问题登记 → 责任分配 → 整改 → 独立复测 → 关闭。不能跳过复测直接关闭。</p></div><div class="row"><button id="export" class="btn secondary">另存为 / 导出 CSV</button></div></div>
${canCreate?`<section class="card"><h2>新增质量问题</h2><form id="issue-form"><div class="fields"><div class="field"><label>问题标题 *</label><input id="title" minlength="3" maxlength="160" required placeholder="例如：机构主数据存在重复ID"></div><div class="field"><label>严重程度 *</label><select id="severity"><option value="medium">中</option><option value="high">高</option><option value="critical">紧急</option><option value="low">低</option></select></div><div class="field"><label>负责人员</label>${assigneeSelect()}</div><div class="field"><label>预计完成日期</label><input id="due" type="date"></div></div><div class="field"><label>问题描述</label><textarea id="description" placeholder="描述实际现象、期望结果、影响范围"></textarea></div><p><button class="btn" type="submit">创建整改工单</button></p></form></section>`:''}
<section class="card"><h2>工单列表 <span class="pill">${items.length} 条</span></h2>${items.length?`<div class="table-wrap"><table class="table"><thead><tr><th>问题</th><th>级别</th><th>负责人</th><th>状态</th><th>整改 / 复测</th><th>证据附件</th></tr></thead><tbody>${items.map(x=>`<tr><td><b>${esc(x.title)}</b><div class="muted tiny">${esc(x.id.slice(0,8))} · ${esc(x.description.slice(0,90))}</div></td><td><span class="severe-${esc(x.severity)}">${esc(sevText[x.severity])}</span></td><td>${esc(S.members.find(m=>m.id===x.assignee_id)?.name||'未分配')}</td><td>${pill(x.status)}</td><td><div class="row"><button class="btn small ghost issue-view" data-id="${x.id}">详情</button>${x.status!=='closed'?`<button class="btn small secondary issue-next" data-id="${x.id}" data-state="${x.status}">处理</button>`:''}</div></td><td>${attachments.filter(a=>a.target_type==='issue'&&a.target_id===x.id).map(a=>`<a class="muted sm" target="_blank" rel="noopener" href="${pid(`/attachments/${a.id}/file${a.media_type.startsWith('image/')?'?preview=true':''}`)}">${esc(a.filename)}</a>`).join('<br>')||'<span class="muted tiny">暂无</span>'}<div>${can('manager','tester')||(can('implementer')&&x.assignee_id===S.me.id)?`<input type="file" class="attach-issue" data-id="${x.id}" accept=".jpg,.jpeg,.png,.pdf" aria-label="上传工单证据" style="max-width:145px">`:''}</div></td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">暂无工单，先登记一个问题。</div>'}</section>`;
if(canCreate)$('issue-form').onsubmit=async e=>{e.preventDefault();try{await api(pid('/issues'),{method:'POST',body:JSON.stringify({title:$('title').value,description:$('description').value,severity:$('severity').value,assignee_id:$('owner').value||null,due_date:$('due').value||null})});toast('问题已登记');await showIssues()}catch(ex){error(ex)}};
$('export').onclick=exportCSV;
  document.querySelectorAll('.attach-issue').forEach(el=>el.onchange=()=>uploadEvidence('issue',el.dataset.id,el,showIssues));
document.querySelectorAll('.issue-view').forEach(el=>el.onclick=()=>{const i=items.find(x=>x.id===el.dataset.id);alert(`工单编号：${i.id}\n问题：${i.title}\n状态：${statusText[i.status]}\n描述：${i.description}\n整改说明：${i.resolution_notes||'暂无'}\n复测记录：${i.retest_notes||'暂无'}`)});
document.querySelectorAll('.issue-next').forEach(el=>el.onclick=async()=>{const i=items.find(x=>x.id===el.dataset.id);const states={open:'in_progress',in_progress:'ready_for_retest',ready_for_retest:null};let target=states[i.status];if(i.status==='ready_for_retest'){target=confirm('复测通过并关闭工单？\n点击取消将退回继续整改。')?'closed':'in_progress'}const notes=i.status==='open'?'开始处理':prompt(i.status==='in_progress'?'请输入整改措施及证据（至少5字）':'请输入复测过程、结果及证据（至少5字）');if(notes===null)return;try{await api(pid(`/issues/${i.id}/transition`),{method:'POST',body:JSON.stringify({target_status:target,notes})});toast('状态已更新并写入审计日志');await showIssues()}catch(ex){error(ex)}});
}
async function exportCSV(){
  try{
    let handle=null;
    if('showSaveFilePicker' in window){try{handle=await window.showSaveFilePicker({suggestedName:'VeriFlow_issues.csv',types:[{description:'CSV',accept:{'text/csv':['.csv']}}]})}catch(e){if(e.name==='AbortError'){toast('已取消保存');return} /* browser may disable picker; fall back to download */}}
    const res=await api(pid('/issues.csv'));
    const blob=await res.blob();
    if(handle){const stream=await handle.createWritable();await stream.write(blob);await stream.close();toast(`已保存到你选择的位置：${handle.name}`)}
    else{const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download='VeriFlow_issues.csv';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),5000);toast('已发起下载。实际保存位置由浏览器设置决定，可按 Ctrl+J 查看下载记录。')}
  }catch(e){error(e)}
}
function parseCSV(text){
  const rows=[]; let row=[], cell='', quoted=false;const input=text.replace(/^\uFEFF/,'');
  for(let i=0;i<input.length;i++){const ch=input[i];if(ch==='"'){if(quoted&&input[i+1]==='"'){cell+='"';i++}else quoted=!quoted;} else if(ch===','&&!quoted){row.push(cell);cell=''} else if((ch==='\n'||ch==='\r')&&!quoted){if(ch==='\r'&&input[i+1]==='\n')i++;row.push(cell);if(row.some(v=>v!==''))rows.push(row);row=[];cell=''} else cell+=ch;}
  if(cell||row.length){row.push(cell);rows.push(row)} if(!rows.length)return [];
  const heads=rows.shift().map(x=>x.trim());
  return rows.map(r=>Object.fromEntries(heads.map((key,i)=>[key,r[i]??''])));
}
async function showQuality(){const runs=await api(pid('/quality/runs'));const canCheck=can('manager','tester');
$('app').innerHTML=`<h1>数据质量检查</h1><p class="intro">基于预先定义的业务规则进行完整性、唯一性、取值范围和格式校验。</p><div class="notice warn"><b>隐私约束：</b>仅接受模拟的机构接口数据。禁止上传真实患者信息、客户隐私或单位内部生产数据。仅校验指定6列，最多1000行。</div>
<section class="card"><h2>导入机构接入数据</h2><div class="row"><input aria-label="导入CSV" id="csvfile" type="file" accept=".csv,text/csv"><button id="sample" class="btn secondary">载入12行异常样本</button><button id="sample-clean" class="btn ghost">载入12行合格样本</button>${canCheck?'<button id="run-check" class="btn">执行质量检查</button>':''}</div><p id="csv-note" class="muted sm">样本列：institution_id / institution_name / system_code / status / success_rate / go_live_date</p><div id="quality-result"></div></section>
<section class="card"><h2>历史检查批次</h2>${runs.length?`<div class="table-wrap"><table class="table"><thead><tr><th>检查时间</th><th>总记录数</th><th>异常记录</th></tr></thead><tbody>${runs.map(r=>`<tr><td>${esc(r.created_at.replace('T',' ').slice(0,19))}</td><td>${r.total}</td><td>${r.bad_count}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">暂无检查记录</div>'}</section>`;
$('csvfile').onchange=async e=>{const file=e.target.files[0];if(!file)return;if(file.size>1024*1024){toast('文件太大，仅支持1MB以内的模拟CSV',true);return}try{S.checkedRows=parseCSV(await file.text());$('csv-note').textContent=`已载入 ${S.checkedRows.length} 行；请执行质量检查。`}catch(err){error(err)}};
$('sample').onclick=async()=>{try{const res=await fetch('/sample.csv');S.checkedRows=parseCSV(await res.text());$('csv-note').textContent=`已载入模拟样本 ${S.checkedRows.length} 行（预期3条异常）`;}catch(err){error(err)}};
$('sample-clean').onclick=async()=>{try{const res=await fetch('/sample-clean.csv');S.checkedRows=parseCSV(await res.text());$('csv-note').textContent=`已载入合格模拟样本 ${S.checkedRows.length} 行（预期0条异常）`;}catch(err){error(err)}};
if(canCheck)$('run-check').onclick=async()=>{if(!S.checkedRows){toast('请先选择CSV或载入样本',true);return}try{const out=await api(pid('/quality/check'),{method:'POST',body:JSON.stringify({rows:S.checkedRows})});S.lastRun=out.run_id;$('quality-result').innerHTML=`<hr class="divider"><div class="row"><span class="pill">数据总量 ${out.total}</span><span class="pill good">通过 ${out.passed}</span><span class="pill bad">异常记录 ${out.bad_count}</span><span class="pill">通过率 ${out.pass_rate}%</span></div><p class="small-label" style="margin-top:17px">异常明细</p>${out.errors.length?`<div class="table-wrap"><table class="table"><thead><tr><th>CSV行号</th><th>机构ID</th><th>规则</th></tr></thead><tbody>${out.errors.map(a=>`<tr><td>${a.row}</td><td>${esc(a.institution_id||'空')}</td><td>${esc(a.rule)}</td></tr>`).join('')}</tbody></table></div>`:'<p>未发现异常</p>'}<button id="to-issue" class="btn secondary" style="margin-top:16px">将异常转成整改工单</button>`;$('to-issue').onclick=async()=>{try{const r=await api(pid(`/quality/${S.lastRun}/create-issues`),{method:'POST'});toast(`新建工单 ${r.created} 条，跳过重复 ${r.skipped_duplicates} 条`)}catch(e){error(e)}};}catch(err){error(err)}};
}
async function showUat(){const [items, attachments]=await Promise.all([api(pid('/uat')),api(pid('/attachments'))]);const tester=can('tester');const approver=can('approver');
$('app').innerHTML=`<h1>UAT用户验收测试</h1><p class="intro">由测试人员执行并提供证据，再由不同的验收负责人审核；不能单击勾选即完成验收。</p><div class="notice">共 ${items.length} 项检查，已验收 ${items.filter(x=>x.status==='accepted').length} 项。证据支持文字说明和受控上传PNG/JPG/PDF。禁止上传真实患者资料。</div><section class="card"><h2>业务验收清单</h2>${items.map(c=>`<article class="uat"><div><span class="muted tiny">${esc(c.code)}</span><h3>${esc(c.title)}</h3>${pill(c.status)}${c.evidence?`<p class="sm muted">执行证据：${esc(c.evidence)}</p>`:''}${c.review_notes?`<p class="sm muted">审核记录：${esc(c.review_notes)}</p>`:''}<div class="muted sm">${attachments.filter(a=>a.target_type==='uat'&&a.target_id===String(c.id)).map(a=>`<a target="_blank" rel="noopener" href="${pid(`/attachments/${a.id}/file${a.media_type.startsWith('image/')?'?preview=true':''}`)}">📎 ${esc(a.filename)}</a>`).join(' · ')||'暂无证据附件'}</div>${tester&&c.status!=='accepted'?`<div><label class="muted sm">上传截图或测试报告（5MB以内）<input class="attach-uat" type="file" data-id="${c.id}" accept=".png,.jpg,.jpeg,.pdf"></label></div>`:''}</div><div class="actions">${tester?`<button class="btn small secondary uat-execute" data-id="${c.id}" data-ok="true">测试通过</button><button class="btn small ghost uat-execute" data-id="${c.id}" data-ok="false">测试失败</button>`:''}${approver&&c.status==='passed'?`<button class="btn small uat-review" data-id="${c.id}" data-ok="true">验收通过</button><button class="btn small danger uat-review" data-id="${c.id}" data-ok="false">驳回</button>`:''}</div></article>`).join('')}</section>`;
document.querySelectorAll('.attach-uat').forEach(el=>el.onchange=()=>uploadEvidence('uat',el.dataset.id,el,showUat));
document.querySelectorAll('.uat-execute').forEach(el=>el.onclick=async()=>{const evidence=prompt('请填写测试证据（至少5字），例如：执行日期、测试步骤和截图编号。');if(evidence===null)return;try{await api(pid(`/uat/${el.dataset.id}/execute`),{method:'POST',body:JSON.stringify({passed:el.dataset.ok==='true',evidence})});toast('执行结果已记录');await showUat()}catch(e){error(e)}});
document.querySelectorAll('.uat-review').forEach(el=>el.onclick=async()=>{const yes=el.dataset.ok==='true';const notes=prompt(yes?'审核说明（可选）':'请填写驳回原因（至少5字）');if(notes===null)return;try{await api(pid(`/uat/${el.dataset.id}/review`),{method:'POST',body:JSON.stringify({accepted:yes,notes})});toast('验收记录已保存');await showUat()}catch(e){error(e)}})
}
async function showAudit(){const events=await api(pid('/audit'));$('app').innerHTML=`<h1>项目审计日志</h1><p class="intro">保存关键操作人、时间、事件和对象，用于问题追溯。只展示最近100条。</p><section class="card">${events.length?`<div class="table-wrap"><table class="table"><thead><tr><th>时间</th><th>操作</th><th>操作人</th><th>对象</th></tr></thead><tbody>${events.map(x=>`<tr><td>${esc(x.created_at.replace('T',' ').slice(0,19))}</td><td>${esc(x.action)}</td><td><span class="code">${esc(x.actor_id.slice(0,8))}</span></td><td>${esc(x.entity_type)} · <span class="code">${esc(x.entity_id.slice(0,8))}</span></td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">暂无日志</div>'}</section>`;}
async function showUsers(){if(!S.me.is_admin)return;const users=await api('/api/admin/users');await members();$('app').innerHTML=`<h1>用户与项目权限</h1><p class="intro">当前为${S.mode==='demo'?'演示模式（允许角色兼任）':'正式模式（每人每项目只能有一个业务角色）'}。权限只由服务器配置决定，界面不可临时切换。</p><div class="grid2"><section class="card"><h2>创建用户</h2><form id="userform"><div class="field"><label>姓名</label><input id="username" required></div><div class="field" style="margin-top:12px"><label>邮箱</label><input id="useremail" type="email" required></div><p><button class="btn" type="submit">创建临时账号</button></p></form><div id="user-result"></div></section><section class="card"><h2>分配当前项目角色</h2><form id="memberform"><div class="field"><label>用户</label><select id="memberuser">${users.map(x=>`<option value="${x.id}">${esc(x.name)} (${esc(x.email)})</option>`).join('')}</select></div><div class="field" style="margin-top:12px"><label>角色</label><select id="memberrole">${Object.entries(roleText).filter(([k])=>k!=='admin').map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select>${S.mode==='demo'?'<p class="muted sm">演示模式可用英文逗号填写多个角色，如 manager,tester；执行人与审核人仍不能为同一人。</p><input id="extra-roles" placeholder="例如 manager,tester （可选）">':''}</div><p><button class="btn secondary" type="submit">保存项目角色</button></p></form></section></div><section class="card"><h2>当前用户清单</h2><div class="table-wrap"><table class="table"><thead><tr><th>姓名</th><th>邮箱</th><th>平台身份</th><th>当前项目角色</th><th>管理</th></tr></thead><tbody>${users.map(u=>`<tr><td>${esc(u.name)}</td><td>${esc(u.email)}</td><td>${u.is_admin?'系统管理员':'普通账户'}</td><td>${esc(roleLabel(S.members.find(m=>m.id===u.id)?.role)||'未加入')}</td></tr>`).join('')}</tbody></table></div></section>`;
$('userform').onsubmit=async e=>{e.preventDefault();try{const u=await api('/api/admin/users',{method:'POST',body:JSON.stringify({email:$('useremail').value,name:$('username').value})});$('user-result').innerHTML=`<div class="notice warn"><strong>临时密码仅此一次展示，请安全传达。</strong><p class="pre" id="temp-pass"></p></div>`;$('temp-pass').textContent=u.temporary_password;const option=document.createElement('option');option.value=u.id;option.textContent=`${$('username').value} (${u.email})`; $('memberuser').appendChild(option);$('memberuser').value=u.id;toast('账号已创建并已选中，继续分配项目角色。')}catch(e){error(e)}};
$('memberform').onsubmit=async e=>{e.preventDefault();try{await api(pid('/members'),{method:'POST',body:JSON.stringify({user_id:$('memberuser').value,role:($('extra-roles')?.value.trim()||$('memberrole').value)})});toast('项目角色已更新');await showUsers()}catch(err){error(err)}};
document.querySelectorAll('.user-disable').forEach(b=>b.onclick=async()=>{if(!confirm('确定停用此用户并撤销其登录会话？'))return;try{await api(`/api/admin/users/${b.dataset.id}/deactivate`,{method:'POST'});toast('用户已停用');await showUsers()}catch(e){error(e)}});
}
async function uploadEvidence(type, target, input, after){
  const file=input.files[0];if(!file)return;
  if(file.size>5*1024*1024){toast('文件超过5MB上限',true);return;}
  if(!/\.(png|jpe?g|pdf)$/i.test(file.name)){toast('只接受PNG、JPG或PDF',true);return;}
  try{const form=new FormData();form.append('upload',file);
    const a=await api(pid(`/attachments/${type}/${target}`),{method:'POST',body:form});
    toast(`已保存证据：${a.filename}（服务端受控存储）`);await after();}
  catch(ex){error(ex)}
}
async function showRelease(){
  const d=await api(pid('/release'));
  const cs=d.checks;const eligible=!cs.blockers.length;
  const manager=can('manager'),approver=can('approver');
  const recent=d.requests[0];const pending=d.requests.find(x=>x.status==='submitted');
  const statusLabel={submitted:'待审核',approved:'流程批准',rejected:'已驳回'};
  $('app').innerHTML=`<h1>上线审批与质量门禁</h1><p class="intro">这是质量管理流程演示。审批通过≠企业生产环境可安全发布。</p>
    <div class="notice ${eligible?'good':'warn'}">${eligible?'质量规则检查通过，可提交审批':'尚未满足提交条件：'+cs.blockers.map(esc).join('；')}<p class="muted sm">低/中等级遗留工单 ${cs.residual_issues} 项；UAT ${cs.uat_accepted}/${cs.uat_total}；最新检查批次 ${esc(cs.latest_quality_run||'暂无')}</p></div>
    <section class="card"><h2>流程要求与责任分工</h2><p>项目经理提交：安全复核、回滚验证、备份恢复演练、交付文档、运维交接并填写证据编号。业务验收人独立复核。审批不能由同一个账号完成。</p><p class="muted sm">本版本只记录人员确认和证据编号，不能自动核验外部报告、真实回滚演练或合规结论。</p></section>
    ${manager?`<section class="card"><h2>提交上线准备审批</h2><form id="release-form">
      ${[['security_reviewed','已完成安全复核'],['rollback_plan_tested','已验证回滚方案'],['backup_restore_tested','已完成备份与恢复演练'],['delivery_documents_ready','交付文档齐全'],['operations_handover_ready','已完成运维交接']].map(([k,v])=>`<label class="check-line"><input type="checkbox" name="${k}" required> ${v}</label>`).join('')}
      <div class="field"><label>证明材料编号或附件引用（至少12字符，不能填患者资料）</label><textarea id="release-evidence" required minlength="12" placeholder="如 SEC-001 / RESTORE-01 / UAT-2026-11"></textarea></div>
      <div class="field"><label>低/中级遗留问题的风险接受说明（存在时必填）</label><textarea id="release-residual" placeholder="说明影响、责任人及后续整改安排"></textarea></div>
      <button class="btn" type="submit" ${eligible&&!pending?'':'disabled'}>提交审批</button></form></section>`:''}
    ${pending&&approver?`<section class="card"><h2>当前待审核：${esc(pending.id.slice(0,10))}</h2><p>申请人：${esc(pending.requested_by.slice(0,8))}；资料编号：${esc(pending.evidence_reference)}</p><div class="field"><label>审核意见（不少于8字）</label><textarea id="release-review-notes"></textarea></div><div class="row"><button class="btn release-review" data-ok="true">批准流程</button><button class="btn danger release-review" data-ok="false">驳回申请</button></div></section>`:''}
    <section class="card"><h2>历史审批记录</h2>${d.requests.length?`<div class="table-wrap"><table class="table"><thead><tr><th>申请时间</th><th>状态</th><th>申请人</th><th>审核意见</th></tr></thead><tbody>${d.requests.map(x=>`<tr><td>${esc(x.requested_at.replace('T',' ').slice(0,19))}</td><td>${esc(statusLabel[x.status])}</td><td>${esc(x.requested_by.slice(0,8))}</td><td>${esc(x.review_notes||'—')}</td></tr>`).join('')}</tbody></table></div>`:'<p class="muted">目前没有审批记录</p>'}</section>`;
  if(manager)$('release-form').onsubmit=async e=>{e.preventDefault();const obj={evidence_reference:$('release-evidence').value,residual_risk_notes:$('release-residual').value};
    for(const k of ['security_reviewed','rollback_plan_tested','backup_restore_tested','delivery_documents_ready','operations_handover_ready'])obj[k]=$('release-form').elements.namedItem(k).checked;
    try{await api(pid('/release'),{method:'POST',body:JSON.stringify(obj)});toast('已提交上线流程审批，请由另一名验收负责人审核');await showRelease()}catch(ex){error(ex)}};
  document.querySelectorAll('.release-review').forEach(el=>el.onclick=async()=>{const notes=$('release-review-notes').value;try{await api(pid(`/release/${pending.id}/review`),{method:'POST',body:JSON.stringify({accepted:el.dataset.ok==='true',notes})});toast('审核结果已记录');await showRelease()}catch(e){error(e)}});
}
boot();
