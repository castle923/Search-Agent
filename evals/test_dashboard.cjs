const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
new Function(script);
const elements = {};
const context = vm.createContext({
  $: id => elements[id] ||= {style: {}, textContent: '', innerHTML: ''},
  TextDecoder,
});
vm.runInContext(script.slice(script.indexOf('function renderCharts(')), context);
context.renderCharts([{days_left:0}, {days_left:7}, {days_left:14}, {days_left:30}, {days_left:31}], 5);
assert.equal(elements.validationRate.textContent, '50%');
assert.equal(elements.legendValid.textContent, 5);
assert.equal((elements.deadlineChart.innerHTML.match(/<title>[^<]*1건<\/title>/g) || []).length, 5);
context.renderCharts([], 0);
assert.equal(elements.validationRate.textContent, '—');
assert.ok(elements.deadlineChart.innerHTML.includes('표시할 유효 공고가 없습니다'));
context.renderCharts([], 3);
assert.equal(elements.validationRate.textContent, '0%');
vm.runInContext(script.slice(script.indexOf('async function stream('), script.indexOf('function onEvent(')), context);
(async () => {
  context.fetch = async () => new Response('{"message":"한글"}\n{"done":true}');
  const events = [];
  await context.stream('/test', {}, e => events.push(e));
  assert.equal(events[0].message, '한글');
  assert.equal(events[1].done, true);
  context.fetch = async () => new Response('', {status: 500});
  await assert.rejects(context.stream('/test', {}, () => {}), /HTTP 500/);
  console.log('PASS: dashboard syntax, deadline buckets, empty states, ratios, NDJSON final line, HTTP errors');
})().catch(e => { console.error(e); process.exitCode = 1; });
