// オフラインHTMLの操作が、実際の反復データを表示することを検証する。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const output = path.resolve(__dirname, '..', process.argv[2] || 'optimization_output');
const report = JSON.parse(fs.readFileSync(path.join(output, 'result.json'), 'utf8'));
const page = fs.readFileSync(path.join(output, 'learning_graphs.html'), 'utf8');
const selected = page.match(/<option value="(\d+)" selected>/);
assert.ok(selected, '採用試行が初期選択されている');
assert.equal(Number(selected[1]), report.selected_trial);
const elements = Object.fromEntries(['trial', 'iteration', 'trace', 'step-state'].map(id => [id, {
  value: id === 'trial' ? selected[1] : '0', max: 0,
  innerHTML: '', textContent: '', listeners: {},
  addEventListener(event, listener) { this.listeners[event] = listener; },
}]));
const script = page.match(/<script>([\s\S]*?)<\/script>/)[1];
vm.runInNewContext(script, { document: { getElementById: id => elements[id] } });
const trial = report.trials[report.selected_trial];
assert.equal(Number(elements.iteration.max), trial.history.length - 1);
assert.ok(elements['step-state'].textContent.includes('反復 0 /'));
assert.ok(elements['step-state'].textContent.includes((100*trial.history[0].forward_efficiency).toFixed(6)));
elements.iteration.value = String(trial.history.length - 1);
elements.iteration.listeners.input();
assert.ok(elements['step-state'].textContent.includes((100*report.best.forward_efficiency).toFixed(6)));
assert.ok(elements['step-state'].textContent.includes('可行'));
const initialSvg = elements.trace.innerHTML;
const failure = report.trials.find(t => !t.solver_success)
  || report.trials.find(t => t.start_index !== report.selected_trial);
assert.ok(failure, '別の初期値の試行も確認できる');
elements.trial.value = String(failure.start_index);
elements.trial.listeners.change();
assert.equal(Number(elements.iteration.value), 0);
assert.equal(Number(elements.iteration.max), failure.history.length-1);
assert.notEqual(elements.trace.innerHTML, initialSvg);
assert.ok(elements['step-state'].textContent.includes(failure.solver_message));
assert.equal((page.match(/data:image\/png;base64,/g) || []).length, 8);
console.log('PASS: 初期値選択、反復スライダー、数値表示、8種類の画像');
