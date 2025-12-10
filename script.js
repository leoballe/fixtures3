// Script para el generador de fixtures con asignación manual

// URL base del backend. Si se sirve desde Flask en el mismo host, usar ruta relativa
const BASE_URL = '';

const uploadBtn = document.getElementById('upload-btn');
const generateBtn = document.getElementById('generate-btn');
const teamsFileInput = document.getElementById('teams_file');
const matchListDiv = document.getElementById('match-list');
const scheduleContainer = document.getElementById('schedule-container');

let teamsLoaded = false;
let draggedCard = null;

// Subir CSV de equipos al backend
uploadBtn.addEventListener('click', async () => {
  const file = teamsFileInput.files[0];
  if (!file) {
    alert('Seleccione un archivo CSV de equipos.');
    return;
  }
  const formData = new FormData();
  formData.append('file', file, file.name);
  try {
    const res = await fetch(`${BASE_URL}/import_teams`, {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || 'Error al cargar equipos');
      return;
    }
    teamsLoaded = true;
    matchListDiv.innerHTML = '<h2>Partidos</h2><p class="placeholder">Genere horarios para ver los partidos.</p>';
    alert(`Se cargaron ${data.teams.length} equipos.`);
  } catch (err) {
    console.error(err);
    alert('Error de red al cargar equipos');
  }
});

// Generar horarios y lista de partidos
generateBtn.addEventListener('click', async () => {
  if (!teamsLoaded) {
    alert('Primero cargue un archivo CSV de equipos.');
    return;
  }
  const system = document.getElementById('system').value;
  const homeAndAway = document.getElementById('home_and_away').checked;
  const days = parseInt(document.getElementById('days').value, 10);
  const fields = parseInt(document.getElementById('fields').value, 10);
  const matchDuration = parseInt(document.getElementById('match_duration').value, 10);
  const startTime = document.getElementById('start_time').value;
  const endTime = document.getElementById('end_time').value;
  const middayInput = document.getElementById('midday_break').value.trim();
  let middayBreak = null;
  if (middayInput) {
    const parts = middayInput.split(',');
    if (parts.length === 2) {
      middayBreak = [parts[0].trim(), parts[1].trim()];
    }
  }
  const body = {
    system: system,
    days: days,
    fields: fields,
    start_time: startTime,
    end_time: endTime,
    match_duration: matchDuration,
    home_and_away: homeAndAway,
  };
  if (middayBreak) body.midday_break = middayBreak;
  try {
    const res = await fetch(`${BASE_URL}/generate_parts`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || 'Error al generar datos');
      return;
    }
    renderMatches(data.matches);
    renderSchedule(data.timeslots, fields, matchDuration);
  } catch (err) {
    console.error(err);
    alert('Error de red al generar datos');
  }
});

// Renderiza la lista de partidos como tarjetas arrastrables
function renderMatches(matches) {
  matchListDiv.innerHTML = '<h2>Partidos</h2>';
  if (!matches || matches.length === 0) {
    const p = document.createElement('p');
    p.textContent = 'No hay partidos disponibles.';
    matchListDiv.appendChild(p);
    return;
  }
  matches.forEach((m) => {
    const card = document.createElement('div');
    card.className = 'match-card';
    card.draggable = true;
    // Guardar datos para restricciones
    card.dataset.home = m.home;
    card.dataset.away = m.away;
    card.dataset.zone = m.zone;
    card.dataset.round = m.round;
    card.innerHTML = `<strong>${m.home} vs ${m.away}</strong><br><small>Zona ${m.zone}, Ronda ${m.round}</small>`;
    card.addEventListener('dragstart', handleDragStart);
    matchListDiv.appendChild(card);
  });
}

// Renderiza la tabla de horarios por día y cancha
function renderSchedule(timeslots, fieldsCount, matchDuration) {
  scheduleContainer.innerHTML = '<h2>Horarios</h2>';
  if (!timeslots || timeslots.length === 0) {
    const p = document.createElement('p');
    p.textContent = 'No se generaron horarios.';
    scheduleContainer.appendChild(p);
    return;
  }
  // Agrupar slots por día
  const byDay = {};
  timeslots.forEach((ts) => {
    if (!byDay[ts.day]) byDay[ts.day] = [];
    byDay[ts.day].push(ts);
  });
  Object.keys(byDay).forEach((day) => {
    const slots = byDay[day];
    // Crear enumeración local para numerar los slots del día
    const enumeration = {};
    slots.forEach((slot, idx) => {
      enumeration[slot.index] = idx + 1;
    });
    // Obtener campos y horarios únicos en orden
    const fields = [...new Set(slots.map((s) => s.field))];
    const times = [...new Set(slots.map((s) => s.time))];
    // Ordenar las horas
    times.sort((a, b) => timeToMinutes(a) - timeToMinutes(b));
    // Construir tabla
    const table = document.createElement('table');
    table.className = 'schedule-day';
    const caption = document.createElement('caption');
    caption.textContent = `Día ${day}`;
    table.appendChild(caption);
    // Cabecera
    const thead = document.createElement('thead');
    const trh = document.createElement('tr');
    const emptyTh = document.createElement('th');
    emptyTh.textContent = '';
    trh.appendChild(emptyTh);
    fields.forEach((field) => {
      const th = document.createElement('th');
      th.textContent = field;
      trh.appendChild(th);
    });
    thead.appendChild(trh);
    table.appendChild(thead);
    // Cuerpo
    const tbody = document.createElement('tbody');
    times.forEach((time) => {
      const tr = document.createElement('tr');
      const thTime = document.createElement('th');
      thTime.textContent = time;
      tr.appendChild(thTime);
      fields.forEach((field) => {
        const td = document.createElement('td');
        td.className = 'timeslot';
        // Buscar slot correspondiente
        const slot = slots.find((s) => s.time === time && s.field === field);
        if (slot) {
          td.dataset.day = slot.day;
          td.dataset.time = slot.time;
          td.dataset.field = slot.field;
          td.dataset.index = slot.index;
          td.dataset.matchDuration = matchDuration;
          // Mostrar número de slot dentro de la celda
          const numSpan = document.createElement('span');
          numSpan.className = 'slot-number';
          numSpan.textContent = enumeration[slot.index] || '';
          td.appendChild(numSpan);
          // Eventos de drag & drop
          td.addEventListener('dragover', handleDragOver);
          td.addEventListener('drop', handleDrop);
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    scheduleContainer.appendChild(table);
  });
}

// Manejo de drag & drop
function handleDragStart(ev) {
  draggedCard = this;
}

function handleDragOver(ev) {
  ev.preventDefault();
}

function handleDrop(ev) {
  ev.preventDefault();
  if (!draggedCard) return;
  const cell = this;
  // Evitar sobrescribir celdas ocupadas
  if (cell.classList.contains('filled')) {
    return;
  }
  const day = parseInt(cell.dataset.day, 10);
  const time = cell.dataset.time;
  const field = cell.dataset.field;
  const matchDuration = parseInt(cell.dataset.matchDuration, 10);
  const restMinutes = matchDuration; // descanso mínimo igual a duración
  const draggedHome = draggedCard.dataset.home;
  const draggedAway = draggedCard.dataset.away;
  // Comprobar si alguno de los equipos ya tiene partido cercano
  const filledSlots = document.querySelectorAll('td.timeslot.filled');
  for (const fs of filledSlots) {
    const fsDay = parseInt(fs.dataset.day, 10);
    if (fsDay !== day) continue;
    const fsTime = fs.dataset.time;
    const fsHome = fs.dataset.home;
    const fsAway = fs.dataset.away;
    // Comparar equipos
    if (fsHome === draggedHome || fsHome === draggedAway || fsAway === draggedHome || fsAway === draggedAway) {
      // Calcular diferencia de tiempo
      const diff = Math.abs(timeToMinutes(fsTime) - timeToMinutes(time));
      if (diff < restMinutes) {
        alert('No se puede asignar: equipo ya tiene un partido cercano.');
        return;
      }
    }
  }
  // Asignar partido a la celda
  cell.classList.add('filled');
  // Aplicar color según la zona del partido
  const zone = draggedCard.dataset.zone;
  const zoneColor = zoneColors[zone] || '#cfe8cf';
  cell.style.backgroundColor = zoneColor;
  cell.innerHTML = `<strong>${draggedHome} vs ${draggedAway}</strong><br><small>Zona ${draggedCard.dataset.zone}, Ronda ${draggedCard.dataset.round}</small>`;
  cell.dataset.home = draggedHome;
  cell.dataset.away = draggedAway;
  cell.dataset.zone = draggedCard.dataset.zone;
  cell.dataset.round = draggedCard.dataset.round;
  // Eliminar tarjeta
  draggedCard.remove();
  draggedCard = null;
}

// Utilidades para conversión de horarios
function timeToMinutes(t) {
  const [h, m] = t.split(':').map((v) => parseInt(v, 10));
  return h * 60 + m;
}