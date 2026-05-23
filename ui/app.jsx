/* global React, ReactDOM, eel,
   LiveIdle, LiveRecording, LivePostProcessing,
   Library, Settings */

// =========================================================================
// Auralis — App entry point. See README "UI function inventory".
// =========================================================================

const useState = React.useState;
const useEffect = React.useEffect;
const useRef = React.useRef;
const useCallback = React.useCallback;

// --- Eel wrappers ---------------------------------------------------------
const api = {
  call: async (name, ...args) => {
    if (!window.eel || !eel[name]) return null;
    try { return await eel[name](...args)(); } catch (e) { console.error(name, e); return null; }
  },
};

const Api = {
  getState:           ()       => api.call('get_state'),
  startRecording:     (c, k)   => api.call('start_recording', c, k),
  stopRecording:      ()       => api.call('stop_recording'),
  saveTranscriptNow:  ()       => api.call('save_transcript_now'),
  recopyLastTrigger:  ()       => api.call('recopy_last_trigger'),
  forceVocabRefresh:  ()       => api.call('force_vocab_refresh'),
  newCourse:          (name)   => api.call('new_course', name),
  deleteRecording:    (path)   => api.call('delete_recording', path),
  moveRecording:      (p, t)   => api.call('move_recording', p, t),
  renameRecording:    (p, n)   => api.call('rename_recording', p, n),
  rerunPostprocess:   (path)   => api.call('rerun_postprocess', path),
  openPath:           (path)   => api.call('open_path', path),
  revealInFolder:     (path)   => api.call('reveal_in_folder', path),
  saveConfig:         (partial)=> api.call('save_config', partial),
  refreshDevices:     ()       => api.call('refresh_devices'),
  refreshApps:        ()       => api.call('refresh_apps'),
  audioSessionsCount: ()       => api.call('audio_sessions_count'),
  setTheme:           (dark)   => api.call('set_theme', dark),
  applyModel:         (label)  => api.call('apply_model', label),
  importWav:          ()       => api.call('import_wav'),
  restoreDefaults:    ()       => api.call('restore_defaults'),
  resetSession:       ()       => api.call('reset_session'),
  cancelPolish:       ()       => api.call('cancel_polish'),
  setupChecklist:     ()       => api.call('setup_checklist'),
  getModelStatus:     (l)      => api.call('get_model_status', l),
  showAbout:          ()       => api.call('show_about'),
  dismissOnboarding:  ()       => api.call('dismiss_onboarding'),
};
window.Api = Api;

// --- Push events from Python -----------------------------------------------
//
// CRITICAL: Eel's Python side parses these source files at eel.init() time
// to discover the JS-exposed functions. The parser is strict — each call
// must be `eel.expose(name, 'literal_string')` with NO '(' or '=' inside
// the args. That means we have to declare each stub as a named function
// (no inline expressions, no default args, no destructuring), then pass
// just the bare name.
//
// _push_handlers is a registry the App component populates on mount; the
// stubs forward calls to whichever handler is currently installed.

const _push_handlers = {};
function installPushHandlers(handlers) { Object.assign(_push_handlers, handlers); }

function _h_state_patch(p)       { if (_push_handlers.push_state_patch)       _push_handlers.push_state_patch(p); }
function _h_toast(t)              { if (_push_handlers.push_toast)              _push_handlers.push_toast(t); }
function _h_transcript_segment(s) { if (_push_handlers.push_transcript_segment) _push_handlers.push_transcript_segment(s); }
function _h_trigger(t)            { if (_push_handlers.push_trigger)            _push_handlers.push_trigger(t); }
function _h_dyn_vocab(v)          { if (_push_handlers.push_dyn_vocab)          _push_handlers.push_dyn_vocab(v); }
function _h_recording_state(r)    { if (_push_handlers.push_recording_state)    _push_handlers.push_recording_state(r); }
function _h_polish_progress(p)    { if (_push_handlers.push_polish_progress)    _push_handlers.push_polish_progress(p); }
function _h_audio_level(l)        { if (_push_handlers.push_audio_level)        _push_handlers.push_audio_level(l); }
function _h_library_changed()     { if (_push_handlers.push_library_changed)    _push_handlers.push_library_changed(); }
function _h_status(m)             { if (_push_handlers.push_status)             _push_handlers.push_status(m); }

if (window.eel) {
  eel.expose(_h_state_patch,        'push_state_patch');
  eel.expose(_h_toast,              'push_toast');
  eel.expose(_h_transcript_segment, 'push_transcript_segment');
  eel.expose(_h_trigger,            'push_trigger');
  eel.expose(_h_dyn_vocab,          'push_dyn_vocab');
  eel.expose(_h_recording_state,    'push_recording_state');
  eel.expose(_h_polish_progress,    'push_polish_progress');
  eel.expose(_h_audio_level,        'push_audio_level');
  eel.expose(_h_library_changed,    'push_library_changed');
  eel.expose(_h_status,             'push_status');
}

// --- Toast helper ---------------------------------------------------------

function Toast({ toast, onDismiss }) {
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(onDismiss, toast.durationMs || 6000);
    return () => clearTimeout(t);
  }, [toast]);
  if (!toast) return null;
  const vc = toast.variant === 'accent' ? 'is-accent'
           : toast.variant === 'warn'   ? 'is-warn' : 'is-good';
  return (
    <div className="au-toast">
      <div className={"t-ico " + vc}>{toast.icon || '✓'}</div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <span className="t-title">{toast.title}</span>
        {toast.body && <span style={{ color: 'var(--text-3)' }}>{toast.body}</span>}
      </div>
      {toast.action && (
        <span className="t-action" onClick={() => {
          if (toast.actionCmd === 'reveal' && toast.actionPath) Api.revealInFolder(toast.actionPath);
          else if (toast.actionCmd === 'open' && toast.actionPath) Api.openPath(toast.actionPath);
          onDismiss();
        }}>{toast.action}</span>
      )}
      <span className="t-dismiss" onClick={onDismiss}>×</span>
    </div>
  );
}

// --- Modal scaffolding -----------------------------------------------------

function Modal({ children, onClose }) {
  return (
    <div className="au-modal-backdrop" onClick={onClose}>
      <div className="au-modal" onClick={e => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}

function AboutModal({ data, onClose }) {
  return (
    <Modal onClose={onClose}>
      <div className="au-modal-hd">
        <div className="t">About Auralis</div>
        <span className="x" onClick={onClose}>×</span>
      </div>
      <div className="au-modal-bd">
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 18 }}>
          <div style={{
            width: 48, height: 48, borderRadius: 12,
            background: 'linear-gradient(155deg, var(--accent), var(--accent-2))',
            display: 'grid', placeItems: 'center', color: '#fff',
            fontSize: 22, fontWeight: 700,
          }}>A</div>
          <div>
            <div style={{ fontSize: 17, fontWeight: 600 }}>Auralis · v{data.version}</div>
            <div style={{ color: 'var(--text-3)', fontSize: 12.5 }}>{data.tagline}</div>
          </div>
        </div>
        <div className="au-kv">
          <div className="k">Build</div><div className="v">{data.build_date}</div>
          <div className="k">Author</div><div className="v">{data.author}</div>
          <div className="k">License</div><div className="v">{data.license}</div>
        </div>
        <div style={{ marginTop: 18, fontSize: 11.5, color: 'var(--text-3)',
                      textTransform: 'uppercase', letterSpacing: '0.08em',
                      fontWeight: 600 }}>Credits</div>
        <ul style={{ margin: '8px 0 0 0', padding: 0, listStyle: 'none',
                     display: 'flex', flexDirection: 'column', gap: 4 }}>
          {(data.credits || []).map(c => (
            <li key={c.name} style={{ fontSize: 13 }}>
              <a href={c.url} target="_blank" rel="noopener noreferrer"
                 style={{ color: 'var(--accent)' }}>{c.name}</a>
            </li>
          ))}
        </ul>
      </div>
      <div className="au-modal-ft">
        <button className="au-btn au-btn-primary" onClick={onClose}>Close</button>
      </div>
    </Modal>
  );
}

function SetupChecklistModal({ items, onClose, onOpenSettings }) {
  return (
    <Modal onClose={onClose}>
      <div className="au-modal-hd">
        <div className="t">Setup checklist</div>
        <span className="x" onClick={onClose}>×</span>
      </div>
      <div className="au-modal-bd">
        <ul style={{ margin: 0, padding: 0, listStyle: 'none',
                     display: 'flex', flexDirection: 'column', gap: 10 }}>
          {(items || []).map((it, i) => (
            <li key={i} style={{
              display: 'grid',
              gridTemplateColumns: '26px 1fr',
              alignItems: 'center',
              gap: 10,
              padding: '10px 12px',
              border: '1px solid var(--hairline)',
              borderRadius: 10,
              background: 'var(--surface)',
            }}>
              <span style={{
                width: 22, height: 22, borderRadius: '50%',
                display: 'grid', placeItems: 'center',
                background: it.ok ? 'var(--good-soft)' : 'var(--warn-soft)',
                color: it.ok ? 'var(--good)' : 'var(--warn)',
                fontWeight: 700, fontSize: 12,
              }}>{it.ok ? '✓' : '!'}</span>
              <div>
                <div style={{ fontWeight: 500, color: 'var(--text)' }}>{it.label}</div>
                {it.detail && <div style={{ fontSize: 12, color: 'var(--text-3)' }}>{it.detail}</div>}
              </div>
            </li>
          ))}
        </ul>
      </div>
      <div className="au-modal-ft">
        <button className="au-btn" onClick={() => { onClose(); onOpenSettings(); }}>Open settings</button>
        <button className="au-btn au-btn-primary" onClick={onClose}>Done</button>
      </div>
    </Modal>
  );
}

function ErrorCard({ err, onRetry, onOpenSettings }) {
  return (
    <div style={{
      maxWidth: 640, margin: '60px auto',
      padding: 24, background: 'var(--surface)',
      border: '1px solid var(--hairline)', borderRadius: 14,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 14 }}>
        <div style={{
          width: 44, height: 44, borderRadius: 12,
          background: 'var(--rec-soft)', border: '1px solid rgba(240,101,106,0.35)',
          display: 'grid', placeItems: 'center', color: 'var(--rec)',
        }}>
          <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
            <path d="M8 3v6M8 12v.1" /><circle cx="8" cy="8" r="6.5" />
          </svg>
        </div>
        <div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{err.title || "Recording error"}</div>
          <div style={{ fontSize: 12.5, color: 'var(--text-3)' }}>{err.code || ''}</div>
        </div>
      </div>
      <p style={{ color: 'var(--text-2)' }}>{err.body || err.message}</p>
      <div style={{ display: 'flex', gap: 8, marginTop: 18 }}>
        <button className="au-btn au-btn-primary" onClick={onRetry}>Try again</button>
        <button className="au-btn" onClick={onOpenSettings}>Open settings</button>
        <div style={{ flex: 1 }} />
        <button className="au-btn au-btn-ghost"
                onClick={() => Api.openPath('logs/auralis.log')}>View log</button>
      </div>
    </div>
  );
}

// --- App root -------------------------------------------------------------

// --- Mini player ----------------------------------------------------------
// A small audio element pinned to the bottom of the Library tab. It's
// rendered once at the App root so playback survives tab switches.
function MiniPlayer({ player, onClose }) {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [t, setT] = useState(0);
  const [dur, setDur] = useState(0);

  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    a.src = '/wav?path=' + encodeURIComponent(player.path);
    a.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
  }, [player.path]);

  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    const onTime = () => setT(a.currentTime);
    const onDur  = () => setDur(a.duration || 0);
    const onEnd  = () => setPlaying(false);
    a.addEventListener('timeupdate', onTime);
    a.addEventListener('loadedmetadata', onDur);
    a.addEventListener('ended', onEnd);
    return () => {
      a.removeEventListener('timeupdate', onTime);
      a.removeEventListener('loadedmetadata', onDur);
      a.removeEventListener('ended', onEnd);
    };
  }, []);

  // Spacebar play/pause when the mini player is mounted and the user isn't
  // typing.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== ' ') return;
      const tg = e.target;
      const tag = tg && tg.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (tg && tg.isContentEditable)) return;
      e.preventDefault();
      const a = audioRef.current;
      if (!a) return;
      if (a.paused) { a.play(); setPlaying(true); }
      else          { a.pause(); setPlaying(false); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const fmt = s => {
    const x = Math.max(0, Math.floor(s));
    return `${String(Math.floor(x/60)).padStart(2,'0')}:${String(x%60).padStart(2,'0')}`;
  };
  const pct = dur > 0 ? (t / dur) * 100 : 0;
  const togglePlay = () => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) { a.play(); setPlaying(true); }
    else          { a.pause(); setPlaying(false); }
  };
  const seek = (e) => {
    const a = audioRef.current;
    if (!a) return;
    const r = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - r.left;
    a.currentTime = (x / r.width) * (dur || 0);
  };

  return (
    <div style={{
      position: 'fixed', left: 50, right: 50, bottom: 14,
      background: 'var(--surface)',
      border: '1px solid var(--border)', borderRadius: 12,
      padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 12,
      boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
      zIndex: 90,
    }}>
      <audio ref={audioRef} preload="metadata" />
      <button className="au-iconbtn"
              style={{ background: 'var(--accent)', color: '#fff',
                       width: 32, height: 32, borderRadius: 8 }}
              onClick={togglePlay}>
        {playing ? '⏸' : '▶'}
      </button>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12,
                      color: 'var(--text)', overflow: 'hidden',
                      textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {player.name}
        </div>
        <div onClick={seek} style={{
          height: 6, marginTop: 6,
          background: 'var(--surface-2)', borderRadius: 999,
          overflow: 'hidden', cursor: 'pointer',
        }}>
          <div style={{ width: pct + '%', height: '100%',
                        background: 'linear-gradient(90deg, var(--accent), var(--accent-2))',
                        borderRadius: 999, transition: 'width 0.15s linear' }} />
        </div>
      </div>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11,
                     color: 'var(--text-3)', minWidth: 80, textAlign: 'right' }}>
        {fmt(t)} / {fmt(dur)}
      </span>
      <span style={{ width: 26, height: 26, display: 'grid', placeItems: 'center',
                     color: 'var(--text-3)', cursor: 'pointer', fontSize: 16 }}
            onClick={onClose}>×</span>
    </div>
  );
}

function App() {
  const [tab, setTab]       = useState('live');
  const [state, setState]   = useState(null);
  const [toast, setToast]   = useState(null);
  const [modal, setModal]   = useState(null);   // {kind:'about'|'setup', data:...}
  const [errorBlob, setErrorBlob] = useState(null);
  const [player, setPlayer] = useState(null);   // {path, name}

  // Initial state pull
  useEffect(() => {
    Api.getState().then(s => { if (s) setState(s); });
  }, []);

  // Sidebar callbacks via window so existing components don't have to thread
  // props through.
  useEffect(() => {
    window.__appOnSelect = (id) => setTab(id);
    window.__appOnQuick  = async (id) => {
      if (id === 'open-folder') {
        if (state?.app_dir) Api.openPath(state.app_dir);
      } else if (id === 'about') {
        const d = await Api.showAbout();
        if (d) setModal({ kind: 'about', data: d });
      } else if (id === 'status-click') {
        setTab('settings');
        setTimeout(() => {
          const el = document.getElementById('sec-transcription');
          if (el) el.scrollIntoView({ behavior: 'smooth' });
        }, 60);
      }
    };
    window.__appLight = (state?.config?.dark_mode === false);
  }, [state]);

  // Keyboard shortcuts — global.
  useEffect(() => {
    const onKey = (e) => {
      // Don't intercept while typing in an input/textarea.
      const tgt = e.target;
      const tag = (tgt && tgt.tagName) || '';
      const editable = (tgt && tgt.isContentEditable);
      const inField = (tag === 'INPUT' || tag === 'TEXTAREA' || editable);
      const ctrl  = e.ctrlKey || e.metaKey;

      if (e.key === 'Escape') {
        if (modal) setModal(null);
        if (errorBlob) setErrorBlob(null);
        return;
      }
      // Ctrl shortcuts work even inside inputs.
      if (ctrl && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        if (tab !== 'library') setTab('library');
        setTimeout(() => {
          const inp = document.querySelector('.au-topbar input[placeholder^="Search"]');
          if (inp) inp.focus();
        }, 80);
        return;
      }
      if (ctrl && e.key.toLowerCase() === 'n') {
        e.preventDefault();
        const name = window.prompt('New course name:');
        if (name && name.trim()) Api.newCourse(name.trim());
        return;
      }
      if (ctrl && e.key === ',') {
        e.preventDefault();
        setTab('settings');
        return;
      }
      if (inField) return;
      if (e.key === '1') { setTab('live'); return; }
      if (e.key === '2') { setTab('library'); return; }
      if (e.key === '3') { setTab('settings'); return; }
      const r = state?.recording || {};
      if (e.key.toLowerCase() === 'r' && !r.is_recording && !r.polishing) {
        const c = state?.config?.current_course;
        const k = state?.config?.current_category;
        Api.startRecording(c, k);
        return;
      }
      if (e.key.toLowerCase() === 's' && r.is_recording) {
        Api.stopRecording();
        return;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [tab, state, modal, errorBlob]);

  // Push-event subscriptions — install once on mount. The actual eel.expose
  // stubs are registered at module top level (see _push_handlers) so Python
  // sees the names at scan time.
  useEffect(() => {
    installPushHandlers({
    push_state_patch: (patch) => {
      setState(prev => prev ? { ...prev, ...patch } : patch);
    },
    push_toast: (t) => setToast(t),
    push_transcript_segment: (seg) => {
      setState(prev => {
        if (!prev) return prev;
        const segs = (prev.transcript_segments || []).concat([seg]);
        return { ...prev, transcript_segments: segs };
      });
    },
    push_trigger: (trig) => {
      setState(prev => {
        if (!prev) return prev;
        const trigs = (prev.triggers || []).concat([trig]);
        return { ...prev, triggers: trigs };
      });
    },
    push_dyn_vocab: (terms) => {
      setState(prev => prev ? { ...prev, dyn_vocab: terms } : prev);
    },
    push_recording_state: (rec) => {
      setState(prev => prev ? { ...prev, recording: rec } : prev);
    },
    push_polish_progress: (pct) => {
      setState(prev => {
        if (!prev) return prev;
        const r = { ...(prev.recording || {}), polish_progress: pct };
        return { ...prev, recording: r };
      });
    },
    push_audio_level: (lvl) => {
      // Append to rolling buffer (last 96 samples), kept on window so the
      // waveform component can read it without re-rendering the whole tree.
      const buf = window.__audioLevelBuf || [];
      buf.push(lvl);
      if (buf.length > 96) buf.shift();
      window.__audioLevelBuf = buf;
    },
    push_library_changed: () => {
      Api.getState().then(s => s && setState(s));
    },
    push_status: (msg) => {
      const el = document.getElementById('au-status-sub');
      if (el) el.textContent = msg;
    },
    });
  }, []);

  // Quick-open About / Setup helpers exposed to existing tab components.
  window.__openAbout = async () => {
    const d = await Api.showAbout();
    if (d) setModal({ kind: 'about', data: d });
  };
  window.__openSetupChecklist = async () => {
    const items = await Api.setupChecklist();
    setModal({ kind: 'setup', data: items });
  };

  if (!state) {
    return (
      <div style={{
        width: '100%', height: '100%',
        display: 'grid', placeItems: 'center',
        background: 'var(--bg)', color: 'var(--text-3)',
        fontSize: 13.5, fontFamily: 'var(--font-ui)',
      }}>
        Loading Auralis…
      </div>
    );
  }

  window.__appState = state;
  window.__appSetState = setState;
  window.__appShowToast = setToast;
  window.__appApi = Api;
  window.__appPlay = (rec) => setPlayer({ path: rec.path, name: rec.name });
  window.__appStop = () => setPlayer(null);

  let view;
  if (tab === 'live') {
    const rec = state.recording || {};
    const loading = (state.whisper_status === 'loading');
    if (rec.polishing) view = <LivePostProcessing state={state} api={Api} />;
    // While the user clicked Start but the Whisper model is still warming up,
    // stay on LiveIdle so the morphing CTA (Start → Loading → Recording) is
    // visible in the same spot. Only switch to LiveRecording once the model
    // is loaded and segments are about to flow.
    else if (rec.is_recording && !loading) view = <LiveRecording state={state} api={Api} />;
    else view = <LiveIdle state={state} api={Api} />;
  } else if (tab === 'library') {
    view = <Library state={state} api={Api} />;
  } else if (tab === 'settings') {
    view = <Settings state={state} api={Api} />;
  }

  return (
    <>
      {view}
      <Toast toast={toast} onDismiss={() => setToast(null)} />
      {modal && modal.kind === 'about' && (
        <AboutModal data={modal.data} onClose={() => setModal(null)} />
      )}
      {modal && modal.kind === 'setup' && (
        <SetupChecklistModal items={modal.data}
                             onClose={() => setModal(null)}
                             onOpenSettings={() => setTab('settings')} />
      )}
      {player && (
        <MiniPlayer player={player} onClose={() => setPlayer(null)} />
      )}
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
