/* global React */

// =====================================================================
// Tiny inline icons. 16px viewBox unless noted.
// =====================================================================
const Ico = {
  brand: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M3 8 V6 M6 8 V3 M9 8 V5 M12 8 V7" />
      <path d="M2 11 H14" opacity="0.6" />
    </svg>
  ),
  live: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="8" cy="8" r="3" fill="currentColor" />
      <circle cx="8" cy="8" r="5.5" opacity="0.45" />
    </svg>
  ),
  library: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <rect x="2.5" y="3" width="11" height="10" rx="1.5" />
      <path d="M5 6 H11 M5 9 H11 M5 12 H9" />
    </svg>
  ),
  settings: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="8" cy="8" r="2" />
      <path d="M8 1.5v2M8 12.5v2M14.5 8h-2M3.5 8h-2M12.6 3.4l-1.4 1.4M4.8 11.2l-1.4 1.4M12.6 12.6l-1.4-1.4M4.8 4.8 3.4 3.4" strokeLinecap="round" />
    </svg>
  ),
  search: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
      <circle cx="7" cy="7" r="4.2" />
      <path d="m10.4 10.4 3 3" />
    </svg>
  ),
  bolt: () => (
    <svg viewBox="0 0 16 16" fill="currentColor">
      <path d="M9.5 1 3.2 9h3.6L6 15l6.3-8H8.7z" />
    </svg>
  ),
  recDot: () => (
    <svg viewBox="0 0 16 16" fill="currentColor">
      <circle cx="8" cy="8" r="5" />
    </svg>
  ),
  square: () => (
    <svg viewBox="0 0 16 16" fill="currentColor">
      <rect x="4" y="4" width="8" height="8" rx="1.5" />
    </svg>
  ),
  copy: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="5" y="5" width="8.5" height="8.5" rx="1.5" />
      <path d="M3.5 10.5V4a1.5 1.5 0 0 1 1.5-1.5h6.5" />
    </svg>
  ),
  save: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3h8l2.5 2.5V13a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
      <path d="M5 3v3h5V3M5 10h6" />
    </svg>
  ),
  plus: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
      <path d="M8 3.5v9M3.5 8h9" />
    </svg>
  ),
  refresh: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 8a5 5 0 0 1 8.7-3.3L13.5 3.5M13 8a5 5 0 0 1-8.7 3.3L2.5 12.5" />
      <path d="M13.5 1.5v3h-3M2.5 14.5v-3h3" />
    </svg>
  ),
  sun: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="8" cy="8" r="3" />
      <path strokeLinecap="round" d="M8 1.5v1.5M8 13v1.5M14.5 8h-1.5M3 8H1.5M12.5 3.5l-1 1M4.5 11.5l-1 1M12.5 12.5l-1-1M4.5 4.5l-1-1" />
    </svg>
  ),
  moon: () => (
    <svg viewBox="0 0 16 16" fill="currentColor">
      <path d="M13.5 10.5A6 6 0 1 1 5.5 2.5a5 5 0 0 0 8 8Z" />
    </svg>
  ),
  info: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="8" cy="8" r="6" />
      <path d="M8 7.5v3.5M8 5v.1" strokeLinecap="round" />
    </svg>
  ),
  folder: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round">
      <path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h2.6L7.5 4.5h5A1.5 1.5 0 0 1 14 6v6a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 12V4.5Z" />
    </svg>
  ),
  wave: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
      <path d="M3 8 V6 M5 8 V4 M7 8 V2 M9 8 V5 M11 8 V3.5 M13 8 V6.5" />
    </svg>
  ),
  trash: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <path d="M3 4.5h10M6 4.5V3.5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1M5 4.5l.7 8a1 1 0 0 0 1 1h2.6a1 1 0 0 0 1-1l.7-8" />
    </svg>
  ),
  more: () => (
    <svg viewBox="0 0 16 16" fill="currentColor">
      <circle cx="4" cy="8" r="1.2" /><circle cx="8" cy="8" r="1.2" /><circle cx="12" cy="8" r="1.2" />
    </svg>
  ),
  play: () => (
    <svg viewBox="0 0 16 16" fill="currentColor">
      <path d="M4.5 3.5v9l8-4.5z" />
    </svg>
  ),
  chevR: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="m6 4 4 4-4 4" />
    </svg>
  ),
  chevD: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="m4 6 4 4 4-4" />
    </svg>
  ),
  upload: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 11V3M5 6l3-3 3 3" />
      <path d="M3 11v2a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-2" />
    </svg>
  ),
  external: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 3h4v4M13 3l-6 6M11 9v3.5A.5.5 0 0 1 10.5 13h-7A.5.5 0 0 1 3 12.5v-7A.5.5 0 0 1 3.5 5H7" />
    </svg>
  ),
  check: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m3.5 8.5 3 3 6-6.5" />
    </svg>
  ),
  x: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
      <path d="m4 4 8 8M12 4l-8 8" />
    </svg>
  ),
  download: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 3v8M5 8l3 3 3-3" />
      <path d="M3 13h10" />
    </svg>
  ),
  spark: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 1.5 9.4 5.2 13.5 6 9.4 6.8 8 10.5 6.6 6.8 2.5 6 6.6 5.2 8 1.5Z" />
      <path d="M13 11l.5 1.5L15 13l-1.5.5L13 15l-.5-1.5L11 13l1.5-.5z" />
    </svg>
  ),
};

// =====================================================================
// Window chrome + sidebar — used by all artboards
// =====================================================================
function AuFrame({ tab, light, recording, onSelect, onQuick, children }) {
  // Fall back to app-level callbacks so the existing tab components don't
  // need to know how to wire them. App.jsx sets these on mount.
  const sel = onSelect || window.__appOnSelect;
  const qk  = onQuick  || window.__appOnQuick;
  // Read the theme straight from window.__appState (which App.jsx mirrors
  // synchronously each render) — using window.__appLight from a useEffect
  // lagged by one render and meant the dark/light toggle didn't take effect.
  let lite = false;
  if (light !== undefined) {
    lite = light;
  } else {
    const cfg = (window.__appState && window.__appState.config) || {};
    lite = (cfg.dark_mode === false);
  }
  return (
    <div className={"au-frame" + (lite ? " au-light" : "")}>
      <AuTitlebar light={lite} recording={recording} />
      <div className="au-body">
        <AuSidebar active={tab} onSelect={sel} onQuick={qk} />
        <div className="au-content">{children}</div>
      </div>
    </div>
  );
}

function AuTitlebar({ light, recording }) {
  return (
    <div className="au-titlebar">
      <div className="tb-title">
        <span className="tb-icon"><Ico.brand /></span>
        Auralis
        {recording && (
          <span style={{ marginLeft: 6, color: 'var(--rec)', fontWeight: 500, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span className="au-rec-dot" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--rec)', boxShadow: '0 0 0 3px rgba(240,101,106,0.18)' }} />
            Recording
          </span>
        )}
      </div>
      <div className="tb-spacer" />
      <div className="tb-controls">
        <div className="tb-btn" title={light ? 'Dark theme' : 'Light theme'}>
          {light ? <Ico.moon /> : <Ico.sun />}
        </div>
        <div className="tb-btn" title="Minimize">
          <svg width="11" height="11" viewBox="0 0 11 11"><path d="M2 5.5h7" stroke="currentColor" strokeWidth="1" /></svg>
        </div>
        <div className="tb-btn" title="Maximize">
          <svg width="11" height="11" viewBox="0 0 11 11"><rect x="1.5" y="1.5" width="8" height="8" stroke="currentColor" strokeWidth="1" fill="none" /></svg>
        </div>
        <div className="tb-btn tb-close" title="Close">
          <svg width="11" height="11" viewBox="0 0 11 11"><path d="m1.5 1.5 8 8M9.5 1.5l-8 8" stroke="currentColor" strokeWidth="1.1" /></svg>
        </div>
      </div>
    </div>
  );
}

function AuSidebar({ active = 'live', onSelect, onQuick }) {
  const items = [
    { id: 'live', icon: <Ico.live />, label: 'Live', kbd: '1' },
    { id: 'library', icon: <Ico.library />, label: 'Library', kbd: '2' },
    { id: 'settings', icon: <Ico.settings />, label: 'Settings', kbd: '3' },
  ];
  const pick = (id) => { if (onSelect) onSelect(id); };
  const quick = (id) => { if (onQuick) onQuick(id); };
  return (
    <aside className="au-sidebar">
      <div className="au-sb-brand">
        <span className="brand-mark"><Ico.brand /></span>
        Auralis
      </div>

      <div className="au-sb-group-label">Workspace</div>
      {items.map(it => (
        <div key={it.id}
             className={"au-sb-item" + (active === it.id ? " is-active" : "")}
             onClick={() => pick(it.id)}>
          <span className="sb-ico">{it.icon}</span>
          <span style={{ flex: 1 }}>{it.label}</span>
          <span style={{ fontSize: 11, color: 'var(--text-4)', fontFamily: 'var(--font-mono)' }}>{it.kbd}</span>
        </div>
      ))}

      <div className="au-sb-group-label">Quick</div>
      <div className="au-sb-item" onClick={() => quick('open-folder')}>
        <span className="sb-ico"><Ico.folder /></span>
        <span style={{ flex: 1 }}>Open recordings folder</span>
      </div>
      <div className="au-sb-item" onClick={() => quick('about')}>
        <span className="sb-ico"><Ico.info /></span>
        <span style={{ flex: 1 }}>About Auralis</span>
      </div>

      <div className="au-sb-foot">
        <div className="foot-avatar">A</div>
        <div className="foot-meta" onClick={() => quick('status-click')}
             title="Open Settings → Transcription">
          <span className="foot-name">Local · offline</span>
          <span className="foot-sub" id="au-status-sub">Whisper · ready</span>
        </div>
      </div>
    </aside>
  );
}

// =====================================================================
// Re-usable bits used across artboards
// =====================================================================
function AuTopbar({ title, sub, actions }) {
  return (
    <div className="au-topbar">
      <h1>{title}</h1>
      {sub && <div className="top-sub">{sub}</div>}
      <div className="top-spacer" />
      <div className="top-actions">{actions}</div>
    </div>
  );
}

function AuToast({ icon, title, body, action }) {
  return (
    <div className="au-toast">
      <div className="t-ico">{icon || <Ico.check />}</div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <span className="t-title">{title}</span>
        {body && <span style={{ color: 'var(--text-3)' }}>{body}</span>}
      </div>
      {action && <span className="t-action">{action}</span>}
      <span className="t-dismiss"><Ico.x /></span>
    </div>
  );
}

Object.assign(window, { AuFrame, AuTopbar, AuToast, Ico });
