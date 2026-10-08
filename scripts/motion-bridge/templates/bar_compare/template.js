(function () {
  "use strict";
  var M = window.VBMotion;
  var v = M.data.variables || {};
  var duration = Number(M.data.duration) || 6;
  var bars = (v.bars || []).slice(0, 5);
  var unit = v.unit || "";
  var max = Math.max.apply(null, bars.map(function (bar) { return Number(bar.value) || 0; }).concat([0])) || 1;
  M.setText("t", v.title);
  M.setText("s", v.subtitle || "");
  for (var i = 0; i < 5; i += 1) {
    M.show("r" + i, i < bars.length);
    if (i < bars.length) {
      M.setText("l" + i, bars[i].label);
      if (Number(bars[i].value) === max) M.byId("r" + i).classList.add("win");
    }
  }
  var grow = Math.min(1.6, duration * 0.3);
  function widestFinalValue() {
    var widest = 0;
    bars.forEach(function (bar) {
      var probe = M.setText("m", M.formatNumber(bar.value) + unit);
      widest = Math.max(widest, probe.offsetWidth);
    });
    return widest;
  }
  M.register(function (t) {
    var title = M.byId("t");
    var p = M.clamp(t / 0.7);
    title.style.opacity = p;
    title.style.transform = "translateY(" + (40 * (1 - p)) + "px)";
    var room = Math.max(400, 1640 - 464 - widestFinalValue() - 16);
    bars.forEach(function (bar, index) {
      var q = M.easeOut(M.clamp((t - 0.8 - index * 0.25) / grow));
      var shown = Number(bar.value) * q;
      var width = room * shown / max;
      M.byId("b" + index).style.width = width + "px";
      var label = M.setText("v" + index, M.formatNumber(shown) + unit);
      label.style.left = (440 + width + 24) + "px";
    });
  });
})();
