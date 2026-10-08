(function () {
  "use strict";
  var M = window.VBMotion;
  var v = M.data.variables || {};
  var duration = Number(M.data.duration) || 5;
  var amount = Math.max(0, Math.round(Number(v.amount) || 0));
  var prefix = v.prefix === undefined ? "₩" : v.prefix;
  var suffix = v.suffix || "";
  var finalText = prefix + amount.toLocaleString("en-US") + suffix;
  var size = Math.min(230, Math.floor(1700 / Math.max(1, finalText.length * 0.62)));
  var number = M.byId("num");
  number.style.fontSize = size + "px";
  number.style.top = (400 + (230 - size) / 2) + "px";
  M.setText("lead", v.lead || "");
  M.setText("cap", v.caption || "");
  var count = Math.min(2.8, duration * 0.5);
  M.register(function (t) {
    M.byId("lead").style.opacity = M.clamp(t / 0.5);
    var q = M.easeOut(M.clamp((t - 0.4) / count));
    M.setText("num", prefix + Math.round(amount * q).toLocaleString("en-US") + suffix);
    M.byId("cap").style.opacity = M.clamp((t - 0.4 - count - 0.2) / 0.6);
  });
})();
