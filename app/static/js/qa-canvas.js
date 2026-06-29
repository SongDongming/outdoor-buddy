/**
 * QA Page Canvas — Dark Ambient Particles
 * Alpine Tech: subtle aurora waves + floating light particles
 */
(function(){
  const canvas = document.getElementById('qaCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let width, height, time = 0;

  const particles = [];
  const PARTICLE_COUNT = 40;

  function resize() {
    const area = document.querySelector('.qa-page');
    if (!area) return;
    width = canvas.width = area.offsetWidth;
    height = canvas.height = area.offsetHeight;
    initParticles();
  }

  function initParticles() {
    particles.length = 0;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        r: 0.5 + Math.random() * 2,
        vx: (Math.random() - 0.5) * 0.15,
        vy: 0.1 + Math.random() * 0.3,
        opacity: 0.1 + Math.random() * 0.25,
        flicker: Math.random() * Math.PI * 2,
        hue: Math.random() < 0.5 ? 40 : 170,
      });
    }
  }

  function drawAuroraWaves() {
    for (let band = 0; band < 2; band++) {
      ctx.beginPath();
      const baseY = height * (0.2 + band * 0.12);
      ctx.strokeStyle = band === 0
        ? `rgba(61,184,168,0.04)`
        : `rgba(134,200,216,0.03)`;
      ctx.lineWidth = 50;
      for (let x = 0; x <= width; x += 5) {
        const nx = x / width;
        const y = baseY + Math.sin(nx * 2 + time * 0.2 + band) * 18 + Math.cos(nx * 4 + time * 0.15) * 12;
        if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
  }

  function drawParticles() {
    particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      p.flicker += 0.012;
      if (p.y > height + 20) { p.y = -20; p.x = Math.random() * width; }
      if (p.x > width + 20) p.x = -20;
      if (p.x < -20) p.x = width + 20;

      const alpha = p.opacity * (0.5 + 0.5 * Math.sin(p.flicker));
      const color = p.hue === 40
        ? `rgba(255,200,140,${alpha})`
        : `rgba(100,210,200,${alpha})`;

      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
      // Micro glow
      ctx.fillStyle = p.hue === 40
        ? `rgba(255,200,140,${alpha * 0.2})`
        : `rgba(100,210,200,${alpha * 0.15})`;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r * 3, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  function draw() {
    ctx.clearRect(0, 0, width, height);
    time += 0.003;

    drawAuroraWaves();
    drawParticles();

    requestAnimationFrame(draw);
  }

  const observer = new ResizeObserver(() => resize());
  const area = document.querySelector('.qa-page');
  if (area) observer.observe(area);

  resize();
  draw();
})();