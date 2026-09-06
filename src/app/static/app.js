// Lightweight UI helpers for modals, confirmations and drag-n-drop ordering.

function openModal(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.remove('hidden');
        document.body.classList.add('modal-open');
        el.scrollTop = 0;
    }
}
function closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('hidden');
    if (!document.querySelector('.modal-backdrop:not(.hidden)')) {
        document.body.classList.remove('modal-open');
    }
}

document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    document.querySelectorAll('.modal-backdrop:not(.hidden)').forEach((modal) => closeModal(modal.id));
});

// Confirmation forms: any element with data-confirm shows a native confirm().
document.addEventListener('submit', (e) => {
    const msg = e.target.getAttribute('data-confirm');
    if (msg && !window.confirm(msg)) {
        e.preventDefault();
    }
});

// Initialise SortableJS on draw tables and keep a hidden "order" field in sync.
function initSortable(tbodyId, hiddenId) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    if (typeof Sortable !== 'undefined' && !tbody.dataset.sortableInitialized) {
        Sortable.create(tbody, {
            animation: 150,
            handle: '.draw-row',
            onEnd: () => syncOrder(tbodyId, hiddenId),
        });
        tbody.dataset.sortableInitialized = 'true';
    }
}
function syncOrder(tbodyId, hiddenId) {
    const tbody = document.getElementById(tbodyId);
    const hidden = document.getElementById(hiddenId);
    if (!tbody || !hidden) return;
    const ids = Array.from(tbody.querySelectorAll('tr[data-pid]'))
        .map((tr) => tr.getAttribute('data-pid'));
    const value = ids.join(',');
    hidden.value = value;
    hidden.setAttribute('value', value);
    // renumber the visible "Number" column
    tbody.querySelectorAll('tr[data-pid] .draw-number').forEach((cell, i) => {
        cell.textContent = i + 1;
    });
}

// Re-init sortable after HTMX swaps in new content.
document.body.addEventListener('htmx:afterSwap', () => {
    if (document.getElementById('draw-body')) {
        initSortable('draw-body', 'order-field');
    }
});

function initCurrentDraw() {
    if (document.getElementById('draw-body')) {
        initSortable('draw-body', 'order-field');
    }
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCurrentDraw);
} else {
    initCurrentDraw();
}

document.body.addEventListener('documentsImported', () => closeModal('docs-modal'));
