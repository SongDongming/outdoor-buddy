/**
 * Hero Canvas — Alpine Tech Aurora + Particles
 * Dark theme: aurora bands, subtle mountain silhouettes, glowing particles
 */
(function(){
  const canvas = document.getElementById('heroCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  let width, height, mouseX = 0.5, mouseY = 0.5;
  let targetX = 0.5, targetY = 0.5;
  let time = 0;

  const particles = [];
  const PARTICLE_COUNT = 80;

  function resize(){
    const main = document.querySelector('.main-content');
    width = canvas.width = main ? main.offsetWidth : window.innerWidth;
    height = canvas.height = window.innerHeight;
    initParticles();
  }

  function initParticles() {
    particles.length = 0;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        r: 0.3 + Math.random() * 1.8,
        vx: (Math.random() - 0.5) * 0.2,
        vy: -0.05 - Math.random() * 0.3,
        opacity: 0.2 + Math.random() * 0.5,
        flicker: Math.random() * Math.PI * 2,
        hue: Math.random() < 0.6 ? 40 : 170, // mostly amber, some teal
      });
    }
  }

  function drawAurora() {
    // Aurora band — subtle teal/green sweep
    const offsetX = (mouseX - 0.5) * 30;
    const offsetY = (mouseY - 0.5) * 10;
    for (let band = 0; band < 3; band++) {
      ctx.beginPath();
      const baseY = height * (0.15 + band * 0.08) + offsetY;
      const alpha = 0.025 - band * 0.006;
      ctx.strokeStyle = band === 0
        ? `rgba(61,184,168,${alpha})`
        : band === 1
        ? `rgba(134,200,216,${alpha * 0.7})`
        : `rgba(91,156,110,${alpha * 0.5})`;
      ctx.lineWidth = 40 + band * 15;

      for (let x = 0; x <= width; x += 3) {
        const nx = x / width;
        const y = baseY
          + Math.sin(nx * 2.5 + time * 0.3 + band) * (20 + band * 12)
          + Math.cos(nx * 4.1 + time * 0.2 + band * 0.7) * (15 + band * 8)
          + Math.sin(nx * 6.3 + time * 0.15) * (8 + band * 4);
        const px = x + offsetX * (1 + band * 0.1);
        if (x === 0) ctx.moveTo(px, y);
        else ctx.lineTo(px, y);
      }
      ctx.stroke();
    }
  }

  function drawMountains() {
    const offsetX = (mouseX - 0.5) * 50;
    const offsetY = (mouseY - 0.5) * 12;

    // Far mountain layers
    for (let layer = 0; layer < 4; layer++) {
      ctx.beginPath();
      const baseY = height * (0.5 + layer * 0.07);
      const alpha = 0.06 - layer * 0.012;
      ctx.strokeStyle = `rgba(255,255,255,${alpha})`;
      ctx.lineWidth = 1.2 + layer * 0.15;

      for (let x = 0; x <= width; x += 3) {
        const nx = x / width;
        const y = baseY
          + Math.sin(nx * 3.2 + layer * 0.8) * (22 + layer * 12)
          + Math.cos(nx * 4.8 + layer) * (16 + layer * 8)
          + Math.sin(nx * 6.8 + layer * 1.5) * (8 + layer * 4);
        const px = x + offsetX * (1 + layer * 0.12);
        const py = y + offsetY * (1 + layer * 0.08);
        if (x === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.stroke();
    }

    // Main peak silhouette
    ctx.beginPath();
    const peakBaseY = height * 0.38;
    ctx.moveTo(0, height);
    for (let x = 0; x <= width; x += 2) {
      const nx = x / width;
      const y = peakBaseY
        + Math.sin(nx * 2.0) * 40
        + Math.cos(nx * 4.3) * 24
        + Math.sin(nx * 7.0) * 14
        + offsetY * 0.3;
      ctx.lineTo(x, y);
    }
    ctx.lineTo(width, height);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, peakBaseY - 40, 0, height);
    grad.addColorStop(0, 'rgba(255,255,255,0.06)');
    grad.addColorStop(0.5, 'rgba(255,255,255,0.02)');
    grad.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = grad;
    ctx.fill();
  }

  function drawParticles() {
    particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      p.flicker += 0.015;
      if (p.y < -10) { p.y = height + 10; p.x = Math.random() * width; }
      if (p.x < -10) p.x = width + 10;
      if (p.x > width + 10) p.x = -10;

      const alpha = p.opacity * (0.5 + 0.5 * Math.sin(p.flicker));
      const color = p.hue === 40
        ? `rgba(255,200,140,${alpha})`
        : `rgba(100,210,200,${alpha})`;

      // Core
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
      // Glow
      ctx.fillStyle = p.hue === 40
        ? `rgba(255,200,140,${alpha * 0.25})`
        : `rgba(100,210,200,${alpha * 0.2})`;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r * 3.5, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  function draw() {
    ctx.clearRect(0, 0, width, height);
    mouseX += (targetX - mouseX) * 0.03;
    mouseY += (targetY - mouseY) * 0.03;
    time += 0.004;

    drawAurora();
    drawMountains();
    drawParticles();

    requestAnimationFrame(draw);
  }

  document.addEventListener('mousemove', e => {
    targetX = e.clientX / window.innerWidth;
    targetY = e.clientY / window.innerHeight;
  });
  document.addEventListener('mouseleave', () => { targetX = 0.5; targetY = 0.5; });

  window.addEventListener('resize', () => { resize(); });
  resize();
  initParticles();
  draw();
})();