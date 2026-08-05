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
      <label class="select"><input type="checkbox" data-select="${escapeHtml(v.video_id)}" value="${escapeHtml(v.video_id)}"></label>
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

  const meta = v.metadata || {};
  const metaTitle = meta.title != null ? `<p class="meta-title">${escapeHtml(meta.title)}</p>` : '';
  const metaDesc =
    meta.description != null ? `<p class="meta-desc">${escapeHtml(meta.description)}</p>` : '';
  const metaCategory =
    meta.category != null ? `<p class="meta-category">Category: ${escapeHtml(String(meta.category))}</p>` : '';
  const tags = (meta.tags || [])
    .map((t) => `<li class="tag">${escapeHtml(t)}</li>`)
    .join('');

  const scenes = (v.script?.scenes || [])
    .map((s) => {
      const keywords = (s.key_visual_keywords || [])
        .map((k) => `<span class="kw">${escapeHtml(k)}</span>`)
        .join(' ');
      const facts = (s.facts || [])
        .map((f) => `<li>${escapeHtml(f)}</li>`)
        .join('');
      return `<li><strong>Scene ${escapeHtml(String(s.scene_id))}</strong>${keywords ? `<div class="keywords">${keywords}</div>` : ''}<p>${escapeHtml(s.narration)}</p>${facts ? `<ul class="scene-facts">${facts}</ul>` : ''}</li>`;
    })
    .join('');

  const facts = (v.fact_check?.results || [])
    .map(
      (r) =>
        `<li class="fact ${r.flagged ? 'flagged' : ''}">${escapeHtml(r.confidence)}: ${escapeHtml(r.claim)}</li>`,
    )
    .join('');
  const lowConf = (v.fact_check?.low_confidence || [])
    .map(
      (r) =>
        `<li class="fact flagged">${escapeHtml(r.confidence)}: ${escapeHtml(r.claim)}</li>`,
    )
    .join('');

  return `
    <div class="detail">
      <video class="player" controls src="${midform}"></video>
      <section><h3>Metadata</h3>${metaTitle}${metaDesc}${metaCategory}${tags ? `<ul class="tags">${tags}</ul>` : ''}</section>
      <section><h3>Script</h3><ul>${scenes}</ul></section>
      <section><h3>Fact Check</h3><ul>${facts}</ul>${lowConf ? `<h3>Low Confidence</h3><ul>${lowConf}</ul>` : ''}</section>
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
