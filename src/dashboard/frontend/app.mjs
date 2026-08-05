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
      selection = selection.toggle(cb.dataset.select);
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
  selection = new Selection();
  paint();
}

document.getElementById('bulk-approve').addEventListener('click', () => bulk('approve'));
document.getElementById('bulk-reject').addEventListener('click', () => bulk('reject'));

refresh();
