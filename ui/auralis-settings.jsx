/* global React, AuFrame, AuTopbar, Ico */

const { useState: useStateSet, useEffect: useEffectSet,
        useMemo: useMemoSet, useRef: useRefSet } = React;

// =====================================================================
// Hoisted helper components — these MUST live at module scope, not inside
// Settings(). Defining them inside the parent re-creates a new function
// identity on every parent render, which makes React unmount/remount them
// on every state change. That kills text-input focus, scroll position,
// and the auto-scroll the section nav relies on.
// =====================================================================

function Sec({ id, title, desc, children }) {
  return (
    <section style={{ marginBottom: 28 }} id={'sec-' + id} data-section={id}>
      <h2 style={{ margin: '0 0 4px', fontSize: 15, fontWeight: 600, letterSpacing: '-0.005em' }}>{title}</h2>
      {desc && <p style={{ margin: '0 0 16px', fontSize: 12.5, color: 'var(--text-3)' }}>{desc}</p>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>{children}</div>
    </section>
  );
}

function SettingRow({ label, desc, children, inline }) {
  if (inline) {
    return (
      <div>
        <div style={{ fontSize: 12.5, color: 'var(--text-2)', fontWeight: 500, marginBottom: 6 }}>{label}</div>
        {children}
        {desc && <div style={{ fontSize: 11.5, color: 'var(--text-4)', marginTop: 6 }}>{desc}</div>}
      </div>
    );
  }
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '220px 1fr',
      gap: 22, alignItems: 'flex-start',
      paddingBottom: 14, borderBottom: '1px dashed var(--hairline)',
    }}>
      <div>
        <div style={{ fontSize: 13, color: 'var(--text)', fontWeight: 500 }}>{label}</div>
        {desc && <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 3, lineHeight: 1.45 }}>{desc}</div>}
      </div>
      <div>{children}</div>
    </div>
  );
}

function SettingToggle({ label, desc, on, onChange }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 14,
      padding: '10px 14px',
      background: 'var(--surface)', border: '1px solid var(--hairline)',
      borderRadius: 10,
    }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, color: 'var(--text)', fontWeight: 500 }}>{label}</div>
        {desc && <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{desc}</div>}
      </div>
      <div className={"au-switch" + (on ? " is-on" : "")} onClick={() => onChange(!on)} style={{ cursor: 'pointer' }} />
    </div>
  );
}

// =====================================================================
// SETTINGS
// =====================================================================
function Settings({ state, api }) {
  const cfg = state.config || {};
  const modelLabels = state.model_labels || [];
  const devices = state.devices || [];
  const audioApps = state.audio_apps || [];

  // Ref to the inner scroll container so the section nav can scroll it
  // directly. Avoids issues with scrollIntoView in nested scroll regions.
  const scrollContainerRef = useRefSet(null);
  const scrollToSection = (sectionId) => {
    const cont = scrollContainerRef.current;
    if (!cont) return;
    const el = cont.querySelector('[data-section="' + sectionId + '"]');
    if (!el) return;
    const target = el.offsetTop - 8;
    cont.scrollTo({ top: target, behavior: 'smooth' });
  };

  // Local buffers — snappy text, commit on blur.
  const [triggers, setTriggers] = useStateSet((cfg.triggers || []).join(', '));
  const [cooldown, setCooldown] = useStateSet(cfg.cooldown_seconds || 30);
  const [autostop, setAutostop] = useStateSet(cfg.auto_stop_silence_minutes || 0);
  const [silthr, setSilthr]     = useStateSet(cfg.silence_rms_threshold || 0.005);
  const [dvInt, setDvInt]       = useStateSet(cfg.dynamic_vocab_interval_minutes || 10);
  const [dvHist, setDvHist]     = useStateSet(cfg.dynamic_vocab_history_minutes || 20);
  const [dvTopN, setDvTopN]     = useStateSet(cfg.dynamic_vocab_top_n || 30);
  const [modelStatus, setModelStatus] = useStateSet(null);
  const [sessionsCount, setSessionsCount] = useStateSet(0);
  const [activeSec, setActiveSec] = useStateSet('audio');

  useEffectSet(() => setTriggers((cfg.triggers || []).join(', ')), [(cfg.triggers || []).join('|')]);
  useEffectSet(() => setCooldown(cfg.cooldown_seconds || 30),      [cfg.cooldown_seconds]);
  useEffectSet(() => setAutostop(cfg.auto_stop_silence_minutes || 0), [cfg.auto_stop_silence_minutes]);
  useEffectSet(() => setSilthr(cfg.silence_rms_threshold || 0.005), [cfg.silence_rms_threshold]);
  useEffectSet(() => setDvInt(cfg.dynamic_vocab_interval_minutes || 10), [cfg.dynamic_vocab_interval_minutes]);
  useEffectSet(() => setDvHist(cfg.dynamic_vocab_history_minutes || 20), [cfg.dynamic_vocab_history_minutes]);
  useEffectSet(() => setDvTopN(cfg.dynamic_vocab_top_n || 30),    [cfg.dynamic_vocab_top_n]);

  // Refresh the "Downloaded · 1.5 GB" pill whenever the model picker changes.
  useEffectSet(() => {
    api.getModelStatus(cfg.whisper_model_label).then(setModelStatus);
  }, [cfg.whisper_model_label]);

  // Refresh audio-emitting apps every ~3 seconds while the user is on
  // Audio source. Keeps the "N sessions live" pill honest.
  useEffectSet(() => {
    if (activeSec !== 'audio') return;
    const tick = async () => {
      await api.refreshApps();
      const c = await api.audioSessionsCount();
      setSessionsCount(c || 0);
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => clearInterval(id);
  }, [activeSec]);

  // Auto-save indicator — "last edited N min/sec ago".
  const [, force] = useStateSet(0);
  useEffectSet(() => {
    const id = setInterval(() => force(x => x + 1), 15000);
    return () => clearInterval(id);
  }, []);
  const lastSavedAgo = useMemoSet(() => {
    const t = state.config_last_saved_ts;
    if (!t) return null;
    const sec = Math.max(0, Math.floor(Date.now() / 1000 - t));
    if (sec < 5) return 'just now';
    if (sec < 60) return sec + 's ago';
    const m = Math.floor(sec / 60);
    if (m < 60) return m + ' min ago';
    const h = Math.floor(m / 60);
    return h + ' hr ago';
  }, [state.config_last_saved_ts, state]);

  const save = partial => api.saveConfig(partial);
  const onModelChange = label => api.applyModel(label);
  const onRestoreDefaults = async () => {
    if (!window.confirm('Reset all settings to defaults?\n\nYour recordings and transcripts on disk are NOT touched.')) return;
    await api.restoreDefaults();
  };

  const removeTrigger = t => {
    const next = (cfg.triggers || []).filter(x => x !== t);
    save({ triggers: next });
  };
  const addTrigger = () => {
    const v = window.prompt('Add trigger keyword:');
    if (v && v.trim()) save({ triggers: [...(cfg.triggers || []), v.trim()] });
  };

  // Aliases — Sec / Row / Toggle are now module-level (above) so they don't
  // remount on every parent render. Keep short local names so the JSX below
  // doesn't have to change.
  const Row = SettingRow;
  const Toggle = SettingToggle;
  const captureMode = cfg.audio_capture_mode || 'system';

  return (
    <AuFrame tab="settings">
      <AuTopbar
        title="Settings"
        sub="Preferences are saved automatically to config.json."
        actions={
          <>
            <button className="au-tb-btn" onClick={onRestoreDefaults}>
              <span className="sw"><Ico.refresh /></span>Restore defaults
            </button>
          </>
        }
      />

      <div className="au-page" style={{ padding: 0, display: 'grid', gridTemplateColumns: '188px 1fr', minHeight: 0 }}>

        <nav style={{ padding: '20px 12px', borderRight: '1px solid var(--hairline)', display: 'flex', flexDirection: 'column', gap: 2 }}>
          {[
            ['audio', 'Audio source'],
            ['transcription', 'Transcription'],
            ['triggers', 'Triggers'],
            ['saving', 'Saving'],
            ['autostop', 'Auto-stop'],
            ['vocab', 'Dynamic vocab'],
            ['appearance', 'Appearance'],
            ['storage', 'Storage'],
          ].map(([id, label]) => (
            <SettingsNav key={id} id={id} label={label}
                         active={activeSec === id}
                         onClick={() => {
                           setActiveSec(id);
                           scrollToSection(id);
                         }} />
          ))}
        </nav>

        <div ref={scrollContainerRef}
             style={{ padding: '24px 32px 32px', overflow: 'auto', minHeight: 0, maxWidth: 760 }}>

          <Sec id="audio" title="Audio source" desc="Pick what Auralis listens to.">
            <Row label="Capture mode"
                 desc="Whole system is simplest; per-app is best for Zoom or Chrome.">
              <div className="au-seg">
                {[
                  ['Whole system', 'system'],
                  ['Output device', 'device'],
                  ['Specific app', 'app'],
                ].map(([t, v]) => (
                  <button key={v} className={captureMode === v ? 'is-on' : ''}
                          onClick={() => save({ audio_capture_mode: v })}>{t}</button>
                ))}
              </div>
            </Row>

            {captureMode === 'device' && (
              <Row label="Output device"
                   desc="The speaker Auralis loops back from.">
                <select className="au-select" style={{ maxWidth: 360 }}
                        value={cfg.output_device_name || ''}
                        onChange={e => save({ output_device_name: e.target.value })}>
                  <option value="">(default speaker)</option>
                  {devices.map(d => <option key={d} value={d}>{d}</option>)}
                </select>
              </Row>
            )}

            {captureMode === 'app' && (
              <Row label="Audio-emitting app"
                   desc="Showing apps producing sound right now — refreshes live.">
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <select className="au-select" style={{ maxWidth: 280 }}
                          value={cfg.output_app_name || ''}
                          onChange={e => {
                            const name = e.target.value;
                            const found = (audioApps || []).find(a => a.name === name);
                            save({
                              output_app_name: name,
                              output_app_pid: found ? found.pid : 0,
                            });
                          }}>
                    <option value="">(pick an app)</option>
                    {audioApps.map(a => (
                      <option key={(a.pid || 0) + ':' + a.name} value={a.name}>
                        {(a.playing ? '▶ ' : '  ') + a.name}
                      </option>
                    ))}
                  </select>
                  <span className="au-pill is-good" style={{ height: 26 }}>
                    <span className="dot" />{sessionsCount} session{sessionsCount === 1 ? '' : 's'} live
                  </span>
                  <button className="au-btn sm" onClick={async () => {
                    await api.refreshApps();
                    const c = await api.audioSessionsCount();
                    setSessionsCount(c || 0);
                  }}>
                    <Ico.refresh /> Refresh
                  </button>
                </div>
              </Row>
            )}

            <Row label="Language" desc="auto detects per segment.">
              <select className="au-select" style={{ maxWidth: 220 }}
                      value={cfg.language || 'he'}
                      onChange={e => save({ language: e.target.value })}>
                <option value="auto">auto (mixed he + en)</option>
                <option value="he">Hebrew (he)</option>
                <option value="en">English (en)</option>
              </select>
            </Row>
          </Sec>

          <Sec id="transcription" title="Transcription" desc="Whisper model.">
            <Row label="Model"
                 desc="Pre-bundled. Auralis offers to download larger ones on demand.">
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <select className="au-select" style={{ maxWidth: 360 }}
                        value={cfg.whisper_model_label || ''}
                        onChange={e => onModelChange(e.target.value)}>
                  {modelLabels.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
                {modelStatus && (
                  modelStatus.downloaded ? (
                    <span className="au-pill is-good" style={{ height: 26 }}>
                      <Ico.check />Downloaded · {(modelStatus.size_mb / 1024).toFixed(1)} GB
                    </span>
                  ) : (
                    <span className="au-pill is-warn" style={{ height: 26 }}>
                      <span className="dot" />Not in cache
                    </span>
                  )
                )}
              </div>
            </Row>
            <Row label="Compute type"
                 desc="int8 is fast on CPU; float16 needs a CUDA GPU.">
              <select className="au-select" style={{ maxWidth: 200 }}
                      value={cfg.compute_type || 'int8'}
                      onChange={e => save({ compute_type: e.target.value })}>
                <option value="int8">int8 (CPU)</option>
                <option value="int8_float16">int8_float16</option>
                <option value="float16">float16 (GPU)</option>
                <option value="float32">float32</option>
              </select>
            </Row>
          </Sec>

          <Sec id="triggers" title="Triggers"
               desc="Words that copy recent transcript context to your clipboard.">
            <Row label="Keywords">
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
                {(cfg.triggers || []).map(t => (
                  <span key={t} className="au-chip"
                        dir={/[֐-׿]/.test(t) ? 'rtl' : 'ltr'}>
                    {t}
                    <span className="x" onClick={() => removeTrigger(t)}><Ico.x /></span>
                  </span>
                ))}
                <button className="au-btn sm au-btn-ghost"
                        style={{ height: 24, padding: '0 8px', fontSize: 11.5 }}
                        onClick={addTrigger}>
                  <Ico.plus /> Add keyword
                </button>
              </div>
            </Row>
            <Row label="Cooldown"
                 desc="Won't re-fire the same trigger more than once every N seconds.">
              <div className="au-num">
                <button onClick={() => { const v = Math.max(5, cooldown - 5); setCooldown(v); save({ cooldown_seconds: v }); }}>−</button>
                <input value={cooldown}
                       onChange={e => setCooldown(parseInt(e.target.value, 10) || 0)}
                       onBlur={() => save({ cooldown_seconds: cooldown })} />
                <button onClick={() => { const v = cooldown + 5; setCooldown(v); save({ cooldown_seconds: v }); }}>+</button>
                <span style={{ padding: '0 10px', color: 'var(--text-3)', fontSize: 12 }}>seconds</span>
              </div>
            </Row>
            <Row label="When a trigger word fires, ask Claude"
                 desc="The prompt that's pre-pended to the trigger payload.">
              <textarea className="au-textarea"
                        defaultValue={cfg.meeting_prompt || ''}
                        onBlur={e => save({ meeting_prompt: e.target.value })}
                        style={{ minHeight: 70 }} />
            </Row>
          </Sec>

          <Sec id="saving" title="Saving & post-processing">
            <Toggle label="Save live transcript on Stop"
                    desc="A .txt next to the .wav."
                    on={!!cfg.save_live_transcript_enabled}
                    onChange={v => save({ save_live_transcript_enabled: v })} />
            <Toggle label="Post-process audio on Stop"
                    desc="Higher-accuracy second pass. Runs in the background."
                    on={!!cfg.postprocess_enabled}
                    onChange={v => save({ postprocess_enabled: v })} />
            <Toggle label="Save raw audio (.wav)"
                    desc="Disable to save space if you only need transcripts."
                    on={!!cfg.save_audio}
                    onChange={v => save({ save_audio: v })} />
          </Sec>

          <Sec id="autostop" title="Auto-stop on silence"
               desc="Walk away during a Q&A break and Auralis will stop on its own.">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <Row inline label="Silence cutoff" desc="0 disables auto-stop.">
                <div className="au-num">
                  <button onClick={() => { const v = Math.max(0, autostop - 5); setAutostop(v); save({ auto_stop_silence_minutes: v }); }}>−</button>
                  <input value={autostop}
                         onChange={e => setAutostop(parseInt(e.target.value, 10) || 0)}
                         onBlur={() => save({ auto_stop_silence_minutes: autostop })} />
                  <button onClick={() => { const v = autostop + 5; setAutostop(v); save({ auto_stop_silence_minutes: v }); }}>+</button>
                  <span style={{ padding: '0 10px', color: 'var(--text-3)', fontSize: 12 }}>minutes</span>
                </div>
              </Row>
              <Row inline label="Silence threshold"
                   desc="Lecture audio ~0.05. Use 0.005 to catch whispers.">
                <div className="au-num">
                  <input value={silthr}
                         onChange={e => setSilthr(parseFloat(e.target.value) || 0)}
                         onBlur={() => save({ silence_rms_threshold: silthr })} />
                </div>
              </Row>
            </div>
          </Sec>

          <Sec id="vocab" title="Dynamic vocabulary"
               desc="Auralis tracks recurring words and feeds them back to Whisper.">
            <Toggle label="Enabled"
                    desc="Auto-bias the model every refresh interval."
                    on={!!cfg.dynamic_vocab_enabled}
                    onChange={v => save({ dynamic_vocab_enabled: v })} />
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
              <Row inline label="Update interval">
                <div className="au-num">
                  <button onClick={() => { const v = Math.max(1, dvInt - 1); setDvInt(v); save({ dynamic_vocab_interval_minutes: v }); }}>−</button>
                  <input value={dvInt}
                         onChange={e => setDvInt(parseInt(e.target.value, 10) || 0)}
                         onBlur={() => save({ dynamic_vocab_interval_minutes: dvInt })} />
                  <button onClick={() => { const v = dvInt + 1; setDvInt(v); save({ dynamic_vocab_interval_minutes: v }); }}>+</button>
                  <span style={{ padding: '0 10px', color: 'var(--text-3)', fontSize: 12 }}>min</span>
                </div>
              </Row>
              <Row inline label="History window">
                <div className="au-num">
                  <button onClick={() => { const v = Math.max(1, dvHist - 5); setDvHist(v); save({ dynamic_vocab_history_minutes: v }); }}>−</button>
                  <input value={dvHist}
                         onChange={e => setDvHist(parseInt(e.target.value, 10) || 0)}
                         onBlur={() => save({ dynamic_vocab_history_minutes: dvHist })} />
                  <button onClick={() => { const v = dvHist + 5; setDvHist(v); save({ dynamic_vocab_history_minutes: v }); }}>+</button>
                  <span style={{ padding: '0 10px', color: 'var(--text-3)', fontSize: 12 }}>min</span>
                </div>
              </Row>
              <Row inline label="Top-N terms">
                <div className="au-num">
                  <button onClick={() => { const v = Math.max(5, dvTopN - 5); setDvTopN(v); save({ dynamic_vocab_top_n: v }); }}>−</button>
                  <input value={dvTopN}
                         onChange={e => setDvTopN(parseInt(e.target.value, 10) || 0)}
                         onBlur={() => save({ dynamic_vocab_top_n: dvTopN })} />
                  <button onClick={() => { const v = dvTopN + 5; setDvTopN(v); save({ dynamic_vocab_top_n: v }); }}>+</button>
                </div>
              </Row>
            </div>
          </Sec>

          <Sec id="appearance" title="Appearance">
            <Toggle label="Dark theme"
                    desc="Toggle between dark and light palettes."
                    on={!!cfg.dark_mode}
                    onChange={v => api.setTheme(v)} />
          </Sec>

          <Sec id="storage" title="Storage"
               desc="All data lives next to the app — back up these folders and you keep your library.">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <a style={{ color: 'var(--accent)', cursor: 'pointer', fontWeight: 500, fontSize: 13 }}
                 onClick={() => api.openPath(state.app_dir)}>
                → Open Auralis folder
              </a>
              <a style={{ color: 'var(--accent)', cursor: 'pointer', fontWeight: 500, fontSize: 13 }}
                 onClick={() => api.openPath((state.app_dir || '') + '/logs/auralis.log')}>
                → Open log file
              </a>
              <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
                Version {state.version || ''} · built {state.build_date || ''}
              </div>
            </div>
          </Sec>

          {/* Footer save bar */}
          <div style={{ display: 'flex', gap: 10, marginTop: 24, paddingTop: 18,
                        borderTop: '1px solid var(--hairline)', alignItems: 'center' }}>
            <button className="au-btn au-btn-ghost"
                    onClick={() => window.location.reload()}>Discard unsaved edits</button>
            <div style={{ flex: 1 }} />
            <span style={{ fontSize: 12, color: 'var(--text-4)' }}>
              Settings auto-save{lastSavedAgo ? ' · last edited ' + lastSavedAgo : ''}
            </span>
          </div>

        </div>
      </div>
    </AuFrame>
  );
}

function SettingsNav({ id, label, active, onClick }) {
  return (
    <div onClick={onClick} style={{
      height: 30, padding: '0 12px',
      display: 'flex', alignItems: 'center',
      borderRadius: 6,
      background: active ? 'var(--accent-soft)' : 'transparent',
      color: active ? 'var(--text)' : 'var(--text-2)',
      fontSize: 13, fontWeight: active ? 500 : 450,
      cursor: 'pointer', position: 'relative',
    }}>
      {active && <span style={{ position: 'absolute', left: -12, top: 7, bottom: 7, width: 2, borderRadius: '0 2px 2px 0', background: 'var(--accent)' }} />}
      {label}
    </div>
  );
}

Object.assign(window, { Settings });
