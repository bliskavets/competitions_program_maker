// Lightweight UI helpers for modals, confirmations and drag-n-drop ordering.

function openModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove('hidden');
}
function closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('hidden');
}

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
    if (!tbody || typeof Sortable === 'undefined') return;
    Sortable.create(tbody, {
        animation: 150,
        handle: '.draw-row',
        onEnd: () => syncOrder(tbodyId, hiddenId),
    });
    syncOrder(tbodyId, hiddenId);
}
function syncOrder(tbodyId, hiddenId) {
    const tbody = document.getElementById(tbodyId);
    const hidden = document.getElementById(hiddenId);
    if (!tbody || !hidden) return;
    const ids = Array.from(tbody.querySelectorAll('tr[data-pid]'))
        .map((tr) => tr.getAttribute('data-pid'));
    hidden.value = ids.join(',');
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
