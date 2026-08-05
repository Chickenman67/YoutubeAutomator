# Review Dashboard Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for each task below. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local HTML + vanilla-JS review dashboard (served by the existing #18 Flask backend) that lists pending Videos with thumbnails, expands to preview mid-form + Shorts with full script / fact-check / metadata, and approves/rejects individually and in bulk.

**Architecture:** Two layers: (1) `src/dashboard/frontend/core.mjs` — pure, dependency-free functions (HTML rendering, selection state, decision submission against the #18 API) that are unit-tested with Node 24's stdlib `node:test` runner (no npm packages); (2) `src/dashboard/frontend/app.mjs` — thin DOM wiring that calls `core.mjs` and `fetch`. Flask serves these static files (`static_url_path=/static`) plus `GET /` → `index.html`.

**Tech Stack:** Python 3.14 + Flask 3.1.3 (already installed) for serving; vanilla HTML/CSS/ES-module JS; Node 24 `node:test` + `node:assert` for JS logic tests; pytest for Flask-serve tests. No build step, no npm deps.

**Design context:** Consumes the #18 API exactly: `GET /pending` → `{videos:[{video_id,topic,title,thumbnail}]}`; `GET /video/{id}` → `{video_id,topic,metadata{title,description,tags,category},fact_check{topic,results[{claim,confidence,flagged}],low_confidence},script{scenes[{scene_id,narration,facts,key_visual_keywords}]},assets{midform,shorts[],thumbnail}}`; `POST /approve|reject/{id}` → `{video_id,status}`; `GET /video/{id}/asset/{filename}` serves media. Spec (`docs/spec.md` Review Dashboard section): "Local HTML + JavaScript (Flask backend for file serving)"; runs locally via `python src/dashboard/app.py`, opens to localhost:5000.

**Why Node tests in a Python repo:** AC 7 explicitly requires tests for "UI interactions, API calls, state updates", which are JS behavior. Node 24 is installed and its `node:test` runner is stdlib (zero npm dependencies), so this satisfies the AC with the lowest possible footprint. Python pytest still covers Flask serving.

## Global Constraints

- Python suite runner: `venv\Scripts\python -m pytest -q`. JS suite runner: `node --test "tests/dashboard/*.test.mjs"` (glob form — a bare directory arg mis-resolves on Windows). Run BOTH for full verification.
- Follow repo conventions for the Flask side (dataclasses, injected seams, `logging.getLogger(__name__)`, no comments). Frontend is vanilla JS.
- Keep the #18 API contract EXACTLY — the frontend must parse the exact response shapes above (watchpoint carried from #18 review).
- No build step, no bundler, no npm dependency install. ES modules (`type="module"`) work in modern browsers and Node 24.
- Every user-facing text element is escaped (no raw interpolation) to avoid XSS from untrusted topic/title/claim strings.
- Security: `assetUrl`/`submitDecision` URL-encode user-supplied IDs/filenames.
- Reject → `POST /reject/{id}`; approve → `POST /approve/{id}` (matches #18 and Queue states).

---

### Task 1: Frontend core logic (pure, Node-tested)

**Files:**
- Create: `src/dashboard/frontend/core.mjs`
- Create: `tests/dashboard/frontend.test.mjs`

**Interfaces:**
- Produces (all pure, no DOM): `escapeHtml(value) -> str`, `assetUrl(video_id, filename) -> str`, `renderList(videos) -> str`, `renderDetail(videoPackage) -> str`, `removePending(videos, video_id) -> List`, `Selection` (immutable Set wrapper: `toggle`, `count`, `ids`), `submitDecision(fetchImpl, video_id, action) -> Promise`.
- Later task `app.mjs` consumes these.

- [ ] **Step 1: Write the failing JS tests**

```js
import test from 'node:test';
import assert from 'node:assert/strict';

import {
  assetUrl,
  escapeHtml,
  removePending,
  renderDetail,
  renderList,
  Selection,
  submitDecision,
} from '../../src/dashboard/frontend/core.mjs';

test('assetUrl builds asset path', () => {
  assert.equal(assetUrl('v1', 'v1_thumb.png'), '/video/v1/asset/v1_thumb.png');
});

test('escapeHtml escapes markup characters', () => {
  assert.equal(escapeHtml('<a&">'), '&lt;a&amp;&quot;&gt;');
});

test('renderList renders a card per video with select and thumbnail', () => {
  const html = renderList([
    { video_id: 'v1', title: 'Space Explained', topic: 'Space', thumbnail: 'v1_thumbnail.png' },
  ]);
  assert.match(html, /data-id="v1"/);
  assert.match(html, /data-select="v1"/);
  assert.match(html, /\/video\/v1\/asset\/v1_thumbnail\.png/);
  assert.match(html, /Space Explained/);
});

test('renderList emits an empty state when no videos', () => {
  assert.match(renderList([]), /No pending videos/);
});

test('renderDetail includes player, script, fact-check, shorts, and actions', () => {
  const v = {
    video_id: 'v1',
    metadata: { description: 'desc' },
    fact_check: { results: [{ claim: 'C1', confidence: 'high', flagged: false }] },
    script: { scenes: [{ scene_id: 1, narration: 'narration here', facts: ['f'] }] },
    assets: { midform: 'v1_midform.mp4', shorts: ['v1_short_01.mp4', 'v1_short_02.mp4'], thumbnail: 'v1_thumbnail.png' },
  };
  const html = renderDetail(v);
  assert.match(html, /v1_midform\.mp4/);
  assert.match(html, /v1_short_01\.mp4/);
  assert.match(html, /v1_short_02\.mp4/);
  assert.match(html, /data-decision="approve"/);
  assert.match(html, /data-decision="reject"/);
  assert.match(html, />C1</);
});

test('removePending removes the video with the given id', () => {
  assert.deepEqual(
    removePending([{ video_id: 'a' }, { video_id: 'b' }], 'a'),
    [{ video_id: 'b' }],
  );
});

test('Selection toggles ids and reports count', () => {
  let s = new Selection();
  s = s.toggle('x');
  s = s.toggle('y');
  assert.equal(s.count(), 2);
  s = s.toggle('x');
  assert.equal(s.count(), 1);
  assert.deepEqual(s.ids(), ['y']);
});

test('submitDecision posts to the approve endpoint', async () => {
  const calls = [];
  const fetchImpl = async (url, opts) => {
    calls.push({ url, opts });
    return { ok: true, json: async () => ({ status: 'approved' }) };
  };
  await submitDecision(fetchImpl, 'v1', 'approve');
  assert.equal(calls[0].url, '/approve/v1');
  assert.equal(calls[0].opts.method, 'POST');
});

test('submitDecision posts to the reject endpoint', async () => {
  let url = '';
  const fetchImpl = async (u) => {
    url = u;
    return { ok: true, json: async () => ({}) };
  };
  await submitDecision(fetchImpl, 'v1', 'reject');
  assert.equal(url, '/reject/v1');
});

test('submitDecision throws when the response is not ok', async () => {
  const fetchImpl = async () => ({ ok: false });
  await assert.rejects(() => submitDecision(fetchImpl, 'v1', 'approve'));
});

test('renderDetail escapes untrusted claim text', () => {
  const v = {
    video_id: 'v1',
    metadata: {},
    fact_check: { results: [{ claim: '<script>alert(1)</script>', confidence: 'low', flagged: true }] },
    script: { scenes: [] },
    assets: { midform: 'v1_midform.mp4', shorts: [], thumbnail: 'v1_thumbnail.png' },
  };
  assert.match(renderDetail(v), /&lt;script&gt;/);
  assert.doesNotMatch(renderDetail(v), /<script>alert/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/dashboard`
Expected: FAIL with `Cannot find module` for `core.mjs`.

- [ ] **Step 3: Write minimal implementation**

```js
export function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

export function assetUrl(videoId, filename) {
  return `/video/${encodeURIComponent(videoId)}/asset/${encodeURIComponent(filename)}`;
}

export function renderList(videos) {
  if (!Array.isArray(videos) || videos.length === 0) {
    return '<p class="empty">No pending videos.</p>';
  }
  return videos
    .map(
      (v) => `
    <article class="video-card" data-id="${escapeHtml(v.video_id)}">
      <label class="select"><input type="checkbox" data-select="${escapeHtml(v.video_id)}"></label>
      <img class="thumb" src="${assetUrl(v.video_id, v.thumbnail)}" alt="">
      <div class="summary">
        <h2>${escapeHtml(v.title)}</h2>
        <p class="topic">${escapeHtml(v.topic)}</p>
      </div>
      <button data-action="expand" type="button">Details</button>
    </article>`,
    )
    .join('');
}

export function renderDetail(v) {
  const midform = assetUrl(v.video_id, v.assets?.midform);
  const shorts = (v.assets?.shorts || [])
    .map((name) => `<li><video controls src="${assetUrl(v.video_id, name)}"></video></li>`)
    .join('');
  const facts = (v.fact_check?.results || [])
    .map(
      (r) =>
        `<li class="fact ${r.flagged ? 'flagged' : ''}">${escapeHtml(r.confidence)}: ${escapeHtml(r.claim)}</li>`,
    )
    .join('');
  const scenes = (v.script?.scenes || [])
    .map(
      (s) =>
        `<li><strong>Scene ${s.scene_id}</strong><p>${escapeHtml(s.narration)}</p></li>`,
    )
    .join('');
  return `
    <div class="detail">
      <video class="player" controls src="${midform}"></video>
      <section><h3>Metadata</h3><p>${escapeHtml(v.metadata?.description || '')}</p></section>
      <section><h3>Script</h3><ul>${scenes}</ul></section>
      <section><h3>Fact Check</h3><ul>${facts}</ul></section>
      <section><h3>Shorts</h3><ul>${shorts}</ul></section>
      <div class="actions">
        <button data-decision="approve" type="button">Approve</button>
        <button data-decision="reject" type="button">Reject</button>
      </div>
    </div>`;
}

export function removePending(videos, videoId) {
  return videos.filter((v) => v.video_id !== videoId);
}

export class Selection {
  constructor(selected = new Set()) {
    this.selected = selected;
  }

  toggle(id) {
    const next = new Set(this.selected);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    return new Selection(next);
  }

  count() {
    return this.selected.size;
  }

  ids() {
    return [...this.selected];
  }
}

export async function submitDecision(fetchImpl, videoId, action) {
  const url =
    action === 'reject'
      ? `/reject/${encodeURIComponent(videoId)}`
      : `/approve/${encodeURIComponent(videoId)}`;
  const res = await fetchImpl(url, { method: 'POST' });
  if (!res.ok) {
    throw new Error(`failed to ${action} video ${videoId}`);
  }
  return res.json ? await res.json() : null;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/dashboard`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/frontend/core.mjs tests/dashboard/frontend.test.mjs
git commit -m "Add testable frontend core logic for review dashboard (#19)"
```

### Task 2: Flask serving (index.html + static files)

**Files:**
- Modify: `src/dashboard/app.py`
- Create: `src/dashboard/frontend/index.html`
- Create: `src/dashboard/frontend/app.mjs`
- Create: `src/dashboard/frontend/style.css`
- Test: edit `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `create_app` from #18 (add static serving, keep all existing routes and the #18 API contract unchanged).
- Produces: `GET /` → `index.html`; `GET /static/<file>` → frontend static assets (`app.mjs`, `core.mjs`, `style.css`).

- [ ] **Step 1: Write the failing tests (append to `tests/test_dashboard.py`)**

```python
def test_index_serves_frontend_html(client):
    cli, _, _ = client
    resp = cli.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.content_type
    assert "Review Dashboard" in resp.get_data(as_text=True)


def test_index_links_to_module_bundle(client):
    cli, _, _ = client
    html = cli.get("/").get_data(as_text=True)
    assert '<script type="module" src="/static/app.mjs">' in html
    assert '/static/style.css' in html


def test_static_serves_frontend_assets(client):
    cli, _, _ = client
    for path in ["/static/core.mjs", "/static/app.mjs", "/static/style.css"]:
        resp = cli.get(path)
        assert resp.status_code == 200, path
    assert "text/javascript" in cli.get("/static/core.mjs").content_type
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_dashboard.py -q`
Expected: the new frontend tests FAIL (GET / returns 404 because no static config yet).

- [ ] **Step 3: Implement**

`index.html`:
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Review Dashboard</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header>
    <h1>Review Dashboard</h1>
    <div id="bulk-bar">
      <span id="selected-count">0 selected</span>
      <button id="bulk-approve" type="button">Approve selected</button>
      <button id="bulk-reject" type="button">Reject selected</button>
    </div>
  </header>
  <main id="app"></main>
  <script type="module" src="/static/app.mjs"></script>
</body>
</html>
```

`app.mjs` (thin DOM wiring over `core.mjs`):
```js
import {
  removePending,
  renderDetail,
  renderList,
  Selection,
  submitDecision,
} from './core.mjs';

let videos = [];
let selection = new Selection();

const app = document.getElementById('app');
const countEl = document.getElementById('selected-count');

function updateCount() {
  countEl.textContent = `${selection.count()} selected`;
}

function paint() {
  app.innerHTML = renderList(videos);
  updateCount();
  bindList();
}

async function refresh() {
  const res = await fetch('/pending');
  const data = await res.json();
  videos = data.videos || [];
  paint();
}

function bindList() {
  app.querySelectorAll('[data-select]').forEach((cb) => {
    cb.addEventListener('change', () => {
      selection = selection.toggle(cb.value);
      updateCount();
    });
  });
  app.querySelectorAll('[data-action="expand"]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const card = btn.closest('.video-card');
      const id = card.dataset.id;
      const existing = card.querySelector('.detail');
      if (existing) {
        existing.remove();
        return;
      }
      const res = await fetch(`/video/${encodeURIComponent(id)}`);
      const pkg = await res.json();
      card.insertAdjacentHTML('beforeend', renderDetail(pkg));
      card.querySelectorAll('[data-decision]').forEach((b) => {
        b.addEventListener('click', () => decide(card.dataset.id, b.dataset.decision));
      });
    });
  });
}

async function decide(id, action) {
  try {
    await submitDecision(fetch, id, action);
    videos = removePending(videos, id);
    paint();
  } catch (err) {
    console.error(err);
  }
}

async function bulk(action) {
  const ids = selection.ids();
  for (const id of ids) {
    try {
      await submitDecision(fetch, id, action);
      videos = removePending(videos, id);
    } catch (err) {
      console.error(err);
    }
  }
  paint();
}

document.getElementById('bulk-approve').addEventListener('click', () => bulk('approve'));
document.getElementById('bulk-reject').addEventListener('click', () => bulk('reject'));

refresh();
```

`style.css` (responsive):
```css
:root { --border: #d0d7de; --muted: #57606a; --accent: #1f883d; --danger: #cf222e; }
* { box-sizing: border-box; }
body { font-family: system-ui, sans-serif; margin: 0; background: #f6f8fa; color: #1f2328; }
header { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; padding: 16px 24px; background: #fff; border-bottom: 1px solid var(--border); }
#bulk-bar { display: flex; gap: 8px; align-items: center; }
button { padding: 8px 14px; border: 1px solid var(--border); border-radius: 6px; background: #fff; cursor: pointer; }
#bulk-approve { border-color: var(--accent); color: var(--accent); }
#bulk-reject { border-color: var(--danger); color: var(--danger); }
main { max-width: 1100px; margin: 0 auto; padding: 24px; }
.video-card { display: grid; grid-template-columns: 32px 120px 1fr auto; gap: 16px; align-items: center; background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }
.thumb { width: 120px; height: 68px; object-fit: cover; border-radius: 4px; background: #000; }
.summary h2 { margin: 0 0 4px; font-size: 1.05rem; }
.topic { margin: 0; color: var(--muted); }
.detail { grid-column: 1 / -1; border-top: 1px solid var(--border); padding-top: 12px; }
.detail ul { padding-left: 20px; }
.fact.flagged { color: var(--danger); }
.actions { display: flex; gap: 8px; margin-top: 12px; }
[data-decision="approve"] { border-color: var(--accent); color: var(--accent); }
[data-decision="reject"] { border-color: var(--danger); color: var(--danger); }
.empty { color: var(--muted); }
.player { width: 100%; max-width: 640px; }
@media (max-width: 640px) {
  .video-card { grid-template-columns: 32px 1fr auto; }
  .thumb { grid-column: 2 / -1; width: 100%; height: auto; }
  header { flex-direction: column; align-items: flex-start; }
}
```

`app.py` — serve frontend. Add near top:
```python
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
```
and in `create_app`:
```python
app = Flask(
    __name__,
    static_folder=str(FRONTEND_DIR),
    static_url_path="/static",
)
```
plus route:
```python
    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")
```
(`send_from_directory` is already imported from #18.)

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_dashboard.py -q`
Expected: all dashboard tests pass (existing + new). Also run `node --test tests/dashboard` to confirm the JS suite is unaffected.

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/app.py src/dashboard/frontend tests/test_dashboard.py
git commit -m "Serve review dashboard frontend and add serving tests (#19)"
```

### Task 3: Full suite, review, commit

- [ ] Run: `venv\Scripts\python -m pytest -q` (full Python suite, expect 212+ passed) AND `node --test tests/dashboard` (12 JS tests) — both must pass.
- [ ] Two-axis code review (standards + spec) of the diff vs `HEAD~N` (start of #19).
- [ ] Commit any review fixes; push to `master`; close #19 with a summary comment (no secrets in messages).
