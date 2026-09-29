// JavaScript unit tests with a simulated DOM/storage, not a browser verification.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname, '../app/static/workspace.js'), 'utf8');

function workspace(storage = new Map(), userId = 1, monacoEnabled = true) {
  const listeners = {};
  const elements = {};
  const make = id => elements[id] = {id, value: '', hidden: true, dataset: {}, textContent: '',
    listeners: {}, addEventListener(event, fn) { this.listeners[event] = fn; }};
  ['workspace-config', 'lang', 'result', 'editor-fallback', 'draft-status', 'theme', 'input-mode', 'custom', 'editor', 'run', 'submit'].forEach(make);
  const languages = Object.fromEntries(['cpp', 'c', 'python', 'java'].map(language => [language, {starter: `${language} starter`, monaco: language}]));
  elements['workspace-config'].textContent = JSON.stringify({userId, problemId: 100, languages});
  elements.lang.value = 'cpp';
  const document = {documentElement: {dataset: {}}, hidden: false,
    getElementById: id => elements[id], addEventListener: (event, fn) => listeners[event] = fn,
    querySelector: () => ({dataset: {}}), querySelectorAll: () => []};
  let editor;
  const sandbox = {document, localStorage: {getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value)},
    setTimeout: () => 1, clearTimeout: () => {}, matchMedia: () => ({matches: false}),
    addEventListener: (event, fn) => listeners[event] = fn};
  if (monacoEnabled) {
    sandbox.monaco = {editor: {create: (_element, options) => editor = {
      value: options.value, getValue() { return this.value; }, setValue(value) { this.value = value; },
      getModel() { return {}; }, onDidChangeModelContent() {}, layout() {}},
      setModelLanguage() {}, setTheme() {}}};
    sandbox.require = (_modules, loaded) => loaded(); sandbox.require.config = () => {};
  }
  vm.runInNewContext(script, sandbox);
  return {storage, elements, edit(value) { if (editor) editor.value = value; else elements['editor-fallback'].value = value; },
    source() { return editor ? editor.value : elements['editor-fallback'].value; },
    change(language) { elements.lang.value = language; elements.lang.listeners.change(); },
    pagehide() { listeners.pagehide(); }};
}

test('Monaco language switch and refresh retain each language draft', () => {
  const page = workspace();
  page.edit('cpp draft'); page.change('java'); page.edit('java draft'); page.change('cpp');
  assert.equal(page.source(), 'cpp draft');
  page.change('java'); assert.equal(page.source(), 'java draft'); page.pagehide();
  const reload = workspace(page.storage);
  assert.equal(reload.elements.lang.value, 'java'); assert.equal(reload.source(), 'java draft');
});

test('Drafts do not cross users and are persisted when navigating away', () => {
  const page = workspace(); page.edit('private draft'); page.pagehide();
  assert.equal(workspace(page.storage, 1).source(), 'private draft');
  assert.equal(workspace(page.storage, 2).source(), 'cpp starter');
  assert.equal(page.storage.get('draft:1:100:cpp'), 'private draft');
});

test('CDN fallback textarea retains drafts across language changes', () => {
  const page = workspace(new Map(), 1, false);
  assert.equal(page.elements['editor-fallback'].hidden, false);
  page.edit('fallback cpp'); page.change('python'); page.edit('fallback python'); page.pagehide();
  const next = workspace(page.storage, 1, false);
  assert.equal(next.source(), 'fallback python'); next.change('cpp'); assert.equal(next.source(), 'fallback cpp');
});
