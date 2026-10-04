/* Shopkeeper registration helpers.
 *
 * Two jobs: show the shop fields only when "Shopkeeper" is selected, and fill in
 * the latitude/longitude pair from the browser's geolocation API.
 *
 * Failure here must never block registration — a merchant who denies the
 * location prompt still gets an account, and can send a pin from Telegram later.
 */
(function () {
  "use strict";

  function panelFor(select) {
    var form = select.form || document;
    return form.querySelector("[data-shop-fields]");
  }

  function syncRole(select) {
    var panel = panelFor(select);
    if (!panel) return;
    var isShopkeeper = select.value === "shopkeeper";
    panel.classList.toggle("hidden", !isShopkeeper);
    // A hidden <select> must not be required, or the form silently refuses to submit.
    var category = panel.querySelector("select[name='shop_category']");
    if (category) category.required = isShopkeeper;
  }

  function setStatus(prefix, message, state) {
    var node = document.querySelector("[data-status='" + prefix + "']");
    if (!node) return;
    node.textContent = message;
    node.className = "field-status" + (state ? " " + state : "");
  }

  function capture(prefix, button) {
    if (!navigator.geolocation) {
      setStatus(prefix, "This browser cannot share a location. You can send it from Telegram instead.", "warn");
      return;
    }
    var original = button.textContent;
    button.disabled = true;
    button.textContent = "📍 Getting your location…";
    setStatus(prefix, "Waiting for your device…", "");

    navigator.geolocation.getCurrentPosition(
      function (position) {
        var latitude = position.coords.latitude;
        var longitude = position.coords.longitude;
        document.getElementById(prefix + "latitude").value = latitude.toFixed(6);
        document.getElementById(prefix + "longitude").value = longitude.toFixed(6);
        var accuracy = Math.round(position.coords.accuracy || 0);
        setStatus(
          prefix,
          "✅ Location captured (" + latitude.toFixed(5) + ", " + longitude.toFixed(5) +
            ") · accurate to about " + accuracy + "m",
          "ok"
        );
        button.disabled = false;
        button.textContent = "📍 Update location";
      },
      function (error) {
        var reasons = {
          1: "Permission denied. Allow location access, or send your pin from Telegram later.",
          2: "Your position is unavailable right now. Try again outdoors, or send it from Telegram.",
          3: "Timed out while locating you. Please try again."
        };
        setStatus(prefix, "⚠️ " + (reasons[error.code] || "Could not get your location."), "warn");
        button.disabled = false;
        button.textContent = original;
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
    );
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("select[name='role']").forEach(function (select) {
      syncRole(select);
      select.addEventListener("change", function () {
        syncRole(select);
      });
    });

    document.querySelectorAll("[data-locate]").forEach(function (button) {
      button.addEventListener("click", function () {
        capture(button.getAttribute("data-locate"), button);
      });
    });
  });
})();
