/* global React, AuFrame, AuTopbar, AuToast, Ico */

// =====================================================================
// LIVE — Idle / Recording / Polishing
// =====================================================================

const { useState: useStateLive, useEffect: useEffectLive, useRef: useRefLive,
        useMemo: useMemoLive } = React;

function useConfigField(initial, onCommit) {
  const [v, setV] = useStateLive(initial);
  useEffectLive(() => { setV(initial); }, [initial]);
  return [v, setV, () => { if (v !== initial && onCommit) onCommit(v); }];
}

// Parse "a, b, c" → ["a","b","c"]. Used for vocab-prime chips.
function tokenize(text) {
  return (text || '')
    .split(/[,\n;]/)
    .map(s => s.trim())
    .filter(Boolean);
}

// =====================================================================
// Live tab — Idle state
// =====================================================================
function LiveIdle({ state, api }) {
  const cfg = state.config || {};
  const courses = state.courses || cfg.courses || [];
  const categories = state.categories || ['Lectures', 'Exercises'];

  const [course, setCourse]     = useStateLive(cfg.current_course || courses[0] || '');
  const [category, setCategory] = useStateLive(cfg.current_category || categories[0]);
  const [prime, setPrime, commitPrime] = useConfigField(
    cfg.initial_prompt || '', v => api.saveConfig({ initial_prompt: v }));
  const [prompt, setPrompt, commitPrompt] = useConfigField(
    cfg.meeting_prompt || '', v => api.saveConfig({ meeting_prompt: v }));
  const [showCourseMenu, setShowCourseMenu] = useStateLive(false);

  useEffectLive(() => {
    if (course && course !== cfg.current_course) api.saveConfig({ current_course: course });
  }, [course]);
  useEffectLive(() => {
    if (category && category !== cfg.current_category) api.saveConfig({ current_category: category });
  }, [category]);

  const safe = s => (s || '').trim().replace(/\s+/g, '_');
  const savePath = `recordings/${safe(course)}/${safe(category)}/`;

  const onStart = async () => {
    // Optimistic UI: flip the recording state locally the instant the user
    // clicks, so the button visibly changes to red/square/Recording without
    // waiting for the backend → push round-trip. If the backend ultimately
    // rejects (missing dependency, already recording, etc.), revert.
    if (window.__appSetState) {
      window.__appSetState(prev => prev ? {
        ...prev,
        recording: { ...(prev.recording || {}),
                     is_recording: true,
                     elapsed_seconds: 0,
                     recording_start_ts: Date.now() / 1000 },
        transcript_segments: [],
        triggers: [],
      } : prev);
    }
    const r = await api.startRecording(course, category);
    if (r && r.ok === false) {
      // Revert the optimistic flip.
      if (window.__appSetState) {
        window.__appSetState(prev => prev ? {
          ...prev,
          recording: { ...(prev.recording || {}), is_recording: false }
        } : prev);
      }
      window.__appShowToast && window.__appShowToast({
        title: 'Cannot start', body: r.error || 'Unknown error',
        icon: '!', variant: 'warn', durationMs: 6000,
      });
    }
  };
  const onNewCourse = async () => {
    const name = window.prompt('New course name:');
    if (name && name.trim()) {
      const r = await api.newCourse(name.trim());
      if (r && r.ok) setCourse(name.trim());
    }
  };
  const onForceVocab = () => api.forceVocabRefresh();

  // Whisper status pill — three states.
  const whisperState = state.whisper_status || 'ready';
  const whisperPill = whisperState === 'loading'
    ? { variant: 'warn',   text: 'Whisper loading…' }
    : whisperState === 'error'
    ? { variant: 'rec',    text: 'Whisper error' }
    : { variant: 'good',   text: 'Whisper ready · ' + ((cfg.whisper_model_label || '').split(' ')[0] || 'model') };

  // Capturing pill — clickable → Settings → Audio source.
  const sourceLabel = cfg.audio_capture_mode === 'app'
    ? `Capturing ${cfg.output_app_name || '(no app picked)'}`
    : cfg.audio_capture_mode === 'device'
    ? `Capturing ${cfg.output_device_name || 'output device'}`
    : 'Whole system audio';

  // Vocab-prime chips: parsed from the textarea. × removes a term.
  const vocabChips = tokenize(prime);
  const removeChip = (term) => {
    const next = vocabChips.filter(t => t !== term).join(', ');
    setPrime(next);
    api.saveConfig({ initial_prompt: next });
  };

  return (
    <AuFrame tab="live">
      <AuTopbar
        title="Live"
        sub="Capture a lecture in real time."
        actions={
          <>
            <button className="au-tb-btn" onClick={() => api.resetSession()}>
              <span className="sw"><Ico.refresh /></span>Reset session
            </button>
            <button className="au-tb-btn is-ghost"
                    onClick={() => window.__openSetupChecklist && window.__openSetupChecklist()}>
              <span className="sw"><Ico.info /></span>Setup checklist
            </button>
          </>
        }
      />

      <div className="au-page" style={{ maxWidth: 1040, margin: '0 auto', width: '100%' }}>

        {/* Hero */}
        <section className="au-card" style={{ padding: 22, display: 'grid', gridTemplateColumns: '1fr auto', gap: 22, alignItems: 'center' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span className={"au-pill is-" + whisperPill.variant}>
                <span className="dot" />{whisperPill.text}
              </span>
              <span className="au-pill" style={{ cursor: 'pointer' }}
                    onClick={() => window.__appOnSelect('settings')}>
                <span className="dot" />{sourceLabel}
              </span>
            </div>
            <h2 style={{ margin: '4px 0 6px', fontSize: 22, fontWeight: 600, letterSpacing: '-0.01em' }}>
              Ready when you are.
            </h2>
            <p style={{ margin: 0, color: 'var(--text-3)', fontSize: 13.5, maxWidth: 460 }}>
              Pick a destination below, then press <kbd style={kbd}>R</kbd> or click <b style={{ color: 'var(--text-2)' }}>Start recording</b>. Auralis writes a live transcript and runs a higher-quality pass when you stop.
            </p>
          </div>

          {/* Morphing primary CTA. Three states:
                 idle      → indigo "Start recording"   (clicks startRecording)
                 loading   → yellow "Loading model…"    (disabled, model load)
                 recording → green  "● Recording"       (clicks stopRecording)
              The "recording" state is reachable only while the LiveIdle view
              is still up (whisper_status === 'ready' switches the routing to
              LiveRecording, which has its own red Stop & process button). */}
          <RecordButton state={state} api={api} onStart={onStart} />
        </section>

        {/* Course + category */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 14, marginTop: 22 }}>
          <div>
            <label className="au-label">Course</label>
            <select className="au-select" value={course} onChange={e => setCourse(e.target.value)}>
              {courses.map(c => (
                <option key={c} value={c} dir={/[֐-׿]/.test(c) ? 'rtl' : 'ltr'}>{c}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="au-label">Category</label>
            <select className="au-select" value={category} onChange={e => setCategory(e.target.value)}>
              {categories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, position: 'relative' }}>
            <button className="au-btn sm" onClick={onNewCourse}>
              <span className="ico"><Ico.plus /></span>New course
            </button>
            <button className="au-iconbtn ghost-border" title="Manage courses"
                    onClick={() => setShowCourseMenu(v => !v)}>
              <Ico.more />
            </button>
            {showCourseMenu && (
              <div className="au-menu" style={{ top: 38, right: 0 }}
                   onMouseLeave={() => setShowCourseMenu(false)}>
                <div className="au-menu-item" onClick={() => {
                  setShowCourseMenu(false);
                  const newName = window.prompt('Rename course "' + course + '" to:', course);
                  if (newName && newName.trim() && newName.trim() !== course) {
                    // Rename = create new + we'd need a backend op for safety;
                    // for now treat as informational.
                    window.__appShowToast && window.__appShowToast({
                      title: 'Rename via Library', body: 'Use Library kebab → Rename (per recording) for now.',
                      icon: '!', variant: 'warn', durationMs: 6000,
                    });
                  }
                }}>Rename…</div>
                <div className="au-menu-item" onClick={() => {
                  setShowCourseMenu(false);
                  api.openPath(state.app_dir + '/recordings/' + course);
                }}>Reveal in Explorer</div>
                <div className="au-menu-sep" />
                <div className="au-menu-item is-danger" onClick={async () => {
                  setShowCourseMenu(false);
                  if (!window.confirm('Delete course "' + course + '" from the dropdown? (Recordings on disk are NOT removed.)')) return;
                  const remaining = (cfg.courses || []).filter(c => c !== course);
                  await api.saveConfig({ courses: remaining,
                                         current_course: remaining[0] || '' });
                  setCourse(remaining[0] || '');
                }}>Remove from list</div>
              </div>
            )}
          </div>
        </div>

        <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-4)', display: 'flex', alignItems: 'center', gap: 6 }}>
          <Ico.folder />
          Will save to <span style={{ color: 'var(--text-2)', fontFamily: 'var(--font-mono)', fontSize: 11.5 }}>{savePath}</span>
        </div>

        <div className="au-divider" />

        {/* Prompts & vocabulary */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <h3 className="au-h2" style={{ margin: 0 }}>Prompts & vocabulary</h3>
          <span style={{ fontSize: 12, color: 'var(--text-4)' }}>— bias Whisper toward your domain. Optional.</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <label className="au-label">Vocabulary prime</label>
            <textarea className="au-textarea" dir="rtl"
                      value={prime}
                      onChange={e => setPrime(e.target.value)}
                      onBlur={commitPrime}
                      style={{ minHeight: 84 }} />
            {vocabChips.length > 0 && (
              <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {vocabChips.slice(0, 8).map(t => (
                  <span key={t} className="au-chip"
                        dir={/[֐-׿]/.test(t) ? 'rtl' : 'ltr'}>
                    {t}
                    <span className="x" onClick={() => removeChip(t)}><Ico.x /></span>
                  </span>
                ))}
                {vocabChips.length > 8 && (
                  <span style={{ fontSize: 11.5, color: 'var(--text-4)', alignSelf: 'center' }}>
                    +{vocabChips.length - 8} more
                  </span>
                )}
              </div>
            )}
          </div>

          <div>
            <label className="au-label">When a trigger word fires, ask Claude</label>
            <textarea className="au-textarea"
                      value={prompt}
                      onChange={e => setPrompt(e.target.value)}
                      onBlur={commitPrompt}
                      style={{ minHeight: 84 }} />
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-3)' }}>
              <Ico.info /> Triggers copy to clipboard automatically — paste into any chat.
            </div>
          </div>
        </div>

        <div className="au-divider" />

        {/* Dynamic vocab preview */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <h3 className="au-h2" style={{ margin: 0 }}>Dynamic vocabulary</h3>
          <span style={{ fontSize: 12, color: 'var(--text-4)' }}>
            — builds itself from recurring words every {cfg.dynamic_vocab_interval_minutes || 10} minutes.
          </span>
          <div style={{ flex: 1 }} />
          <button className="au-tb-btn" onClick={onForceVocab}>
            <span className="sw"><Ico.refresh /></span>Refresh now
          </button>
        </div>

        {(state.dyn_vocab && state.dyn_vocab.length > 0) ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {state.dyn_vocab.map(w => (
              <span key={w} className="au-chip" dir={/[֐-׿]/.test(w) ? 'rtl' : 'ltr'}>{w}</span>
            ))}
          </div>
        ) : (
          <div className="au-hint">
            <span className="hint-ico"><Ico.spark /></span>
            <div>
              <div style={{ color: 'var(--text-2)', marginBottom: 2 }}>Nothing learned yet.</div>
              <div style={{ color: 'var(--text-3)' }}>After a few minutes of speech, Auralis picks the top recurring words and feeds them back to Whisper to lock in accuracy.</div>
            </div>
          </div>
        )}

      </div>
    </AuFrame>
  );
}
const kbd = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  minWidth: 18, height: 18, padding: '0 5px',
  border: '1px solid var(--border)', borderRadius: 4,
  fontSize: 10.5, color: 'var(--text-2)', fontFamily: 'var(--font-mono)',
  background: 'var(--surface)', verticalAlign: 'middle',
};

// =====================================================================
// Live tab — Recording state
// =====================================================================
function LiveRecording({ state, api }) {
  const rec = state.recording || {};
  const segs = state.transcript_segments || [];
  const trigs = state.triggers || [];
  const cfg = state.config || {};

  // Sticky-bottom scroll — only auto-scroll if the user is already pinned to
  // the bottom. If they've scrolled up, leave them alone.
  const transRef = useRefLive(null);
  const stuckRef = useRefLive(true);
  useEffectLive(() => {
    const el = transRef.current;
    if (!el) return;
    const onScroll = () => {
      const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
      stuckRef.current = gap < 40;
    };
    el.addEventListener('scroll', onScroll);
    return () => el.removeEventListener('scroll', onScroll);
  }, []);
  useEffectLive(() => {
    if (stuckRef.current && transRef.current) {
      transRef.current.scrollTop = transRef.current.scrollHeight;
    }
  }, [segs.length]);

  // Live waveform — render the rolling buffer of audio levels.
  const [waveTick, setWaveTick] = useStateLive(0);
  useEffectLive(() => {
    const id = setInterval(() => setWaveTick(t => t + 1), 80);
    return () => clearInterval(id);
  }, []);
  const buf = window.__audioLevelBuf || [];
  const bars = useMemoLive(() => {
    if (buf.length === 0) {
      return Array.from({ length: 88 }, () => 0.05);
    }
    // Map the rolling buffer to 88 fixed-width bars by sampling.
    const N = 88;
    const out = new Array(N);
    for (let i = 0; i < N; i++) {
      const idx = Math.floor((i / N) * buf.length);
      const v = Math.min(1, (buf[idx] || 0) * 8); // 8× gain
      out[i] = 0.05 + 0.95 * v;
    }
    return out;
  }, [waveTick, buf.length]);

  const fmtTime = secs => {
    const s = Math.max(0, Math.floor(secs || 0));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return (h > 0 ? `${String(h).padStart(2,'0')}:` : '00:') + `${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
  };
  const elapsed = fmtTime(rec.elapsed_seconds);

  const wordCount = useMemoLive(
    () => segs.reduce((sum, s) => sum + ((s.text || '').match(/\S+/g) || []).length, 0),
    [segs.length]
  );

  const [langCycle, setLangCycle] = useStateLive(cfg.language || 'auto');
  useEffectLive(() => { setLangCycle(cfg.language || 'auto'); }, [cfg.language]);
  const cycleLang = () => {
    const order = ['auto', 'he', 'en'];
    const i = order.indexOf(langCycle);
    const next = order[(i + 1) % order.length];
    setLangCycle(next);
    api.saveConfig({ language: next });
  };

  const onStop = async () => {
    // Optimistic flip so the page swaps immediately — to LivePostProcessing
    // if polish is on, else back to LiveIdle. Backend confirms.
    if (window.__appSetState) {
      window.__appSetState(prev => prev ? {
        ...prev,
        recording: { ...(prev.recording || {}),
                     is_recording: false,
                     polishing: !!(prev.config && prev.config.postprocess_enabled) }
      } : prev);
    }
    await api.stopRecording();
  };

  // Countdown to next dyn-vocab refresh.
  const intervalMin = cfg.dynamic_vocab_interval_minutes || 10;
  const elapsedSec = rec.elapsed_seconds || 0;
  const cycleSec = intervalMin * 60;
  const sinceLast = elapsedSec % cycleSec;
  const remaining = Math.max(0, cycleSec - sinceLast);
  const remMin = Math.floor(remaining / 60), remSec = remaining % 60;

  return (
    <AuFrame tab="live" recording>
      <AuTopbar
        title="Live"
        sub={<>Recording into <span style={{ color: 'var(--text-2)' }} className="bidi">{(cfg.current_course || '')} / {(cfg.current_category || '')}</span></>}
        actions={
          <>
            <button className="au-tb-btn" onClick={() => api.recopyLastTrigger()}>
              <span className="sw"><Ico.copy /></span>Re-copy last trigger
            </button>
            <button className="au-tb-btn" onClick={() => api.saveTranscriptNow()}>
              <span className="sw"><Ico.save /></span>Save now
            </button>
          </>
        }
      />

      <div className="au-page" style={{ padding: 0, display: 'grid', gridTemplateRows: 'auto 1fr', minHeight: 0 }}>

        <section style={{
          padding: '20px 32px',
          background: 'linear-gradient(180deg, var(--bg-soft), transparent)',
          borderBottom: '1px solid var(--hairline)',
          display: 'grid', gridTemplateColumns: 'auto 1fr auto',
          alignItems: 'center', gap: 22,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              width: 44, height: 44, borderRadius: 12,
              background: 'var(--rec-soft)', border: '1px solid rgba(240,101,106,0.35)',
              display: 'grid', placeItems: 'center', color: 'var(--rec)',
            }}>
              <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="8" r="5" /></svg>
            </div>
            <div>
              <div style={{ fontSize: 11.5, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600 }}>Recording</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 26, fontWeight: 500, letterSpacing: '0.02em' }}>
                {elapsed}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 2, height: 44, padding: '0 4px' }}>
            {bars.map((b, i) => (
              <div key={i} style={{
                flex: '1 1 0', height: `${Math.max(2, b * 100)}%`, minHeight: 2,
                background: 'var(--accent)', borderRadius: 1, opacity: 0.85,
                transition: 'height 0.08s linear',
              }} />
            ))}
          </div>

          {/* Match the morphing CTA story from LiveIdle: while actively
              recording, the button is green and reads "Recording — click to
              stop". Clicking calls Stop & process (which then transitions
              to the polishing view). */}
          <button className="au-btn"
                  style={{ height: 44, padding: '0 18px', fontSize: 13.5,
                           borderRadius: 10, background: 'var(--good)',
                           color: '#fff', border: 'none',
                           boxShadow: '0 1px 0 rgba(255,255,255,0.16) inset, 0 1px 2px rgba(0,0,0,0.25)' }}
                  onClick={onStop}>
            <span className="au-rec-pulse"
                  style={{ width: 8, height: 8, background: '#fff',
                           borderRadius: '50%', display: 'inline-block',
                           marginRight: 8,
                           boxShadow: '0 0 0 4px rgba(255,255,255,0.18)' }} />
            Recording — click to stop
          </button>
        </section>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 0, minHeight: 0 }}>

          <section ref={transRef}
                   style={{ padding: '20px 32px', borderRight: '1px solid var(--hairline)', overflow: 'auto', minHeight: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <h3 className="au-h2" style={{ margin: 0 }}>Live transcript</h3>
              <span className="au-pill is-accent" style={{ cursor: 'pointer' }}
                    onClick={cycleLang}
                    title="Click to cycle auto / he / en">
                <span className="dot" />{langCycle}
              </span>
              <div style={{ flex: 1 }} />
              <span style={{ fontSize: 11.5, color: 'var(--text-4)' }}>
                {wordCount} word{wordCount === 1 ? '' : 's'} · {segs.length} segment{segs.length === 1 ? '' : 's'}
              </span>
            </div>

            <div className="au-mono" style={{ fontSize: 14, lineHeight: 1.85, color: 'var(--text-2)' }}>
              {segs.length === 0 && (
                <p style={{ color: 'var(--text-4)' }}>Listening… first segment will appear in ~30s.</p>
              )}
              {segs.map((s, i) => {
                const rtl = /[֐-׿]/.test(s.text || '');
                const isLast = i === segs.length - 1;
                return (
                  <p key={i} className={rtl ? 'rtl' : ''} style={{ marginTop: i === 0 ? 0 : '0.6em' }}>
                    <span style={ts}>{s.ts_human || fmtTime(s.timestamp)}</span>
                    {s.text}
                    {isLast && (
                      <span className="au-blink" style={{
                        display: 'inline-block', width: 8, height: 16,
                        background: 'var(--accent)', verticalAlign: 'middle',
                        marginInlineStart: 6,
                      }} />
                    )}
                  </p>
                );
              })}
            </div>
          </section>

          <aside style={{ padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 18, overflow: 'auto', minHeight: 0 }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <h3 className="au-h2" style={{ margin: 0 }}>Trigger handoffs</h3>
                <span className="au-pill" style={{ height: 18, fontSize: 10.5 }}>
                  {trigs.length} this session
                </span>
              </div>

              {trigs.length === 0 ? (
                <p style={{ fontSize: 12.5, color: 'var(--text-3)', margin: '8px 2px' }}>
                  Say one of your keywords and the recent context lands on your clipboard.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {trigs.slice().reverse().map((t, i) => (
                    <TriggerCard key={i} trig={t} api={api} />
                  ))}
                </div>
              )}
            </div>

            <div>
              <h3 className="au-h2" style={{ margin: '0 0 10px' }}>Dynamic vocabulary</h3>
              {(state.dyn_vocab && state.dyn_vocab.length > 0) ? (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                  {state.dyn_vocab.map(w => (
                    <span key={w} className="au-chip" dir={/[֐-׿]/.test(w) ? 'rtl' : 'ltr'}
                          style={{ height: 22, fontSize: 11.5 }}>{w}</span>
                  ))}
                </div>
              ) : (
                <p style={{ fontSize: 11.5, color: 'var(--text-4)' }}>
                  Building — pop in after a few minutes of speech.
                </p>
              )}
              <div style={{ marginTop: 10, fontSize: 11.5, color: 'var(--text-4)' }}>
                Next refresh in {remMin}:{String(remSec).padStart(2,'0')} · {(state.dyn_vocab || []).length} terms tracked
              </div>
            </div>
          </aside>
        </div>
      </div>
    </AuFrame>
  );
}

const ts = {
  display: 'inline-block', fontFamily: 'var(--font-mono)',
  fontSize: 11.5, color: 'var(--text-4)',
  marginInlineEnd: 12, letterSpacing: '0.02em',
  fontWeight: 500, unicodeBidi: 'plaintext',
};

function TriggerCard({ trig, api }) {
  const word = trig.trigger || '';
  const rtl = /[֐-׿]/.test(word);
  return (
    <div style={{
      border: '1px solid var(--hairline)', borderRadius: 10,
      padding: 12, background: 'var(--surface)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span className="au-pill is-accent" style={{ height: 20 }}>
          <Ico.bolt /><span dir={rtl ? 'rtl' : 'ltr'}>{word}</span>
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-4)' }}>
          {trig.ts_human || ''}
        </span>
        <div style={{ flex: 1 }} />
        <span className="au-pill is-good" style={{ height: 18, fontSize: 10.5 }}>
          <Ico.check />Copied
        </span>
      </div>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--text-3)', lineHeight: 1.5 }} className="bidi">
        …{trig.preview || ''}
      </p>
      <div style={{ display: 'flex', gap: 4, marginTop: 8 }}>
        <button className="au-btn sm au-btn-ghost"
                style={{ height: 24, padding: '0 8px', fontSize: 11.5 }}
                onClick={() => api.recopyLastTrigger()}>
          <Ico.copy /> Re-copy
        </button>
        {trig.path && (
          <button className="au-btn sm au-btn-ghost"
                  style={{ height: 24, padding: '0 8px', fontSize: 11.5 }}
                  onClick={() => api.openPath(trig.path)}>
            <Ico.external /> Open file
          </button>
        )}
      </div>
    </div>
  );
}

// =====================================================================
// Live tab — Post-processing state
// =====================================================================
function LivePostProcessing({ state, api }) {
  const cfg = state.config || {};
  const segs = state.transcript_segments || [];
  const rec = state.recording || {};
  const pct = Math.max(0, Math.min(100, rec.polish_progress || 0));

  const [polishedPath, setPolishedPath] = useStateLive(null);
  // The library blob holds the polished path once it's written.
  useEffectLive(() => {
    if (!rec.polish_path) return;
    const m = String(rec.polish_path).match(/(\d{8}_\d{6})/);
    if (!m) return;
    const ts = m[1];
    const lib = state.library || [];
    for (const c of lib) {
      for (const cat of Object.keys(c.categories || {})) {
        for (const r of c.categories[cat]) {
          if (r.path === rec.polish_path && r.post_path) {
            setPolishedPath(r.post_path);
            return;
          }
        }
      }
    }
  }, [rec.polish_path, state.library]);

  const liveTranscriptPath = useMemoLive(() => {
    if (!rec.polish_path) return null;
    const lib = state.library || [];
    for (const c of lib) {
      for (const cat of Object.keys(c.categories || {})) {
        for (const r of c.categories[cat]) {
          if (r.path === rec.polish_path && r.live_path) return r.live_path;
        }
      }
    }
    return null;
  }, [rec.polish_path, state.library]);

  const fmtTime = s => {
    const x = Math.max(0, Math.floor(s));
    return `${String(Math.floor(x/60)).padStart(2,'0')}:${String(x%60).padStart(2,'0')}`;
  };
  const totalEstimateS = useMemoLive(() => {
    if (!rec.polish_path) return 0;
    const lib = state.library || [];
    for (const c of lib) {
      for (const cat of Object.keys(c.categories || {})) {
        for (const r of c.categories[cat]) {
          if (r.path === rec.polish_path) return r.duration_seconds || 0;
        }
      }
    }
    return 0;
  }, [rec.polish_path]);
  const elapsedEstimateS = Math.floor(totalEstimateS * (pct / 100));

  return (
    <AuFrame tab="live">
      <AuTopbar
        title="Live"
        sub="Polishing the recording for best quality."
        actions={
          <button className="au-tb-btn" onClick={() => api.cancelPolish()}>
            <span className="sw"><Ico.x /></span>Cancel polish
          </button>
        }
      />

      <div className="au-page" style={{ padding: 0, display: 'grid', gridTemplateRows: 'auto 1fr', minHeight: 0 }}>

        <section style={{ padding: '22px 32px', borderBottom: '1px solid var(--hairline)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 14 }}>
            <div style={{
              width: 44, height: 44, borderRadius: 12,
              background: 'var(--accent-soft)', border: '1px solid var(--accent-rim)',
              display: 'grid', placeItems: 'center', color: 'var(--accent)',
            }}>
              <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M8 1.5 9.4 5.2 13.5 6 9.4 6.8 8 10.5 6.6 6.8 2.5 6 6.6 5.2 8 1.5Z" />
                <path d="M13 11l.5 1.5L15 13l-1.5.5L13 15l-.5-1.5L11 13l1.5-.5z" />
              </svg>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Post-processing the recording</div>
              <div style={{ fontSize: 12.5, color: 'var(--text-3)' }}>
                Running the high-accuracy pass. Safe to keep using Auralis.
              </div>
            </div>
            <span className="au-pill is-good" style={{ height: 22 }}><Ico.check />Live transcript saved</span>
          </div>

          <div style={{ height: 6, background: 'var(--surface-2)', borderRadius: 999, overflow: 'hidden' }}>
            <div style={{
              width: `${pct}%`, height: '100%',
              background: 'linear-gradient(90deg, var(--accent), var(--accent-2))',
              borderRadius: 999, transition: 'width 0.4s ease',
            }} />
          </div>
          <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between',
                        fontSize: 11.5, color: 'var(--text-4)' }}>
            <span>{fmtTime(elapsedEstimateS)} / {fmtTime(totalEstimateS)} · {pct}%</span>
            <span>It's safe to keep using Auralis — this runs in the background.</span>
          </div>
        </section>

        <section style={{ padding: '18px 32px', overflow: 'auto', minHeight: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <h3 className="au-h2" style={{ margin: 0 }}>Live transcript (preview)</h3>
            <div style={{ flex: 1 }} />
            <button className="au-tb-btn"
                    disabled={!liveTranscriptPath}
                    onClick={() => liveTranscriptPath && api.openPath(liveTranscriptPath)}
                    style={!liveTranscriptPath ? { opacity: 0.5 } : {}}>
              <span className="sw"><Ico.external /></span>Open live transcript
            </button>
            <button className="au-tb-btn is-ghost"
                    disabled={!polishedPath}
                    onClick={() => polishedPath && api.openPath(polishedPath)}
                    style={!polishedPath ? { opacity: 0.5 } : {}}>
              <span className="sw"><Ico.download /></span>
              {polishedPath ? 'Open polished' : 'Polished version coming'}
            </button>
          </div>
          <div className="au-mono" style={{ fontSize: 13.5, lineHeight: 1.8, color: 'var(--text-3)', maxWidth: 880 }}>
            {segs.length === 0 ? (
              <p style={{ color: 'var(--text-4)' }}>(Live transcript will be saved alongside the polished version when polishing completes.)</p>
            ) : (
              segs.slice(-12).map((s, i) => (
                <p key={i} className={/[֐-׿]/.test(s.text||'') ? 'rtl' : ''} style={{ marginTop: i === 0 ? 0 : '0.4em' }}>
                  <span style={ts}>{s.ts_human || ''}</span>{s.text}
                </p>
              ))
            )}
          </div>
        </section>
      </div>
    </AuFrame>
  );
}

// =====================================================================
// Morphing record CTA — used by LiveIdle. The three visual states map to
// (is_recording, whisper_status):
//   (false, *)              → indigo  "● Start recording"
//   (true,  'loading')       → yellow  "⏳ Loading model…" (disabled)
//   (true,  'ready')         → green   "● Recording"        (click = stop)
// The 'recording' state is rendered briefly here before routing flips to
// LiveRecording (where the full waveform / transcript / red Stop & process
// CTA live). It also persists when the user has Live tab open and the model
// is mid-load.
// =====================================================================
function RecordButton({ state, api, onStart }) {
  const rec = state.recording || {};
  const whisperState = state.whisper_status || 'ready';
  const isRecording = !!rec.is_recording;
  const isLoading = isRecording && whisperState === 'loading';
  const isLive    = isRecording && whisperState !== 'loading';

  let label, bg, dotColor, dotPulse, disabled, onClick;
  if (isLoading) {
    label    = 'Loading model…';
    bg       = 'var(--warn)';
    dotColor = '#fff';
    dotPulse = true;
    disabled = true;
    onClick  = null;
  } else if (isLive) {
    label    = 'Recording — click to stop';
    bg       = 'var(--good)';
    dotColor = '#fff';
    dotPulse = true;
    disabled = false;
    onClick  = () => api.stopRecording();
  } else {
    label    = 'Start recording';
    bg       = 'var(--accent)';
    dotColor = '#fff';
    dotPulse = false;
    disabled = false;
    onClick  = onStart;
  }

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="au-btn"
      style={{
        height: 56, padding: '0 26px',
        fontSize: 15, borderRadius: 12, gap: 10,
        background: bg, color: '#fff',
        border: 'none',
        cursor: disabled ? 'wait' : 'pointer',
        opacity: disabled ? 0.92 : 1,
        boxShadow: '0 1px 0 rgba(255,255,255,0.16) inset, 0 1px 2px rgba(0,0,0,0.25)',
        transition: 'background 0.2s ease',
      }}
    >
      <span
        className={dotPulse ? 'au-rec-pulse' : ''}
        style={{
          width: 10, height: 10, background: dotColor, borderRadius: '50%',
          boxShadow: '0 0 0 4px rgba(255,255,255,0.18)',
        }}
      />
      {label}
    </button>
  );
}

Object.assign(window, { LiveIdle, LiveRecording, LivePostProcessing, RecordButton });
