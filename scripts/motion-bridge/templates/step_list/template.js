(function () {
  "use strict";
  var M = window.VBMotion;
  var v = M.data.variables || {};
  var duration = Number(M.data.duration) || 6;
  var steps = (v.steps || []).slice(0, 5);
  M.setText("t", v.title);
  for (var i = 0; i < 5; i += 1) {
    M.show("s" + i, i < steps.length);
    if (i < steps.length) { M.setText("n" + i, i + 1); M.setText("x" + i, steps[i]); }
  }
  var gap = Math.min(1.2, (duration * 0.6) / Math.max(1, steps.length));
  M.register(function (t) {
    var title = M.byId("t");
    var p = M.clamp(t / 0.5);
    title.style.opacity = p;
    title.style.transform = "translateY(" + (30 * (1 - p)) + "px)";
    steps.forEach(function (_step, index) {
      var q = M.easeOut(M.clamp((t - 0.8 - index * gap) / 0.6));
      var row = M.byId("s" + index);
      row.style.opacity = q;
      row.style.transform = "translateX(" + (-80 * (1 - q)) + "px)";
    });
  });
})();
