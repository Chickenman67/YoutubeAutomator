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
  assert.match(html, /high: C1/);
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
