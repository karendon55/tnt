/* TNT — JS mínimo: tema, confeti, utilidades */

// ============ Tema claro/oscuro ============
(function () {
    const btn = document.getElementById('themeToggle');
    if (!btn) return;
    btn.addEventListener('click', () => {
        const cur = document.documentElement.getAttribute('data-theme') || 'dark';
        const next = cur === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        document.documentElement.classList.toggle('dark', next === 'dark');
        localStorage.setItem('tnt-theme', next);
    });
})();

// ============ Confeti de rayos ============
function tntConfetti(options) {
    const opts = Object.assign({ count: 40, duration: 2400 }, options || {});
    let canvas = document.getElementById('confetti');
    if (!canvas) {
        canvas = document.createElement('canvas');
        canvas.id = 'confetti';
        document.body.appendChild(canvas);
    }
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    canvas.style.width = window.innerWidth + 'px';
    canvas.style.height = window.innerHeight + 'px';
    ctx.scale(dpr, dpr);

    const colors = ['#e10600', '#ff1a1a', '#c0c0c0', '#ffffff'];
    const bolts = [];
    for (let i = 0; i < opts.count; i++) {
        bolts.push({
            x: Math.random() * window.innerWidth,
            y: -20 - Math.random() * 200,
            vy: 2 + Math.random() * 4,
            vx: (Math.random() - 0.5) * 2,
            rot: Math.random() * Math.PI * 2,
            vr: (Math.random() - 0.5) * 0.2,
            size: 8 + Math.random() * 14,
            color: colors[Math.floor(Math.random() * colors.length)],
        });
    }

    const start = performance.now();
    function frame(now) {
        const elapsed = now - start;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        bolts.forEach(b => {
            b.y += b.vy;
            b.x += b.vx;
            b.rot += b.vr;
            ctx.save();
            ctx.translate(b.x, b.y);
            ctx.rotate(b.rot);
            ctx.fillStyle = b.color;
            // Rayo simple
            ctx.beginPath();
            ctx.moveTo(0, -b.size);
            ctx.lineTo(-b.size * 0.7, b.size * 0.1);
            ctx.lineTo(-b.size * 0.2, b.size * 0.1);
            ctx.lineTo(-b.size * 0.4, b.size);
            ctx.lineTo(b.size * 0.7, -b.size * 0.2);
            ctx.lineTo(b.size * 0.1, -b.size * 0.2);
            ctx.lineTo(b.size * 0.3, -b.size);
            ctx.closePath();
            ctx.fill();
            ctx.restore();
        });
        if (elapsed < opts.duration) {
            requestAnimationFrame(frame);
        } else {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            canvas.remove();
        }
    }
    requestAnimationFrame(frame);
}
window.tntConfetti = tntConfetti;

// ============ Formatear EUR ============
function formatEUR(amount) {
    return new Intl.NumberFormat('es-ES', {
        style: 'currency',
        currency: 'EUR',
        minimumFractionDigits: 2,
    }).format(amount);
}
window.formatEUR = formatEUR;
