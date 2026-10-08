/* VideoBox 설명 모션 공통 타임라인. 바깥 애니메이션 꾸러미 없이 돈다(네트워크 0건, 2026-10-08 스파이크).
 * (이 파일에 그 꾸러미 이름이나 주소를 적지 않는다 -- tests/test_motion_templates_offline.py가 글자로 막는다.)
 * 하이퍼프레임은 window.__timelines["main"].seek(t)를 프레임마다 부르고 그 순간을 찍는다.
 * 글은 textContent로만 넣는다 -- 마크업으로 바꾸지 않는다. */
(function () {
  "use strict";
  var data = window.__VB_MOTION__ || { variables: {}, duration: 6, mode: "full" };
  function clamp(x) { return Math.max(0, Math.min(1, x)); }
  function easeOut(t) { return 1 - Math.pow(1 - t, 3); }
  function byId(id) { return document.getElementById(id); }
  function setText(id, value) {
    var element = byId(id);
    if (element) element.textContent = value === null || value === undefined ? "" : String(value);
    return element;
  }
  function show(id, visible) {
    var element = byId(id);
    if (element) element.style.display = visible ? "" : "none";
  }
  function formatNumber(value) {
    return Number(value).toLocaleString("en-US", { maximumFractionDigits: 1 });
  }
  function register(apply) {
    var timeline = {
      _t: 0,
      _d: Number(data.duration) || 6,
      pause: function () { return this; },
      play: function () { return this; },
      paused: function () { return true; },
      seek: function (t) { this._t = t; apply(t); return this; },
      time: function (t) { if (t === undefined) return this._t; return this.seek(t); },
      totalTime: function (t) { return this.time(t); },
      duration: function () { return this._d; },
      totalDuration: function () { return this._d; },
      getChildren: function () { return []; }
    };
    window.__timelines = window.__timelines || {};
    window.__timelines["main"] = timeline;
    timeline.seek(0);
  }
  window.VBMotion = { data: data, clamp: clamp, easeOut: easeOut, byId: byId, setText: setText, show: show, formatNumber: formatNumber, register: register };
})();
