const byId = id => document.getElementById(id);
const ROLES = ['water', 'mulch', 'sun'];
// What each station is, depending on whether a Pi sensor or a phone currently holds the role.
const WHO = {
  water: {pi: 'Pi 4 · turn the rotary encoder', phone: 'Phone · slide the bar'},
  mulch: {pi: 'Pi 4 · move the joystick left and right', phone: 'Phone · rub the screen'},
  sun: {pi: 'Pi 4 · hold the button', phone: 'Phone · hold the button'},
};
const canvas = byId('scene'), ctx = canvas.getContext('2d');
const W = 900, H = 500, GROUND = 420, PLANT_X = 470, CAN = {x: 250, y: 250};
const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;

let data = null;                                    // latest state from the laptop
const view = {tilt: 0, sun: 0, mulch: 0, grow: 0};  // eased copies, so the picture moves smoothly
const drops = [];                                   // water drops, splashes and mulch bits

function renderHud() {
  byId('demo-banner').hidden = !data.demo;
  byId('team').textContent = data.team;
  byId('hint').textContent = data.hint;
  byId('hint').className = 'hint ' + data.mode;
  const round = Math.min(data.cycle + 1, data.cycles);
  byId('round').textContent = data.mode === 'bloomed' ? 'All 3 rounds done' : `Round ${round} of ${data.cycles}`;
  byId('pips').textContent = '●'.repeat(data.cycle) + '○'.repeat(data.cycles - data.cycle);
  byId('connection').textContent = data.demo ? 'Offline preview with simulated stations: no MQTT'
    : data.mqtt_connected ? `MQTT messages arriving from the broker · ${data.active} of 3 stations here` : 'Connecting to MQTT. Check the server terminal';
  // The evidence panel: one row per topic, then the most recent changes, newest first.
  byId('topics').replaceChildren(...ROLES.map(role => {
    const name = Object.keys(data.topics).find(t => t.endsWith('/' + role)), row = document.createElement('tr');
    const cells = [name || `…/garden/${role}`, name ? data.topics[name].last : 'nothing yet', name ? data.topics[name].count : 0];
    row.append(...cells.map(text => Object.assign(document.createElement('td'), {textContent: text})));
    return row;
  }));
  byId('log').textContent = data.log.slice().reverse()
    .map(m => `${m.time}  ${m.topic}  ${m.payload}${m.ok ? '' : '   (rejected)'}`).join('\n') || 'No messages yet.';
  byId('status-dot').classList.toggle('connected', data.mqtt_connected && !data.demo);
  const now = ROLES.indexOf(data.step), growing = data.mode === 'growing';
  document.querySelectorAll('.step').forEach((card, i) => {
    const done = data.mode === 'bloomed' || (growing && i < now), current = growing && i === now;
    card.classList.toggle('current', current);
    card.classList.toggle('away', !data.stations[ROLES[i]]);
    card.querySelector('progress').value = done ? 100 : current ? data.meter : 0;
    card.querySelector('.who').textContent = WHO[ROLES[i]][data.sources[ROLES[i]]] || 'Waiting for a station';
    card.querySelector('.state').textContent = (done ? 'Done' : current ? 'Now' : 'Wait') + (data.stations[ROLES[i]] ? '' : ' · away');
  });
}

// --- the picture ---

function spoutTip(angle) {  // where the can's spout ends, after the can is rotated
  return {x: CAN.x + 118 * Math.cos(angle) + 42 * Math.sin(angle), y: CAN.y + 118 * Math.sin(angle) - 42 * Math.cos(angle)};
}

function drawSky(t) {
  ctx.fillStyle = '#cfe3ee';
  ctx.fillRect(0, 0, W, GROUND);
  ctx.fillStyle = `rgba(255, 226, 140, ${0.45 * view.sun})`;
  ctx.fillRect(0, 0, W, GROUND);
  ctx.save();
  ctx.translate(770, 95);
  ctx.strokeStyle = `rgba(242, 178, 40, ${view.sun})`;
  ctx.lineWidth = 6;
  ctx.lineCap = 'round';
  for (let i = 0; i < 12; i++) {  // rays turn slowly while the sun is out
    const a = i * Math.PI / 6 + (calm ? 0 : t / 4);
    ctx.beginPath();
    ctx.moveTo(52 * Math.cos(a), 52 * Math.sin(a));
    ctx.lineTo((62 + 22 * view.sun) * Math.cos(a), (62 + 22 * view.sun) * Math.sin(a));
    ctx.stroke();
  }
  ctx.fillStyle = view.sun > 0.5 ? '#f2c230' : '#e6dcae';
  ctx.beginPath();
  ctx.arc(0, 0, 42, 0, 2 * Math.PI);
  ctx.fill();
  ctx.restore();
}

function drawGround() {
  ctx.fillStyle = '#7d9a5f';
  ctx.fillRect(0, GROUND, W, H - GROUND);
  ctx.fillStyle = '#6b4a33';
  ctx.beginPath();
  ctx.ellipse(PLANT_X, GROUND + 10, 130, 18, 0, 0, 2 * Math.PI);
  ctx.fill();
  ctx.fillStyle = '#a87b4f';  // mulch chips pile up left and right of the stem
  const chips = Math.round(view.mulch / 100 * 26);
  for (let i = 0; i < chips; i++) {
    const side = i % 2 ? 1 : -1, spread = 14 + (i >> 1) * 8;
    ctx.fillRect(PLANT_X + side * spread - 7, GROUND + 2 - (i % 3) * 5, 14, 6);
  }
}

function drawPlant() {
  const dead = data.mode === 'withered', height = 40 + 85 * view.grow;
  const colour = dead ? '#8a6a3a' : '#3f8a3a';
  ctx.strokeStyle = ctx.fillStyle = colour;
  ctx.lineWidth = 7;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(PLANT_X, GROUND);
  let top = {x: PLANT_X, y: GROUND - height};
  if (dead) {  // a withered stem flops over to one side
    top = {x: PLANT_X + height * 0.5, y: GROUND - height * 0.45};
    ctx.quadraticCurveTo(PLANT_X, GROUND - height * 0.8, top.x, top.y);
  } else {
    ctx.lineTo(top.x, top.y);
  }
  ctx.stroke();
  const leaves = dead ? 2 : 1 + 2 * Math.floor(view.grow + 0.01);
  for (let i = 1; i <= leaves; i++) {
    const side = i % 2 ? 1 : -1, y = GROUND - height * i / (leaves + 1) * (dead ? 0.6 : 1);
    ctx.save();
    ctx.translate(PLANT_X + side * 20, y);
    ctx.rotate(dead ? side * 1.1 : -side * 0.45);  // dead leaves hang down
    ctx.beginPath();
    ctx.ellipse(0, 0, 22, 9, 0, 0, 2 * Math.PI);
    ctx.fill();
    ctx.restore();
  }
  if (data.mode === 'bloomed') {
    ctx.fillStyle = '#e06a9a';
    for (let i = 0; i < 8; i++) {
      const a = i * Math.PI / 4;
      ctx.beginPath();
      ctx.ellipse(top.x + 22 * Math.cos(a), top.y + 22 * Math.sin(a), 16, 9, a, 0, 2 * Math.PI);
      ctx.fill();
    }
    ctx.fillStyle = '#f1d36b';
    ctx.beginPath();
    ctx.arc(top.x, top.y, 13, 0, 2 * Math.PI);
    ctx.fill();
  }
}

function drawCan(angle) {
  ctx.save();
  ctx.translate(CAN.x, CAN.y);
  ctx.rotate(angle);
  ctx.strokeStyle = ctx.fillStyle = '#5f84a8';
  ctx.lineCap = 'round';
  ctx.lineWidth = 9;
  ctx.beginPath();
  ctx.arc(-55, -2, 30, 0.5 * Math.PI, 1.5 * Math.PI);  // handle
  ctx.stroke();
  ctx.lineWidth = 14;
  ctx.beginPath();
  ctx.moveTo(50, 18);
  ctx.lineTo(112, -37);  // spout
  ctx.stroke();
  ctx.beginPath();
  ctx.roundRect(-55, -45, 110, 92, 10);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(118, -42, 11, 0, 2 * Math.PI);  // rose at the end of the spout
  ctx.fill();
  ctx.restore();
}

function pour(angle, dt) {
  const tip = spoutTip(angle);
  if (calm) {  // no moving drops: one plain stream
    ctx.strokeStyle = '#4a90d9';
    ctx.lineWidth = 5;
    ctx.beginPath();
    ctx.moveTo(tip.x, tip.y);
    ctx.quadraticCurveTo(tip.x + 60, tip.y + 20, PLANT_X - 20, GROUND);
    ctx.stroke();
    return;
  }
  // Drops leave along the spout, faster the further the can is tipped, then gravity takes over.
  const along = angle - 0.72, speed = 60 + 1.4 * view.tilt;
  for (let n = view.tilt * 0.9 * dt + Math.random(); n >= 1; n--) {
    drops.push({x: tip.x, y: tip.y, vx: speed * Math.cos(along) + 24 * (Math.random() - .5),
                vy: speed * Math.sin(along) + 24 * (Math.random() - .5), r: 3.2, colour: '#4a90d9', splash: true, life: 9});
  }
}

function moveDrops(dt) {
  for (let i = drops.length - 1; i >= 0; i--) {
    const d = drops[i];
    d.vy += 900 * dt;  // gravity, in pixels per second squared
    d.x += d.vx * dt;
    d.y += d.vy * dt;
    d.life -= dt;
    if (d.y >= GROUND + 6 || d.life <= 0) {
      drops.splice(i, 1);
      if (d.splash) {  // each drop that lands kicks up two small ones
        for (let k = 0; k < 2; k++) {
          drops.push({x: d.x, y: GROUND + 4, vx: 90 * (Math.random() - .5), vy: -90 - 80 * Math.random(), r: 1.6, colour: d.colour, life: 0.35});
        }
      }
      continue;
    }
    ctx.fillStyle = d.colour;
    ctx.beginPath();
    ctx.arc(d.x, d.y, d.r, 0, 2 * Math.PI);
    ctx.fill();
  }
  if (drops.length > 500) drops.splice(0, drops.length - 500);
}

let last = performance.now();
function frame(time) {
  const dt = Math.min((time - last) / 1000, 0.05), ease = Math.min(1, dt * 8);
  last = time;
  if (data) {
    const step = ROLES.indexOf(data.step), growing = data.mode === 'growing';
    const mulch = !growing ? 0 : step === 1 ? data.meter : step === 2 ? 100 : 0;
    const grow = data.mode === 'bloomed' ? data.cycles : data.cycle + (step + data.meter / 100) / 3;
    view.tilt += (data.tilt - view.tilt) * ease;
    view.sun += ((data.sun ? 1 : 0) - view.sun) * ease;
    view.mulch += (mulch - view.mulch) * ease;
    view.grow += (grow - view.grow) * ease;
    const angle = view.tilt / 100 * 0.9;  // up to about 52 degrees
    drawSky(time / 1000);
    drawGround();
    drawPlant();
    drawCan(angle);
    if (data.pouring) pour(angle, dt);
    if (data.mulching && !calm && Math.random() < dt * 40) {
      drops.push({x: PLANT_X + 160 * (Math.random() - .5), y: GROUND - 150, vx: 0, vy: 0, r: 3.5, colour: '#a87b4f', life: 3});
    }
    moveDrops(dt);
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

async function poll() {
  try {
    const response = await fetch('/api/state', {cache: 'no-store', signal: AbortSignal.timeout(4000)});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    data = await response.json();
    renderHud();
  } catch (error) {
    byId('connection').textContent = 'Display connection lost. Restart the laptop server';
    byId('status-dot').classList.remove('connected');
  } finally {
    setTimeout(poll, 200);
  }
}
poll();
