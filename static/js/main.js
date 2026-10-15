/**
 * Product Inventory — progressive enhancements.
 *
 * Everything here is optional: the app works (including deletes and
 * validation) if JavaScript is disabled or fails to load.
 */

(function () {
    "use strict";

    /**
     * Confirm destructive submits via the form's `data-confirm` attribute.
     * The message is written in the markup, so product names never have to
     * be escaped into inline JavaScript.
     */
    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!(form instanceof HTMLFormElement)) return;

        if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
            event.preventDefault();
            return;
        }

        // Guard against double submissions (a slow network + two clicks
        // used to create duplicate product rows).
        if (form.method.toLowerCase() !== "get") {
            var button = form.querySelector('button[type="submit"]');
            if (button) {
                button.disabled = true;
                button.dataset.label = button.textContent;
                button.textContent = "Working…";
            }
        }
    });

    /**
     * Auto-dismiss flash messages so they don't sit on the page forever.
     */
    function dismissFlashMessages() {
        var messages = document.querySelectorAll(".alert-dismissible");
        messages.forEach(function (alert) {
            window.setTimeout(function () {
                var close = alert.querySelector(".btn-close");
                if (close) close.click();
            }, 6000);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", dismissFlashMessages);
    } else {
        dismissFlashMessages();
    }
})();
