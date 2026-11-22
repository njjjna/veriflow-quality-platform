'use strict';
// Real form handler under a minimal DOM; this is not browser UAT.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../app/static/app.js'), 'utf8');
const keys = ['security_reviewed', 'rollback_plan_tested', 'backup_restore_tested',
  'delivery_documents_ready', 'operations_handover_ready'];

async function exercise(shouldReject) {
  const requests = [], nodes = new Map();
  for (const id of ['app', 'toast', 'release-form', 'release-evidence', 'release-residual'])
    nodes.set(id, {innerHTML: '', textContent: '', style: {}, value: ''});
  nodes.get('release-evidence').value = 'SEC-DEMO / RESTORE-DEMO / UAT-DEMO';
  nodes.get('release-residual').value = '模拟遗留问题已登记并由负责人跟进';
  nodes.get('release-form').elements = {namedItem: name => {
    assert.ok(keys.includes(name)); return {checked: true};
  }};
  const sandbox = {
    document: {getElementById: id => nodes.get(id) || null, querySelectorAll: () => []},
    window: {}, setTimeout: () => 1, clearTimeout() {}, FormData: class {},
    fetch: async (url, opts) => {
      requests.push({url, opts});
      const rejected = shouldReject && opts.method === 'POST';
      return {ok: !rejected, status: rejected ? 409 : 200,
        headers: {get: () => 'application/json'}, json: async () => rejected
          ? {detail: '模拟门禁重新检查失败'}
          : {checks: {blockers: [], residual_issues: 1, uat_accepted: 8, uat_total: 8}, requests: []}};
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(source.replace(/boot\(\);\s*$/, ''), sandbox);
  await vm.runInContext("S.pid='demo-project'; S.role='manager'; S.mode='demo'; S.csrf='test-csrf'; showRelease()", sandbox);
  let prevented = false;
  await nodes.get('release-form').onsubmit({preventDefault() { prevented = true; }});
  assert.ok(prevented);
  const posts = requests.filter(r => r.opts.method === 'POST');
  assert.equal(posts.length, 1, 'submit must reach the API instead of failing on a null checkbox');
  assert.equal(posts[0].url, '/api/projects/demo-project/release');
  assert.equal(posts[0].opts.headers['X-CSRF-Token'], 'test-csrf');
  const payload = JSON.parse(posts[0].opts.body);
  for (const k of keys) assert.equal(payload[k], true);
  assert.equal(payload.evidence_reference, nodes.get('release-evidence').value);
  assert.equal(payload.residual_risk_notes, nodes.get('release-residual').value);
  return {nodes, requests};
}
test('release submits confirmations, evidence and risk notes', async () => {
  const {nodes, requests} = await exercise(false);
  assert.match(nodes.get('toast').textContent, /已提交/);
  assert.equal(requests.filter(r => (r.opts.method || 'GET') === 'GET').length, 2);
});
test('release displays a server rejection without claiming success', async () => {
  const {nodes} = await exercise(true);
  assert.equal(nodes.get('toast').textContent, '模拟门禁重新检查失败');
});
