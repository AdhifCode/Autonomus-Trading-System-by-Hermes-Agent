# Hermes Monitor V2.1 - Dashboard UI Code

Dokumen ini berisi kode HTML/Tailwind lengkap untuk antarmuka dashboard monitoring sistem trading otomatis (Hermes Agent framework), yang telah disesuaikan secara khusus dengan arsitektur V2.1.

## Penyesuaian Arsitektur yang Diterapkan:
1. **Knowledge Layer (Obsidian Reader)**: Terintegrasi dalam sidebar utama.
2. **Deterministic Risk Engine**: Tercermin pada log terminal dan kolom persetujuan (*approval state*) di tabel transaksi.
3. **Data Operasional (SQLite)**: Ditekankan sebagai *Source of Truth* pada tabel utama.

## Source Code

```html
<!DOCTYPE html>
<html lang="en" class="scroll-smooth">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Hermes System Monitor V2.1</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://code.iconify.design/3/3.1.0/iconify.min.js"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; }
    
    /* Scrollbar Theming */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: #334155; }
    
    /* Custom Quirks */
    .text-xxs { font-size: 0.65rem; line-height: 1rem; }
    .tracking-tight-custom { letter-spacing: -0.025em; }
    .tracking-tighter-custom { letter-spacing: -0.04em; }
  </style>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            bg: '#0b0f14',
            surface: '#0f1720',
            'surface-light': '#16202a',
            accent: '#00d1ff',
            'accent-hover': '#33c2ff',
            accentSec: '#ff6b6b',
            text: '#e6eef6',
            muted: '#9aa8b2',
            success: '#38d89b',
            warning: '#ffb020',
            border: 'rgba(255, 255, 255, 0.06)'
          }
        }
      }
    }
  </script>
</head>
<body class="bg-bg text-text antialiased selection:bg-accent selection:text-bg">

  <!-- SIDEBAR -->
  <aside class="fixed left-0 top-0 h-screen w-64 bg-surface border-r border-border z-40 flex flex-col">
    <div class="h-16 flex items-center px-6 border-b border-border">
      <span class="iconify text-accent mr-2" data-icon="lucide:zap" data-width="20"></span>
      <h1 class="font-semibold tracking-tight-custom text-lg">Hermes V2.1</h1>
    </div>
    
    <nav class="flex-1 overflow-y-auto py-4 space-y-1">
      <div class="px-4 text-xxs font-semibold text-muted uppercase tracking-wider mb-2 mt-4">Trader Control Center</div>
      <a href="#" class="flex items-center px-6 py-2 bg-accent/10 border-r-2 border-accent text-accent hover:bg-surface-light transition-colors duration-200">
        <span class="iconify mr-3" data-icon="lucide:layout-dashboard" data-width="18"></span> Dashboard
      </a>
      <a href="#" class="flex items-center px-6 py-2 text-muted hover:text-text hover:bg-surface-light transition-colors duration-200">
        <span class="iconify mr-3" data-icon="lucide:activity" data-width="18"></span> Trading & Execution
      </a>
      <a href="#" class="flex items-center px-6 py-2 text-muted hover:text-text hover:bg-surface-light transition-colors duration-200">
        <span class="iconify mr-3" data-icon="lucide:shield-check" data-width="18"></span> Risk Center
      </a>
      <a href="#" class="flex items-center px-6 py-2 text-muted hover:text-text hover:bg-surface-light transition-colors duration-200">
        <span class="iconify mr-3" data-icon="lucide:brain" data-width="18"></span> AI Decision Center
      </a>

      <div class="px-4 text-xxs font-semibold text-muted uppercase tracking-wider mb-2 mt-6">Knowledge Base</div>
      <a href="#" class="flex items-center px-6 py-2 text-muted hover:text-text hover:bg-surface-light transition-colors duration-200">
        <span class="iconify mr-3" data-icon="lucide:book-open" data-width="18"></span> Obsidian Reader
      </a>
      <a href="#" class="flex items-center px-6 py-2 text-muted hover:text-text hover:bg-surface-light transition-colors duration-200">
        <span class="iconify mr-3" data-icon="lucide:history" data-width="18"></span> Lessons Learned
      </a>
      
      <div class="px-4 text-xxs font-semibold text-muted uppercase tracking-wider mb-2 mt-6">System Operations</div>
      <a href="#" class="flex items-center px-6 py-2 text-muted hover:text-text hover:bg-surface-light transition-colors duration-200">
        <span class="iconify mr-3" data-icon="lucide:terminal" data-width="18"></span> Audit Log
      </a>
      <a href="#" class="flex items-center px-6 py-2 text-muted hover:text-text hover:bg-surface-light transition-colors duration-200">
        <span class="iconify mr-3" data-icon="lucide:settings" data-width="18"></span> System Control
      </a>
    </nav>
  </aside>

  <!-- TOPBAR -->
  <header class="sticky top-0 h-16 bg-surface/80 backdrop-blur-md border-b border-border z-30 ml-64 flex justify-between items-center px-6">
    <div class="flex items-center space-x-2 text-sm text-muted">
      <span>Dashboard</span>
      <span class="iconify" data-icon="lucide:chevron-right" data-width="14"></span>
      <span class="text-text font-medium">Live Market</span>
    </div>
    
    <div class="flex items-center space-x-6">
      <div class="flex items-center text-xs space-x-4 border-r border-border pr-6">
        <div class="flex items-center">
          <div class="w-2 h-2 rounded-full bg-success mr-2"></div>
          <span class="text-muted mr-1">Adapter:</span> Binance
        </div>
        <div class="flex items-center">
          <span class="iconify text-success mr-1" data-icon="lucide:server" data-width="14"></span>
          <span class="text-muted mr-1">Risk Engine:</span> DETERMINISTIC
        </div>
      </div>
      <button class="flex items-center px-3 py-1.5 rounded bg-accentSec/10 text-accentSec hover:bg-accentSec/20 transition-colors duration-200 text-xs font-semibold">
        <span class="iconify mr-1.5" data-icon="lucide:power" data-width="14"></span> SYSTEM HARD KILL
      </button>
    </div>
  </header>

  <!-- MAIN CONTENT -->
  <main class="ml-64 p-6 min-h-screen space-y-6">
    
    <!-- STATS GRID -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
      <div class="bg-surface border border-border rounded-xl p-4">
        <div class="text-muted text-xs mb-1">Total Equity (Operational)</div>
        <div class="flex items-baseline space-x-2">
          <div class="text-2xl font-semibold tracking-tighter-custom">$42,504.00</div>
        </div>
      </div>
      <div class="bg-surface border border-border rounded-xl p-4">
        <div class="text-muted text-xs mb-1">Net PnL (Today)</div>
        <div class="text-2xl font-semibold tracking-tighter-custom text-success">+$350.00</div>
      </div>
      <div class="bg-surface border border-border rounded-xl p-4">
        <div class="text-muted text-xs mb-1">Risk Policy Version</div>
        <div class="text-2xl font-semibold tracking-tighter-custom">v1.4</div>
      </div>
      <div class="bg-surface border border-border rounded-xl p-4">
        <div class="text-muted text-xs mb-1">Drawdown Status</div>
        <div class="flex items-center space-x-2">
          <div class="text-2xl font-semibold tracking-tighter-custom text-text">Safe</div>
          <span class="iconify text-success opacity-80" data-icon="lucide:shield-check" data-width="20"></span>
        </div>
      </div>
    </div>

    <!-- VISUALIZATION & LOGS -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      
      <!-- Equity Curve -->
      <div class="lg:col-span-2 bg-surface border border-border rounded-xl p-4 h-72 flex flex-col relative overflow-hidden group">
        <div class="flex justify-between items-center mb-4 relative z-10">
          <h2 class="text-sm font-semibold tracking-tight-custom">Performance via DuckDB/Parquet</h2>
          <span class="iconify text-muted" data-icon="lucide:trending-up" data-width="16"></span>
        </div>
        <div class="flex-1 relative w-full mt-2">
          <div class="absolute inset-0 bg-gradient-to-t from-accent/10 to-transparent bottom-0 h-full w-full"></div>
          <svg class="absolute inset-0 h-full w-full" preserveAspectRatio="none" viewBox="0 0 250 150">
            <path d="M0 150 L50 120 L100 130 L150 90 L200 100 L250 40" stroke="#00d1ff" stroke-width="2" fill="none" />
          </svg>
        </div>
      </div>

      <!-- Agent Terminal -->
      <div class="lg:col-span-1 bg-surface-light border border-border rounded-xl p-3 h-72 overflow-y-auto font-mono text-xxs flex flex-col space-y-1.5 shadow-inner">
        <div class="text-muted mb-2 flex items-center border-b border-border pb-2">
          <span class="iconify mr-2" data-icon="lucide:terminal" data-width="14"></span> 
          Execution & Risk Logs
        </div>
        <div class="text-muted"><span class="text-accent">[08:29:58]</span> Hermes: Generating TradeProposal...</div>
        <div class="text-muted"><span class="text-accent">[08:30:00]</span> Hermes: Hypothesis submitted (Confidence: 0.75).</div>
        <div class="text-warning"><span class="text-accent">[08:30:01]</span> RiskEngine: Validating deterministic rules...</div>
        <div class="text-success"><span class="text-accent">[08:30:01]</span> RiskEngine: APPROVED. Policy v1.4 passed.</div>
        <div class="text-muted"><span class="text-accent">[08:30:02]</span> Execution: Idempotent order TRD-000123 submitted.</div>
        <div class="text-success"><span class="text-accent">[08:30:04]</span> Exchange: Order FILLED. SQLite state updated.</div>
        <div class="text-muted"><span class="text-accent">[14:45:00]</span> RiskEngine: Position closed. Triggering LLM Reflection...</div>
        <div class="text-accentSec"><span class="text-accent">[14:45:05]</span> Obsidian: Queueing knowledge sync (Async).</div>
      </div>
    </div>

    <!-- ACTIVE TRADES TABLE -->
    <div class="bg-surface border border-border rounded-xl overflow-hidden">
      <div class="px-4 py-3 border-b border-border flex justify-between items-center">
        <h2 class="text-sm font-semibold tracking-tight-custom">Canonical Operational State (SQLite)</h2>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="bg-surface-light text-muted text-xxs uppercase tracking-wider">
              <th class="px-4 py-3 font-medium">Trade ID</th>
              <th class="px-4 py-3 font-medium">Symbol</th>
              <th class="px-4 py-3 font-medium">Side</th>
              <th class="px-4 py-3 font-medium">Strategy Version</th>
              <th class="px-4 py-3 font-medium">Entry Price</th>
              <th class="px-4 py-3 font-medium text-right">Net PnL</th>
              <th class="px-4 py-3 font-medium text-center">Risk State</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border text-xs">
            <tr class="hover:bg-surface-light transition-colors duration-200">
              <td class="px-4 py-3 font-mono text-muted">TRD-000123</td>
              <td class="px-4 py-3 font-semibold">BTCUSDT</td>
              <td class="px-4 py-3 text-success">LONG</td>
              <td class="px-4 py-3 text-muted">breakout_v2.1</td>
              <td class="px-4 py-3">$42,500.00</td>
              <td class="px-4 py-3 text-right text-success">+$350.00</td>
              <td class="px-4 py-3 text-center">
                <span class="inline-flex items-center px-2 py-0.5 rounded text-xxs font-medium bg-success/10 text-success border border-success/20">APPROVED</span>
              </td>
            </tr>
            <tr class="hover:bg-surface-light transition-colors duration-200">
              <td class="px-4 py-3 font-mono text-muted">TRD-000124</td>
              <td class="px-4 py-3 font-semibold">ETHUSDT</td>
              <td class="px-4 py-3 text-accentSec">SHORT</td>
              <td class="px-4 py-3 text-muted">momentum_v1.2</td>
              <td class="px-4 py-3">$2,800.00</td>
              <td class="px-4 py-3 text-right text-accentSec">-$15.00</td>
              <td class="px-4 py-3 text-center">
                <span class="inline-flex items-center px-2 py-0.5 rounded text-xxs font-medium bg-success/10 text-success border border-success/20">APPROVED</span>
              </td>
            </tr>
            <tr class="hover:bg-surface-light transition-colors duration-200 opacity-60">
              <td class="px-4 py-3 font-mono text-muted">TRD-000125</td>
              <td class="px-4 py-3 font-semibold">SOLUSDT</td>
              <td class="px-4 py-3 text-success">LONG</td>
              <td class="px-4 py-3 text-muted">breakout_v2.1</td>
              <td class="px-4 py-3">-</td>
              <td class="px-4 py-3 text-right">-</td>
              <td class="px-4 py-3 text-center">
                <span class="inline-flex items-center px-2 py-0.5 rounded text-xxs font-medium bg-accentSec/10 text-accentSec border border-accentSec/20">REJECTED</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </main>
</body>
</html>
```
