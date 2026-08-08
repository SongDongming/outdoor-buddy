/**
 * 进站特效 — "用脚步丈量大地"
 * 大地色系 · 极简户外风 · 纯视觉无音效 · 总时长约 1.6s
 *
 * 全部由 animationend 事件驱动，不依赖 CSS 加载时序：
 *   - 地平线 0s 铺开（CSS）
 *   - 七个字 0.3s 起逐字"踩落"（压扁→回弹），每个字落地瞬间撒尘土
 *   - 最后一字结束 → 标题上浮、地平线渐隐 → 副标题淡入 → 整体淡出
 */
(function () {
  var splash = document.getElementById('splash-screen');
  if (!splash) return;

  function removeSplash() {
    if (splash.parentNode) splash.parentNode.removeChild(splash);
  }

  // 尊重系统"减弱动态"偏好：直接淡出跳过动画
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    splash.classList.add('hide');
    setTimeout(removeSplash, 80);
    return;
  }

  var chars = splash.querySelectorAll('.splash-char');
  var STEP_START = 0.4;   // 地平线铺开后第 1 字踩落
  var STEP_GAP = 0.15;    // 逐字间隔（加快弹出节奏）
  var STEP_DURATION = 0.55; // 单字踩落动画时长（与 CSS splash-step 对齐）

  /** 在字符底部撒 3-5 颗尘土细粒，向两侧散开消失 */
  function spawnDust(charEl, count) {
    var rect = charEl.getBoundingClientRect();
    for (var i = 0; i < count; i++) {
      var d = document.createElement('span');
      d.className = 'splash-dust';
      d.style.left = (rect.left + rect.width / 2 + (Math.random() * 10 - 5)) + 'px';
      d.style.top = (rect.bottom - 1) + 'px';
      d.style.setProperty('--dx', (Math.random() * 48 - 24) + 'px');
      d.style.setProperty('--dy', (Math.random() * 14 + 5) + 'px');
      document.body.appendChild(d);
      (function (el) { setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 650); })(d);
    }
  }

  var lastChar = chars[chars.length - 1];

  // 逐字设延迟；在每字落地瞬间（动画约 60% 压扁触地）撒尘土
  Array.prototype.forEach.call(chars, function (ch, i) {
    var delay = STEP_START + i * STEP_GAP;
    ch.style.animationDelay = delay + 's';
    var landMs = (delay + STEP_DURATION * 0.6) * 1000;
    setTimeout(function () {
      spawnDust(ch, 3 + Math.floor(Math.random() * 3));
    }, landMs);
  });

  // 最后一个字踩落结束 → 驱动"上浮 → 副标题 → 淡出"（放慢节奏）
  if (lastChar) {
    lastChar.addEventListener('animationend', function onLast() {
      lastChar.removeEventListener('animationend', onLast);
      splash.classList.add('settle');                                  // 标题上浮 + 地平线渐隐
      setTimeout(function () { splash.classList.add('subtitle-show'); }, 450); // 副标题淡入
      // 完整画面（含副标题）明确停顿约1.5-1.7秒后，整体柔和淡出；
      // 淡出完全结束后（transitionend）才移除，避免中途"突然消失"
      setTimeout(function () { splash.classList.add('hide'); }, 2600);
    });
  }

  // 淡出过渡结束后移除遮罩（保证整幅画面完整淡出）
  // 限定触发对象必须是最外层容器，拦截子元素（如副标题）冒泡事件
  splash.addEventListener('transitionend', function onFade(e) {
    if (e.target === splash && e.propertyName === 'opacity' && splash.classList.contains('hide')) {
      splash.removeEventListener('transitionend', onFade);
      removeSplash();
    }
  });

  // 兜底：仅当动画完全没跑（hide 从未添加）时才强制收尾，避免截断正常淡出
  setTimeout(function () {
    var s = document.getElementById('splash-screen');
    if (s && !s.classList.contains('hide')) {
      s.classList.add('hide');
      setTimeout(removeSplash, 400);
    }
  }, 6000);
})();
