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
