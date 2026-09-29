"""Server rendering for the workspace; only a public problem projection reaches JS."""
import html
import json
from app.providers.judge_provider import LANGUAGES


def render_workspace(problem, user_id):
    esc = lambda value: html.escape(str(value or ""), quote=True)
    config = json.dumps({"problemId": problem.id, "userId": user_id, "languages": LANGUAGES}, ensure_ascii=False).replace("<", "\\u003c")
    options = "".join(f'<option value="{key}">{esc(value["label"])}</option>' for key, value in LANGUAGES.items())
    source = f'<a href="{esc(problem.external_url)}" target="_blank" rel="noopener">原始題目 ↗</a>' if problem.external_url and problem.external_url.startswith(("http://", "https://")) else ""
    return f'''<div class="workspace-tabs" role="group" aria-label="工作區">
      <button data-view="problem" aria-pressed="true">Problem</button><button data-view="code" aria-pressed="false">Code</button><button data-view="result" aria-pressed="false">Result</button>
    </div><div class="workspace" data-view="problem">
    <section class="problem-pane" aria-label="題目"><h1>UVa {problem.problem_number} · {esc(problem.title)}</h1>
    <p class="muted">{esc(problem.difficulty or "未標註難度")} · {esc(problem.source)}</p>
    <h2>Description</h2><pre>{esc(problem.statement or "目前尚未匯入題目敘述，請查看原始題目。")}</pre>
    <h2>Input</h2><pre>{esc(problem.input_description)}</pre><h2>Output</h2><pre>{esc(problem.output_description)}</pre>
    <h2>Sample Input</h2><pre id="sample-in">{esc(problem.sample_input)}</pre>
    <h2>Sample Output</h2><pre>{esc(problem.sample_output)}</pre>
    <p>Time limit: {esc(problem.time_limit)} ms · Memory limit: {esc(problem.memory_limit)} KB</p>{source}</section>
    <section class="code-pane" aria-label="程式碼"><div class="actions"><label for="lang">Language</label><select id="lang">{options}</select><button id="theme" type="button">切換主題</button><span id="draft-status" class="muted" role="status"></span></div>
    <div id="editor" aria-label="Code editor"></div><textarea id="editor-fallback" aria-label="Code editor fallback" hidden></textarea>
    </section><section class="console-pane" aria-label="執行結果"><div class="actions">
    <label for="input-mode">Testcase</label><select id="input-mode"><option value="sample">Sample Input</option><option value="custom">Custom Input</option></select>
    <button id="run" disabled>Run</button><button id="submit" class="primary" disabled>Submit</button></div>
    <textarea id="custom" aria-label="Custom Input" placeholder="Custom input（可留空）" hidden></textarea>
    <pre id="result" role="status" aria-live="polite">選擇語言並開始作答。</pre></section></div>
    <script id="workspace-config" type="application/json">{config}</script><script src="/static/workspace.js" defer></script>'''
