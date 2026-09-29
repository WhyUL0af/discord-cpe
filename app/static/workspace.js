/* Drafts are scoped to the authenticated user, database problem ID and language. */
(() => {
  'use strict';
  const config = JSON.parse(document.getElementById('workspace-config').textContent);
  const byId = id => document.getElementById(id);
  const lang = byId('lang'), result = byId('result'), fallback = byId('editor-fallback');
  let editor, saveTimer, busy = false;
  const preferenceKey = `draft-language:${config.userId}:${config.problemId}`;
  const draftKey = language => `draft:${config.userId}:${config.problemId}:${language}`;
  function read(key) { try { return localStorage.getItem(key); } catch { return null; } }
  function write(key, value) { try { localStorage.setItem(key, value); return true; } catch { return false; } }
  const preferred = read(preferenceKey);
  if (config.languages[preferred]) lang.value = preferred;
  function draft(language) { return read(draftKey(language)) ?? config.languages[language].starter; }
  function source() { return editor ? editor.getValue() : fallback.value; }
  function save() {
    clearTimeout(saveTimer);
    byId('draft-status').textContent = write(draftKey(lang.value), source()) ? '草稿已儲存' : '無法儲存草稿';
    write(preferenceKey, lang.value);
  }
  function changed() { clearTimeout(saveTimer); saveTimer = setTimeout(save, 300); }
  function theme() { return document.documentElement.dataset.theme === 'light' ? 'vs' : 'vs-dark'; }
  const savedTheme = read('cpe-theme');
  document.documentElement.dataset.theme = savedTheme || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  byId('theme').onclick = () => {
    document.documentElement.dataset.theme = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    write('cpe-theme', document.documentElement.dataset.theme);
    if (editor) monaco.editor.setTheme(theme());
  };
  let activeLanguage = lang.value;
  lang.addEventListener('change', () => {
    // Save under the previous language before replacing the editor model.
    write(draftKey(activeLanguage), source());
    activeLanguage = lang.value;
    if (editor) {
      monaco.editor.setModelLanguage(editor.getModel(), config.languages[lang.value].monaco);
      editor.setValue(draft(lang.value));
    } else fallback.value = draft(lang.value);
    save();
  });
  addEventListener('pagehide', save);
  addEventListener('beforeunload', save);
  document.addEventListener('visibilitychange', () => { if (document.hidden) save(); });
  function setView(view) {
    document.querySelector('.workspace').dataset.view = view;
    document.querySelectorAll('[data-view]').forEach(button => {
      if (button.tagName === 'BUTTON') button.setAttribute('aria-pressed', String(button.dataset.view === view));
    });
    if (editor) editor.layout();
  }
  document.querySelectorAll('.workspace-tabs button').forEach(button => button.onclick = () => setView(button.dataset.view));
  byId('input-mode').onchange = () => { byId('custom').hidden = byId('input-mode').value !== 'custom'; };
  function buttons() { byId('run').disabled = busy; byId('submit').disabled = busy; }
  function useFallback() {
    if (editor) return;
    byId('editor').hidden = true;
    fallback.hidden = false;
    fallback.value = draft(lang.value);
    fallback.oninput = changed;
    byId('draft-status').textContent = 'Monaco 無法載入，使用文字編輯器';
    buttons();
  }
  if (typeof require === 'undefined') useFallback();
  else {
    require.config({paths: {vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min/vs'}});
    require(['vs/editor/editor.main'], () => {
      // Preserve fallback edits if the CDN finished loading after a timeout.
      const value = fallback.hidden ? draft(lang.value) : fallback.value;
      editor = monaco.editor.create(byId('editor'), {value, language: config.languages[lang.value].monaco,
        theme: theme(), fontSize: 14, automaticLayout: true, minimap: {enabled: false}});
      fallback.hidden = true; byId('editor').hidden = false;
      editor.onDidChangeModelContent(changed);
      buttons();
    }, useFallback);
    setTimeout(useFallback, 12000);
  }
  async function jsonRequest(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '請求失敗，請確認程式大小與登入狀態');
    return data;
  }
  function show(data, isRun) {
    let text = (data.mock ? '[Development Mock：未執行程式碼]\n' : '') + data.result;
    if (data.passed_tests != null) text += `\nPassed Tests: ${data.passed_tests} / ${data.total_tests}`;
    if (data.runtime_ms != null) text += `\nRuntime: ${data.runtime_ms} ms`;
    if (data.memory_kb != null) text += `\nMemory: ${data.memory_kb} KB`;
    if (data.language) text += `\nLanguage: ${data.language}`;
    if (data.submitted_at) text += `\nSubmitted: ${data.submitted_at}`;
    if (data.compiler_message) text += `\nCompiler:\n${data.compiler_message}`;
    if (isRun) text += `\nstdout:\n${data.stdout || ''}\nstderr:\n${data.stderr || ''}`;
    result.textContent = text;
    if (data.submission_id) {
      const link = document.createElement('a'); link.href = `/submissions/${data.submission_id}`;
      link.textContent = '查看提交詳情';
      result.append(document.createTextNode('\n'), link);
    }
  }
  async function send(isRun) {
    if (busy) return;
    busy = true; buttons(); save(); setView('result'); result.className = '';
    result.textContent = isRun ? 'Running sample/custom input…' : 'Queued · Judging…';
    try {
      let data = await jsonRequest(`/api/problems/${config.problemId}/${isRun ? 'run' : 'submit'}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({language: lang.value, code: source(), input: byId('custom').value, input_mode: byId('input-mode').value})
      });
      if (!isRun) {
        const id = data.submission_id;
        for (let i = 0; i < 120 && data.status !== 'finished'; i++) {
          result.textContent = `${data.mock ? '[Development Mock]\n' : ''}${data.status} · Judging…`;
          await new Promise(resolve => setTimeout(resolve, 300));
          data = await jsonRequest(`/api/submissions/${id}`);
        }
        if (data.status !== 'finished') throw new Error('評測尚未完成，請到提交紀錄查詢。');
      }
      show(data, isRun);
    } catch (error) { result.textContent = error.message; result.className = 'error'; }
    finally { busy = false; buttons(); }
  }
  byId('run').onclick = () => send(true);
  byId('submit').onclick = () => send(false);
})();
