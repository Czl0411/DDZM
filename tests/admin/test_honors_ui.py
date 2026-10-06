from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "src/dzmm_bot/admin/static/honors.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is required for UI checks")
def test_honor_permissions_escaping_and_preview_invalidation():
    javascript = r'''
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const nodes = new Map();
function node(selector) {
  if (!nodes.has(selector)) nodes.set(selector, {
    value: "2026-10-05", innerHTML: "", disabled: false, listeners: {},
    addEventListener(event, callback) { this.listeners[event] = callback; },
    replaceChildren() { this.innerHTML = ""; },
  });
  return nodes.get(selector);
}
const context = vm.createContext({
  Intl, Date, URLSearchParams, identity: {role: "admin"},
  document: {querySelector: node, querySelectorAll: () => []},
  employeeProfileModal: {dataset: {platformId: "one"}},
  escapeHtml: (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll('"', "&quot;"),
  setResult: () => {}, formatHeartbeat: String,
  runMutation: async (button, label, callback) => callback(),
});
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
context.config = {
  version: 1, effective_week: "2026-10-12", first_week: "2099-01-05", current: {enabled: true},
  configuration: {enabled: true, announce: false, group_ids: ["group"], announcement_group_id: null,
    rules: [{key: "title", name: '<img src=x onerror="bad()">', enabled: true,
      minimum: 1, sort_order: 1, public_score: true, description: "<script>bad()</script>"}]},
  definitions: [{key: "title", supported: true}],
};
context.groups = [{id: "group", name: "<unsafe>"}];
vm.runInContext("renderHonorConfiguration(config, groups)", context);
assert.ok(node("#honors-panel").innerHTML.includes("<fieldset disabled>"));
assert.ok(!node("#honors-panel").innerHTML.includes("<img src=x"));
assert.ok(!node("#honors-panel").innerHTML.includes("<script>bad()"));
assert.ok(node("#honors-panel").innerHTML.includes('value="2099-01-05"'));
assert.ok(node("#honors-panel").innerHTML.includes('id="honor-announcement-time" type="time" value="09:00" required'));
context.config.configuration.announcement_time = "08:45";
vm.runInContext("renderHonorConfiguration(config, groups)", context);
assert.ok(node("#honors-panel").innerHTML.includes('id="honor-announcement-time" type="time" value="08:45" required'));
const report = {week_start: "2026-10-05", config_version: 1, can_settle: true,
  preview_digest: "a".repeat(64), entries: []};
(async () => {
  context.identity.role = "super_admin";
  const form = node("#honor-config-form");
  const fields = {
    "#honor-enabled": {checked: true}, "#honor-announce": {checked: true},
    "#honor-announcement-time": {value: "10:15"}, "#honor-announcement-group": {value: "group"},
  };
  form.querySelector = (selector) => fields[selector] || node(selector);
  form.querySelectorAll = () => [];
  vm.runInContext("honorConfiguration = config", context);
  context.loadHonors = async () => {};
  context.eventForm = form;
  let savedConfiguration;
  context.requestGame = async (path, options) => { savedConfiguration = JSON.parse(options.body); };
  await vm.runInContext("saveHonorConfiguration({preventDefault() {}, currentTarget: eventForm})", context);
  assert.equal(savedConfiguration.announcement_time, "10:15");
  context.identity.role = "admin";
  context.requestGame = async () => report;
  await vm.runInContext("previewHonorPeriod()", context);
  assert.equal(node("#honor-settle-button").disabled, true);
  context.identity.role = "super_admin";
  await vm.runInContext("previewHonorPeriod()", context);
  assert.equal(node("#honor-settle-button").disabled, false);
  node("#honor-week").listeners.change();
  assert.equal(node("#honor-settle-button").disabled, true);
  assert.equal(vm.runInContext("honorPreview", context), null);
  let resolve;
  context.requestGame = () => new Promise((done) => { resolve = done; });
  const pending = vm.runInContext("previewHonorPeriod()", context);
  node("#honor-week").value = "2026-10-12";
  resolve(report);
  await pending;
  assert.equal(vm.runInContext("honorPreview", context), null);
  assert.equal(node("#honor-settle-button").disabled, true);
  context.requestGame = async () => { throw new Error("统计数据改变"); };
  await vm.runInContext("previewHonorPeriod()", context);
  assert.equal(vm.runInContext("honorPreview", context), null);
  assert.equal(node("#honor-settle-button").disabled, true);
  context.employeeProfileModal.dataset.platformId = "one";
  context.requestGame = async (path) => path.includes("/users/") ? {
    name: "糯糯", user_id: "uuid-one", equipped: "最有魅力帅哥", items: [], history_counts: {charm_m: 1},
  } : {items: [{week_start: "2026-10-05", name: "<unsafe-title>", active: true}]};
  await vm.runInContext('loadEmployeeHonors("one")', context);
  assert.equal(node("#employee-profile-modal-title").textContent, "编辑档案：糯糯【荣誉称号：最有魅力帅哥】");
  assert.ok(!node("#employee-honors-history").innerHTML.includes("<unsafe-title>"));
  let finishOld;
  context.requestGame = () => new Promise((done) => { finishOld = done; });
  const oldEmployee = vm.runInContext('loadEmployeeHonors("one")', context);
  context.employeeProfileModal.dataset.platformId = "two";
  node("#employee-profile-modal-title").textContent = "第二位员工";
  finishOld({name: "错误旧响应", user_id: "one", items: [], history_counts: {}});
  await oldEmployee;
  assert.equal(node("#employee-profile-modal-title").textContent, "第二位员工");
})().catch((error) => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([shutil.which("node"), "-e", javascript, str(SCRIPT)],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
