from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "src/dzmm_bot/admin/static/admin.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is required for the isolated UI checks")
def test_shop_preview_risk_controls_escape_errors_and_preserve_zero():
    javascript = r'''
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const script = fs.readFileSync(process.argv[1], "utf8");
const helpers = script.slice(script.indexOf("let shopCatalogItems ="), script.indexOf("async function loadShop("));
const confirmButton = {disabled: false};
const risks = [{checked: false}];
const panel = {hidden: true, innerHTML: "", scrollIntoView() {},
  querySelector: () => confirmButton, querySelectorAll: () => risks};
const context = {
  document: {querySelector: (selector) => selector === "#shop-import-preview" ? panel : {click() {}}},
  escapeHtml: (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;"),
};
vm.createContext(context);
vm.runInContext(helpers, context);
context.preview = {
  batch_id: "batch", summary: {create: 0, update: 1, unchanged: 0, delete: 0, restore: 0, errors: 0, error_rows: 0},
  errors: [], warnings: [{code: "risk:2", row: 2, message: "风险"}], changes: [],
};
vm.runInContext("renderShopPreview(preview)", context);
assert.equal(confirmButton.disabled, true);
risks[0].checked = true;
vm.runInContext("updateShopConfirmButton()", context);
assert.equal(confirmButton.disabled, false);
context.preview.errors.push({sheet: "商品列表", row: 2, column: "名称", value: "<script>", message: "<img src=x>", suggestion: "<svg onload=x>"});
context.preview.summary.errors = 1;
vm.runInContext("renderShopPreview(preview)", context);
assert.equal(confirmButton.disabled, true);
assert(panel.innerHTML.includes("&lt;svg onload=x&gt;"));
assert(!panel.innerHTML.includes("<svg onload=x>"));
context.inputs = [
  {dataset: {effectParameter: "reward"}, value: "0"},
  {dataset: {effectParameter: "quota"}, value: ""},
  {dataset: {effectParameter: "template"}, value: "adult_flirt"},
];
context.container = {querySelectorAll: () => context.inputs};
const values = vm.runInContext("readShopEffectFields(container)", context);
assert.equal(values.reward, 0);
assert.equal(values.quota, null);
assert.equal(values.template, "adult_flirt");
vm.runInContext("invalidateShopPreview()", context);
assert.equal(panel.hidden, true);
assert.equal(vm.runInContext("shopChangePreview", context), null);
'''
    result = subprocess.run([shutil.which("node"), "-e", javascript, str(SCRIPT)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is required for JS syntax checks")
def test_admin_javascript_syntax():
    result = subprocess.run([shutil.which("node"), "--check", str(SCRIPT)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
