/**
 * Trader Control Center V2.1 - Interactive Frontend Application
 */

const API_BASE = '/api/v1';
const API_TOKEN = 'hermes-trader-secret-key-v2.1';

let ws = null;
let currentTab = 'dashboard';

// Initialize App
document.addEventListener('DOMContentLoaded', () => {
  initTabNavigation();
  initWebSocket();
  loadAllData();

  // Periodically refresh dashboard state
  setInterval(loadDashboardData, 5000);
});

// ---------------------------------------------------------------------------
// Tab & Navigation Manager
// ---------------------------------------------------------------------------

function initTabNavigation() {
  const hash = window.location.hash.replace('#', '');
  if (hash && document.getElementById(`view-${hash}`)) {
    showTab(hash);
  } else {
    showTab('dashboard');
  }
}

function showTab(tabId) {
  currentTab = tabId;

  // Hide all sections
  document.querySelectorAll('.tab-view').forEach(view => {
    view.classList.add('hidden');
  });

  // Deactivate all nav links
  document.querySelectorAll('.nav-link').forEach(link => {
    link.classList.remove('active');
  });

  // Show active view
  const targetView = document.getElementById(`view-${tabId}`);
  if (targetView) {
    targetView.classList.remove('hidden');
  }

  // Activate nav link
  const targetNav = document.getElementById(`nav-${tabId}`);
  if (targetNav) {
    targetNav.classList.add('active');
  }

  // Update Breadcrumb
  const breadcrumbTitle = document.getElementById('breadcrumb-title');
  const breadcrumbSub = document.getElementById('breadcrumb-sub');
  
  const formattedTitle = tabId.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  if (breadcrumbTitle) breadcrumbTitle.innerText = formattedTitle;
  if (breadcrumbSub) breadcrumbSub.innerText = `Hermes V2.1 / ${formattedTitle}`;

  // Load view specific data
  switch (tabId) {
    case 'dashboard':
      loadDashboardData();
      break;
    case 'positions':
      loadPositions();
      break;
    case 'orders':
      loadOrders();
      break;
    case 'risk-center':
      loadRiskStatus();
      break;
    case 'ai-decisions':
      loadAIDecisions();
      break;
    case 'market-intelligence':
      loadMarketIntelligence();
      break;
    case 'strategies':
      loadStrategies();
      break;
    case 'knowledge':
      loadKnowledgeDashboard();
      break;
    case 'knowledge-notes':
      loadKnowledgeNotes();
      break;
    case 'trading-journal':
      loadTradingJournal();
      break;
    case 'knowledge-graph':
      loadKnowledgeGraph();
      break;
    case 'ai-learning':
      loadLearningPipeline();
      break;
    case 'audit-log':
      loadAuditLogs();
      break;
  }
}

// ---------------------------------------------------------------------------
// REST API Helpers
// ---------------------------------------------------------------------------

async function apiFetch(endpoint, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    'X-API-Key': API_TOKEN,
    ...options.headers,
  };

  try {
    const res = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(errData.detail || `HTTP Error ${res.status}`);
    }
    return await res.json();
  } catch (err) {
    console.error(`API Fetch Error [${endpoint}]:`, err);
    showToast(`Error: ${err.message}`, 'danger');
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Data Loaders
// ---------------------------------------------------------------------------

async function loadAllData() {
  await loadSystemStatus();
  await loadDashboardData();
}

async function loadSystemStatus() {
  try {
    const data = await apiFetch('/system/status');
    
    document.getElementById('topbar-adapter').innerText = data.exchange_adapter || 'Mock Exchange';
    document.getElementById('topbar-risk').innerText = data.risk_engine || 'DETERMINISTIC';
    document.getElementById('topbar-mode').innerText = data.trading_mode || 'DEVELOPMENT';

    const dot = document.getElementById('adapter-dot');
    if (data.kill_switch_active) {
      dot.className = 'w-2 h-2 rounded-full bg-accentSec mr-2';
    } else {
      dot.className = 'w-2 h-2 rounded-full bg-success mr-2 pulse-dot';
    }
  } catch (e) {
    console.warn('System status update failed', e);
  }
}

async function loadDashboardData() {
  try {
    const status = await apiFetch('/system/status');
    const portfolio = await apiFetch('/portfolio');
    const trades = await apiFetch('/trades');

    document.getElementById('dash-equity').innerText = `$${portfolio.total_equity.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
    document.getElementById('dash-pnl').innerText = `+$${portfolio.net_pnl_today.toFixed(2)}`;
    document.getElementById('dash-risk-ver').innerText = status.risk_policy_version || 'v1.4';
    document.getElementById('dash-drawdown').innerText = portfolio.drawdown_status || 'Safe';

    // Render Trades Table
    const tbody = document.getElementById('table-trades-body');
    if (tbody && trades) {
      tbody.innerHTML = trades.map(t => `
        <tr class="hover:bg-surface-light transition-colors duration-200">
          <td class="px-4 py-3 font-mono text-muted">${t.trade_id}</td>
          <td class="px-4 py-3 font-semibold">${t.symbol}</td>
          <td class="px-4 py-3 ${t.side === 'LONG' || t.side === 'BUY' ? 'text-success' : 'text-accentSec'}">${t.side}</td>
          <td class="px-4 py-3 text-muted">${t.strategy_version || 'breakout_v2.1'}</td>
          <td class="px-4 py-3 font-mono">${t.entry_price ? '$' + t.entry_price.toLocaleString() : '-'}</td>
          <td class="px-4 py-3 text-right font-mono ${t.net_pnl >= 0 ? 'text-success' : 'text-accentSec'}">${t.net_pnl ? (t.net_pnl >= 0 ? '+' : '') + '$' + t.net_pnl.toFixed(2) : '-'}</td>
          <td class="px-4 py-3 text-center">
            <span class="inline-flex items-center px-2 py-0.5 rounded text-xxs font-medium ${t.risk_decision === 'APPROVED' ? 'bg-success/10 text-success border border-success/20' : 'bg-accentSec/10 text-accentSec border border-accentSec/20'}">${t.risk_decision || 'APPROVED'}</span>
          </td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.warn('Dashboard load error', e);
  }
}

async function loadPositions() {
  const positions = await apiFetch('/positions');
  const tbody = document.getElementById('table-positions-body');
  if (tbody) {
    tbody.innerHTML = positions.map(p => `
      <tr class="hover:bg-surface-light transition-colors duration-200">
        <td class="px-4 py-3 font-semibold">${p.symbol}</td>
        <td class="px-4 py-3 ${p.side === 'LONG' ? 'text-success' : 'text-accentSec'}">${p.side}</td>
        <td class="px-4 py-3 font-mono">${p.size}</td>
        <td class="px-4 py-3 font-mono">$${p.entry_price.toLocaleString()}</td>
        <td class="px-4 py-3 font-mono">$${p.mark_price ? p.mark_price.toLocaleString() : p.entry_price.toLocaleString()}</td>
        <td class="px-4 py-3 font-mono ${p.unrealized_pnl >= 0 ? 'text-success' : 'text-accentSec'}">+$${p.unrealized_pnl.toFixed(2)}</td>
        <td class="px-4 py-3 text-center">
          <button onclick="closePosition('${p.symbol}', '${p.side}', ${p.size})" class="px-2 py-1 bg-accentSec/10 text-accentSec hover:bg-accentSec/20 border border-accentSec/30 rounded text-xxs font-semibold">
            Close Position
          </button>
        </td>
      </tr>
    `).join('');
  }
}

async function loadOrders() {
  const orders = await apiFetch('/orders');
  const tbody = document.getElementById('table-orders-body');
  if (tbody) {
    tbody.innerHTML = orders.map(o => `
      <tr class="hover:bg-surface-light transition-colors duration-200">
        <td class="px-4 py-3 font-mono text-muted">${o.order_id}</td>
        <td class="px-4 py-3 font-mono text-muted">${o.client_order_id || '-'}</td>
        <td class="px-4 py-3 font-semibold">${o.symbol}</td>
        <td class="px-4 py-3 ${o.side === 'BUY' ? 'text-success' : 'text-accentSec'}">${o.side}</td>
        <td class="px-4 py-3 font-mono">${o.quantity}</td>
        <td class="px-4 py-3 font-semibold text-accent">${o.status}</td>
        <td class="px-4 py-3 text-center">
          ${o.status === 'OPEN' ? `<button onclick="cancelOrder('${o.order_id}')" class="px-2 py-1 bg-warning/10 text-warning hover:bg-warning/20 border border-warning/30 rounded text-xxs font-semibold">Cancel</button>` : '<span class="text-muted">-</span>'}
        </td>
      </tr>
    `).join('');
  }
}

async function loadRiskStatus() {
  const risk = await apiFetch('/risk/status');
  const grid = document.getElementById('validators-grid');
  if (grid && risk.validators) {
    grid.innerHTML = risk.validators.map(v => `
      <div class="p-3 bg-surface-light rounded border border-border flex justify-between items-center text-xs">
        <div>
          <div class="font-mono text-muted text-xxs">${v.id}</div>
          <div class="font-medium text-text">${v.name}</div>
        </div>
        <span class="px-2 py-0.5 rounded text-xxs font-mono ${v.status === 'PASS' ? 'bg-success/10 text-success border border-success/20' : 'bg-accentSec/10 text-accentSec border border-accentSec/20'}">${v.status}</span>
      </div>
    `).join('');
  }
}

async function loadAIDecisions() {
  const decisions = await apiFetch('/ai/decisions');
  const container = document.getElementById('ai-decisions-list');
  if (container) {
    container.innerHTML = decisions.map(d => `
      <div class="p-4 bg-surface-light rounded border border-border space-y-2 text-xs">
        <div class="flex justify-between items-center">
          <div class="font-semibold text-text">${d.symbol} (${d.side}) - LLM Confidence: <span class="text-accent">${(d.llm_confidence * 100).toFixed(0)}%</span></div>
          <span class="px-2 py-0.5 rounded text-xxs font-mono ${d.risk_decision === 'APPROVED' ? 'bg-success/10 text-success border border-success/20' : 'bg-accentSec/10 text-accentSec border border-accentSec/20'}">${d.risk_decision}</span>
        </div>
        <div class="text-muted">${d.reasoning}</div>
        <div class="text-xxs font-mono text-muted flex justify-between">
          <span>Proposal: ${d.proposal_id}</span>
          <span>${d.timestamp}</span>
        </div>
      </div>
    `).join('');
  }
}

async function loadMarketIntelligence() {
  const intel = await apiFetch('/market/regimes');
  document.getElementById('regime-current').innerText = intel.current_regime || 'BULL';
  document.getElementById('regime-adx').innerText = intel.adx_trend_strength || '34.5';
  document.getElementById('regime-atr').innerText = intel.atr_volatility || '420.0';
}

async function loadStrategies() {
  const strats = await apiFetch('/strategies');
  const tbody = document.getElementById('table-strategies-body');
  if (tbody) {
    tbody.innerHTML = strats.map(s => `
      <tr class="hover:bg-surface-light transition-colors duration-200">
        <td class="px-4 py-3 font-semibold">${s.strategy_id}</td>
        <td class="px-4 py-3 font-mono text-muted">v${s.version}</td>
        <td class="px-4 py-3 font-semibold text-accent">${s.lifecycle}</td>
        <td class="px-4 py-3">
          <span class="px-2 py-0.5 rounded text-xxs ${s.immutable ? 'bg-success/10 text-success border border-success/20' : 'bg-warning/10 text-warning border border-warning/20'}">${s.immutable ? 'IMMUTABLE (PRODUCTION)' : 'MUTABLE'}</span>
        </td>
      </tr>
    `).join('');
  }
}

async function loadKnowledgeDashboard() {
  const data = await apiFetch('/knowledge/dashboard');
  document.getElementById('know-notes-count').innerText = data.total_notes || '0';
  document.getElementById('know-vault-path').innerText = data.vault_path || '~/obsidian-vault';
  document.getElementById('know-queue-size').innerText = `${data.queued_sync_tasks || 0} tasks`;
}

async function loadKnowledgeNotes() {
  const notes = await apiFetch('/knowledge/notes');
  const side = document.getElementById('notes-list-side');
  if (side) {
    if (!notes || notes.length === 0) {
      side.innerHTML = '<div class="text-xs text-muted">No notes indexed yet. Vault synced asynchronously.</div>';
      return;
    }
    side.innerHTML = notes.map(n => `
      <div onclick="readNote('${n.note_id}')" class="p-2.5 bg-surface-light hover:bg-surface rounded border border-border cursor-pointer text-xs space-y-1">
        <div class="font-semibold text-accent">${n.title}</div>
        <div class="text-xxs text-muted">${n.category} | ${n.tags ? n.tags.join(', ') : ''}</div>
      </div>
    `).join('');
  }
}

async function readNote(noteId) {
  const notes = await apiFetch('/knowledge/notes');
  const note = notes.find(n => n.note_id === noteId);
  const reader = document.getElementById('note-reader-content');
  if (reader && note) {
    reader.innerHTML = `
      <div class="text-accent font-bold mb-2">${note.title}</div>
      <div class="text-xxs text-muted mb-4">Category: ${note.category} | Author: ${note.author}</div>
      <div class="text-text whitespace-pre-wrap">${note.content}</div>
    `;
  }
}

async function loadKnowledgeGraph() {
  const graph = await apiFetch('/knowledge/graph');
  const container = document.getElementById('graph-container');
  if (container && graph.nodes) {
    // Simple SVG representation of nodes
    const svg = document.getElementById('graph-svg');
    svg.innerHTML = `
      <g>
        ${graph.nodes.map((n, idx) => {
          const cx = 100 + (idx * 120) % 600;
          const cy = 100 + Math.floor(idx / 5) * 80;
          return `
            <circle cx="${cx}" cy="${cy}" r="18" fill="#00d1ff" opacity="0.8" />
            <text x="${cx}" y="${cy + 30}" font-size="10" fill="#e6eef6" text-anchor="middle">${n.title}</text>
          `;
        }).join('')}
      </g>
    `;
  }
}

async function loadLearningPipeline() {
  const lessons = await apiFetch('/learning/pipeline');
  const container = document.getElementById('pipeline-cards');
  if (container && lessons) {
    container.innerHTML = lessons.map(l => `
      <div class="p-4 bg-surface-light rounded border border-border space-y-3 text-xs">
        <div class="flex justify-between items-center">
          <div class="font-bold text-accent">${l.title} <span class="font-mono text-muted text-xxs">(${l.lesson_id})</span></div>
          <span class="px-2 py-0.5 rounded text-xxs font-mono bg-warning/10 text-warning border border-warning/20">HYPOTHESIS ONLY</span>
        </div>
        <div class="text-muted">${l.description}</div>
        <div class="flex justify-between items-center text-xxs font-mono text-muted">
          <span>Current Stage: <strong class="text-accent">${l.stage}</strong></span>
          <span>Evidence Count: ${l.evidence_count} trades</span>
        </div>
        <div class="pt-2 border-t border-border flex justify-end gap-2">
          ${l.stage === 'HUMAN_APPROVAL' ? `
            <button onclick="advanceLessonStage('${l.lesson_id}', 'PRODUCTION_STRATEGY', true)" class="px-3 py-1 bg-success text-bg font-semibold rounded text-xxs">
              Human Approve & Promote to Production
            </button>
          ` : `
            <button onclick="advanceLessonStage('${l.lesson_id}', 'EVIDENCE_CHECK', false)" class="px-3 py-1 bg-surface hover:bg-border text-text rounded text-xxs border border-border">
              Advance Stage
            </button>
          `}
        </div>
      </div>
    `).join('');
  }
}

async function advanceLessonStage(lessonId, targetStage, humanApproved) {
  try {
    const res = await apiFetch('/learning/advance-stage', {
      method: 'POST',
      body: JSON.stringify({
        lesson_id: lessonId,
        target_stage: targetStage,
        human_approved: humanApproved,
      }),
    });
    if (res.status === 'SUCCESS') {
      showToast(`Lesson advanced to ${targetStage}`, 'success');
      loadLearningPipeline();
    } else {
      showToast(`Stage promotion error: ${res.error}`, 'danger');
    }
  } catch (e) {
    showToast(`Failed to advance lesson: ${e.message}`, 'danger');
  }
}

async function loadAuditLogs() {
  const logs = await apiFetch('/audit/logs');
  const tbody = document.getElementById('table-audit-body');
  if (tbody && logs) {
    tbody.innerHTML = logs.map(l => `
      <tr class="hover:bg-surface-light">
        <td class="px-4 py-2 text-muted">${l.event_id}</td>
        <td class="px-4 py-2 text-accent">${l.event_type}</td>
        <td class="px-4 py-2 ${l.severity === 'CRITICAL' ? 'text-accentSec' : 'text-success'}">${l.severity}</td>
        <td class="px-4 py-2 text-muted">${l.component}</td>
        <td class="px-4 py-2 text-text">${l.message}</td>
        <td class="px-4 py-2 text-muted">${l.timestamp}</td>
      </tr>
    `).join('');
  }
}

// ---------------------------------------------------------------------------
// Actions & Handlers
// ---------------------------------------------------------------------------

async function handleTradeProposal(event) {
  event.preventDefault();
  const payload = {
    symbol: document.getElementById('prop-symbol').value,
    side: document.getElementById('prop-side').value,
    order_type: document.getElementById('prop-order-type').value,
    quantity: parseFloat(document.getElementById('prop-quantity').value),
    price: document.getElementById('prop-price').value ? parseFloat(document.getElementById('prop-price').value) : null,
    llm_confidence: parseFloat(document.getElementById('prop-confidence').value),
  };

  try {
    const res = await apiFetch('/trade/propose', {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    const outBox = document.getElementById('proposal-output');
    const jsonBox = document.getElementById('proposal-json');
    if (outBox && jsonBox) {
      outBox.classList.remove('hidden');
      jsonBox.innerText = JSON.stringify(res, null, 2);
    }

    if (res.status === 'APPROVED') {
      showToast('Trade Proposal APPROVED by Risk Engine and submitted!', 'success');
    } else {
      showToast(`Trade Proposal REJECTED by Risk Engine: ${res.message}`, 'danger');
    }
    loadDashboardData();
  } catch (e) {
    showToast(`Proposal Submission Error: ${e.message}`, 'danger');
  }
}

async function closePosition(symbol, side, size) {
  if (!confirm(`Are you sure you want to close position ${symbol} (${side})?`)) return;

  try {
    const res = await apiFetch('/positions/close', {
      method: 'POST',
      body: JSON.stringify({ symbol, side, size }),
    });
    showToast(`Close position submitted: ${res.status}`, res.status === 'APPROVED' ? 'success' : 'warning');
    loadPositions();
  } catch (e) {
    showToast(`Close position failed: ${e.message}`, 'danger');
  }
}

async function cancelOrder(orderId) {
  try {
    const res = await apiFetch('/orders/cancel', {
      method: 'POST',
      body: JSON.stringify({ order_id: orderId }),
    });
    showToast(`Order ${orderId} cancelled`, 'info');
    loadOrders();
  } catch (e) {
    showToast(`Cancel order failed: ${e.message}`, 'danger');
  }
}

async function triggerHardKill() {
  if (!confirm('CRITICAL ACTION: Activate System Hard Kill Switch? This will freeze all trading execution.')) return;

  try {
    const res = await apiFetch('/system/kill-switch', {
      method: 'POST',
      body: JSON.stringify({ active: true, reason: 'Manual Hard Kill triggered via UI' }),
    });
    showToast('HARD KILL SWITCH ACTIVATED', 'danger');
    loadSystemStatus();
  } catch (e) {
    showToast(`Kill Switch Trigger Failed: ${e.message}`, 'danger');
  }
}

async function changeTradingMode(mode) {
  try {
    await apiFetch('/system/trading-mode', {
      method: 'POST',
      body: JSON.stringify({ mode }),
    });
    showToast(`Trading Mode updated to ${mode}`, 'info');
    loadSystemStatus();
  } catch (e) {
    showToast(`Failed to update mode: ${e.message}`, 'danger');
  }
}

// ---------------------------------------------------------------------------
// WebSocket Client
// ---------------------------------------------------------------------------

function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log('WebSocket connected to Trader Control Center');
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'SYSTEM_LOG') {
        appendTerminalLog(msg.message, msg.level);
      }
    } catch (e) {
      console.warn('WS Message parse error', e);
    }
  };

  ws.onclose = () => {
    console.log('WebSocket closed. Retrying in 3 seconds...');
    setTimeout(initWebSocket, 3000);
  };
}

function appendTerminalLog(text, level = 'INFO') {
  const term = document.getElementById('terminal-logs');
  if (!term) return;

  const now = new Date().toTimeString().split(' ')[0];
  const div = document.createElement('div');
  div.className = level === 'CRITICAL' || level === 'WARNING' ? 'text-warning' : 'text-muted';
  div.innerHTML = `<span class="text-accent">[${now}]</span> ${text}`;

  term.appendChild(div);
  term.scrollTop = term.scrollHeight;
}

// ---------------------------------------------------------------------------
// Toast Notification Utility
// ---------------------------------------------------------------------------

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast';
  
  let icon = 'lucide:info';
  let colorClass = 'text-accent';
  if (type === 'success') { icon = 'lucide:check-circle'; colorClass = 'text-success'; }
  if (type === 'warning') { icon = 'lucide:alert-triangle'; colorClass = 'text-warning'; }
  if (type === 'danger') { icon = 'lucide:alert-octagon'; colorClass = 'text-accentSec'; }

  toast.innerHTML = `
    <span class="iconify ${colorClass}" data-icon="${icon}" data-width="18"></span>
    <span class="flex-1">${message}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}
