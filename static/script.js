// script.js - Assetto Corsa Leaderboard Frontend

// ========== ELEMENTOS DOM ==========
const urlInput = document.getElementById('urlInput');
const loadBtn = document.getElementById('loadBtn');
const btnGeneral = document.getElementById('btnGeneral');
const btnCategoria = document.getElementById('btnCategoria');
const statusMsg = document.getElementById('statusMsg');
const leaderboardOutput = document.getElementById('leaderboardOutput');

// ========== CONFIGURACIÓN ==========
let currentMode = 'general'; // 'general' or 'categoria'
let autoRefreshInterval = null;
const REFRESH_INTERVAL = 30000; // 30 segundos

// ========== SOCKET.IO ==========
const socket = io();

// ========== EVENT LISTENERS ==========
// Botones de modo
btnGeneral.addEventListener('click', () => switchMode('general'));
btnCategoria.addEventListener('click', () => switchMode('categoria'));

// Botón de carga
loadBtn.addEventListener('click', loadLeaderboard);

// Enter en input URL
urlInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    loadLeaderboard();
  }
});

// Socket.IO - actualización en tiempo real
socket.on('cat_update', () => {
  console.log('📡 Actualización recibida via Socket.IO');
  loadLeaderboard();
});

// ========== FUNCIONES PRINCIPALES ==========
function switchMode(mode) {
  currentMode = mode;
  
  if (mode === 'general') {
    btnGeneral.classList.add('is-primary', 'is-active-mode');
    btnGeneral.classList.remove('is-light');
    btnCategoria.classList.remove('is-primary', 'is-active-mode');
    btnCategoria.classList.add('is-light');
  } else {
    btnCategoria.classList.add('is-primary', 'is-active-mode');
    btnCategoria.classList.remove('is-light');
    btnGeneral.classList.remove('is-primary', 'is-active-mode');
    btnGeneral.classList.add('is-light');
  }
  
  // Recargar datos si ya hay datos cargados
  if (leaderboardOutput.innerHTML.trim()) {
    loadLeaderboard();
  }
}

function updateStatus(message, isError = false) {
  statusMsg.textContent = message;
  statusMsg.style.backgroundColor = isError ? 
    'rgba(255, 84, 89, 0.2)' : 'rgba(0, 191, 255, 0.2)';
  statusMsg.style.border = isError ? 
    '2px solid #ff5459' : '2px solid #00bfff';
}

// Convertir tiempo de vuelta a número comparable
function lapToNumber(lap) {
  if (lap === "--") return Number.MAX_SAFE_INTEGER;
  const parts = lap.split(/[:.]/);
  if (parts.length !== 3) return Number.MAX_SAFE_INTEGER;
  const minutes = parseInt(parts[0]) || 0;
  const seconds = parseInt(parts[1]) || 0;
  const millis = parseInt(parts[2]) || 0;
  return minutes * 60000 + seconds * 1000 + millis;
}

// Calcular diferencia respecto al primer tiempo
function calculateGap(firstLap, currentLap) {
  if (currentLap === "--" || firstLap === "--") return "";
  
  const firstMs = lapToNumber(firstLap);
  const currentMs = lapToNumber(currentLap);
  
  if (firstMs >= Number.MAX_SAFE_INTEGER || currentMs >= Number.MAX_SAFE_INTEGER) {
    return "";
  }
  
  const diffMs = currentMs - firstMs;
  if (diffMs <= 0) return "";
  
  const minutes = Math.floor(diffMs / 60000);
  const seconds = Math.floor((diffMs % 60000) / 1000);
  const millis = diffMs % 1000;
  
  if (minutes > 0) {
    return `+${minutes}:${seconds.toString().padStart(2, '0')}.${millis.toString().padStart(3, '0')}`;
  } else {
    return `+${seconds}.${millis.toString().padStart(3, '0')}`;
  }
}

// Cargar datos del leaderboard
async function loadLeaderboard() {
  const inputUrl = urlInput.value.trim();
  if (!inputUrl) {
    updateStatus("❌ Introduce una URL válida del servidor Assetto Corsa", true);
    return;
  }
  
  updateStatus("⏳ Cargando datos del servidor...");
  
  try {
    const response = await fetch('/api/leaderboard', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url: inputUrl}),
    });
    
    const data = await response.json();
    
    if (!response.ok || data.error) {
      throw new Error(data.error || `Error HTTP ${response.status}`);
    }
    
    renderLeaderboard(data);
    updateStatus(`✅ Datos actualizados correctamente (${new Date().toLocaleTimeString()})`);
    
    // Iniciar auto-refresh si no está activo
    startAutoRefresh();
    
  } catch (error) {
    console.error('Error cargando leaderboard:', error);
    updateStatus(`❌ Error: ${error.message}`, true);
    stopAutoRefresh();
  }
}

// Renderizar el leaderboard según el modo actual
function renderLeaderboard(data) {
  if (currentMode === 'general') {
    renderGeneralView(data);
  } else {
    renderCategoryView(data);
  }
}

// Vista general - todos los pilotos juntos
function renderGeneralView(data) {
  let pilots = [];
  
  // Usar datos 'general' si están disponibles, sino combinar categorías
  if (Array.isArray(data.general) && data.general.length > 0) {
    pilots = [...data.general];
  } else if (data.categorias) {
    // Combinar todas las categorías
    for (const cat in data.categorias) {
      pilots = pilots.concat(data.categorias[cat]);
    }
    // Eliminar duplicados por nombre
    const uniquePilots = {};
    for (const pilot of pilots) {
      if (!uniquePilots[pilot.name] || lapToNumber(pilot.bestlap) < lapToNumber(uniquePilots[pilot.name].bestlap)) {
        uniquePilots[pilot.name] = pilot;
      }
    }
    pilots = Object.values(uniquePilots);
  }
  
  // Ordenar por tiempo
  pilots.sort((a, b) => lapToNumber(a.bestlap) - lapToNumber(b.bestlap));
  
  if (pilots.length === 0) {
    leaderboardOutput.innerHTML = '<p style="text-align: center; font-size: 1.2rem;">No hay datos disponibles</p>';
    return;
  }
  
  const firstLap = pilots[0]?.bestlap;
  let html = `
    <h2 class="subtitle">🏆 Clasificación General (${pilots.length} pilotos)</h2>
    <table class="table is-striped is-narrow">
      <thead>
        <tr>
          <th>Pos</th>
          <th>Piloto</th>
          <th>Mejor Tiempo</th>
          <th>Diferencia</th>
        </tr>
      </thead>
      <tbody>`;
  
  pilots.forEach((pilot, i) => {
    const position = i + 1;
    let rowClass = '';
    let positionIcon = '';
    
    // Aplicar clases y iconos del podio
    if (position === 1) {
      rowClass = 'podium-1st';
      positionIcon = '🥇';
    } else if (position === 2) {
      rowClass = 'podium-2nd';
      positionIcon = '🥈';
    } else if (position === 3) {
      rowClass = 'podium-3rd';
      positionIcon = '🥉';
    }
    
    const gap = calculateGap(firstLap, pilot.bestlap);
    
    html += `
      <tr class="${rowClass}">
        <td>${positionIcon} ${position}°</td>
        <td>${pilot.name}</td>
        <td>${pilot.bestlap}</td>
        <td>${gap}</td>
      </tr>`;
  });
  
  html += '</tbody></table>';
  leaderboardOutput.innerHTML = html;
}

// Vista por categorías
function renderCategoryView(data) {
  if (!data.categorias || Object.keys(data.categorias).length === 0) {
    leaderboardOutput.innerHTML = '<p style="text-align: center; font-size: 1.2rem;">No hay categorías disponibles</p>';
    return;
  }
  
  let html = '';
  const categories = Object.keys(data.categorias).sort();
  let totalPilots = 0;
  
  for (const cat of categories) {
    const pilots = data.categorias[cat];
    if (!pilots || pilots.length === 0) continue;
    
    totalPilots += pilots.length;
    const firstLap = pilots[0]?.bestlap;
    
    html += `
      <h2 class="subtitle">🏁 ${cat} (${pilots.length} pilotos)</h2>
      <table class="table is-striped is-narrow">
        <thead>
          <tr>
            <th>Pos</th>
            <th>Piloto</th>
            <th>Mejor Tiempo</th>
            <th>Diferencia</th>
          </tr>
        </thead>
        <tbody>`;
    
    pilots.forEach((pilot, i) => {
      const position = i + 1;
      let rowClass = '';
      let positionIcon = '';
      
      // Aplicar clases y iconos del podio por categoría
      if (position === 1) {
        rowClass = 'podium-1st';
        positionIcon = '🥇';
      } else if (position === 2) {
        rowClass = 'podium-2nd';
        positionIcon = '🥈';
      } else if (position === 3) {
        rowClass = 'podium-3rd';
        positionIcon = '🥉';
      }
      
      const gap = calculateGap(firstLap, pilot.bestlap);
      
      html += `
        <tr class="${rowClass}">
          <td>${positionIcon} ${position}°</td>
          <td>${pilot.name}</td>
          <td>${pilot.bestlap}</td>
          <td>${gap}</td>
        </tr>`;
    });
    
    html += '</tbody></table>';
  }
  
  // Añadir resumen al final
  html += `
    <div style="text-align: center; margin-top: 2rem; padding: 1rem; background-color: rgba(255,255,255,0.8); border-radius: 8px;">
      <strong>📊 Resumen: ${categories.length} categorías • ${totalPilots} pilotos totales</strong>
    </div>`;
  
  leaderboardOutput.innerHTML = html;
}

// Auto-refresh
function startAutoRefresh() {
  if (autoRefreshInterval) return; // Ya está activo
  
  autoRefreshInterval = setInterval(() => {
    console.log('🔄 Auto-refresh ejecutándose...');
    loadLeaderboard();
  }, REFRESH_INTERVAL);
  
  console.log(`🔄 Auto-refresh activado cada ${REFRESH_INTERVAL/1000} segundos`);
}

function stopAutoRefresh() {
  if (autoRefreshInterval) {
    clearInterval(autoRefreshInterval);
    autoRefreshInterval = null;
    console.log('⏹️ Auto-refresh desactivado');
  }
}

// ========== INICIALIZACIÓN ==========
document.addEventListener('DOMContentLoaded', () => {
  console.log('🚀 Assetto Corsa Leaderboard inicializado');
  
  // Cargar datos iniciales si hay URL
  if (urlInput.value.trim()) {
    setTimeout(loadLeaderboard, 500); // Pequeño delay para que se vea la animación
  }
});

// Limpiar interval al cerrar página
window.addEventListener('beforeunload', () => {
  stopAutoRefresh();
});

// ========== FUNCIONES DE UTILIDAD ==========
// Formatear números con separadores de miles
function formatNumber(num) {
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Copiar URL transformada al portapapeles
function copyTransformedUrl() {
  const originalUrl = urlInput.value.trim();
  // Simular la transformación que hace el backend
  let transformedUrl = originalUrl;
  if (originalUrl.includes('/live-timing') && !originalUrl.includes('/api/live-timings/leaderboard.json')) {
    transformedUrl = originalUrl.replace(/\/live-timing(\?|$)/, '/api/live-timings/leaderboard.json$1');
  }
  
  navigator.clipboard.writeText(transformedUrl).then(() => {
    updateStatus('📋 URL transformada copiada al portapapeles');
  }).catch(() => {
    updateStatus('❌ Error copiando URL', true);
  });
}

// Exportar datos a CSV (función bonus)
function exportToCSV() {
  const tables = document.querySelectorAll('table');
  if (tables.length === 0) {
    updateStatus('❌ No hay datos para exportar', true);
    return;
  }
  
  let csvContent = '';
  const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
  
  tables.forEach((table, index) => {
    const rows = table.querySelectorAll('tr');
    rows.forEach(row => {
      const cells = row.querySelectorAll('th, td');
      const rowData = Array.from(cells).map(cell => {
        return '"' + cell.textContent.replace(/"/g, '""') + '"';
      }).join(',');
      csvContent += rowData + '\n';
    });
    csvContent += '\n'; // Separar tablas
  });
  
  // Crear y descargar archivo
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `assetto_leaderboard_${timestamp}.csv`;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  
  updateStatus('📁 Datos exportados a CSV correctamente');
}