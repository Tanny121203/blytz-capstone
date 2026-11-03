// Approval modal flow
// This MUST load BEFORE payment_details.js to intercept the submit button
(function() {
  const approvalModal = document.getElementById('approval-modal');
  const paymentModal = document.getElementById('payment-modal');
  const submitBtn = document.querySelector('[data-editor-submit]');
  const approvalCheckbox = document.getElementById('approval-checkbox');
  const approvalAcceptBtn = document.getElementById('approval-accept-btn');
  const approvalDeclineBtn = document.getElementById('approval-decline-btn');
  const paymentCancelBtn = document.getElementById('payment-cancel-btn');

  if (!submitBtn || !approvalModal || !paymentModal) return;

  // ── STEP 1: Block the submit button from opening payment modal ──
  // Use capturing phase to intercept BEFORE payment_details.js handler runs
  submitBtn.addEventListener('click', function(e) {
    e.preventDefault();
    e.stopImmediatePropagation();
    e.stopPropagation();
    openApprovalModal();
  }, true); // true = capturing phase (runs BEFORE bubble-phase handlers)

  // ── STEP 2: Approval modal open/close ──
  function openApprovalModal() {
    // Hide payment modal
    paymentModal.classList.add('hidden');
    paymentModal.classList.remove('flex');

    // Show approval modal
    approvalModal.classList.remove('hidden');
    approvalModal.classList.add('flex');

    // Reset checkbox
    if (approvalCheckbox) approvalCheckbox.checked = false;
    if (approvalAcceptBtn) approvalAcceptBtn.disabled = true;
  }

  function closeApprovalModal() {
    approvalModal.classList.add('hidden');
    approvalModal.classList.remove('flex');
  }

  function openPaymentModal() {
    // Hide approval modal
    closeApprovalModal();

    // Show payment modal
    paymentModal.classList.remove('hidden');
    paymentModal.classList.add('flex');
  }

  function closePaymentModal() {
    paymentModal.classList.add('hidden');
    paymentModal.classList.remove('flex');
  }

  // ── STEP 3: Checkbox enables Accept button ──
  if (approvalCheckbox && approvalAcceptBtn) {
    approvalCheckbox.addEventListener('change', function() {
      approvalAcceptBtn.disabled = !this.checked;
    });
  }

  // ── STEP 4: Accept → open payment modal ──
  if (approvalAcceptBtn) {
    approvalAcceptBtn.addEventListener('click', function() {
      openPaymentModal();
    });
  }

  // ── STEP 5: Decline → close approval modal ──
  if (approvalDeclineBtn) {
    approvalDeclineBtn.addEventListener('click', function() {
      closeApprovalModal();
    });
  }

  // ── STEP 6: Cancel Payment → close payment modal ──
    if (paymentCancelBtn) {
    paymentCancelBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopImmediatePropagation();
        closePaymentModal();
    }, true);
    }

  // ── STEP 7: Close buttons (X) on modals ──
  approvalModal.querySelectorAll('[data-modal-close]').forEach(function(btn) {
    btn.addEventListener('click', function() {
      closeApprovalModal();
    });
  });

  paymentModal.querySelectorAll('[data-modal-close]').forEach(function(btn) {
    btn.addEventListener('click', function() {
      closePaymentModal();
    });
  });

})();