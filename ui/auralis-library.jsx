/* global React, AuFrame, AuTopbar, Ico */

const { useState: useStateLib, useEffect: useEffectLib,
        useMemo: useMemoLib, useRef: useRefLib } = React;

// =====================================================================
// LIBRARY — course rail + recording rows + bulk action bar.
// =====================================================================
function Library({ state, api }) {
  const lib = state.library || [];
  const fallbackCourse = (state.config && state.config.current_course)
                      || (lib[0] && lib[0].course) || '';
  const [activeCourse, setActiveCourse]     = useStateLib(fallbackCourse);
  const [activeCategory, setActiveCategory] = useStateLib('Lectures');
  const [selected, setSelected]             = useStateLib(new Set()); // multi-select
  const [search, setSearch]                 = useStateLib('');
  const [openMenu, setOpenMenu]             = useStateLib(null); // path string of row with kebab open
  const [viewMode, setViewMode]             = useStateLib(state.config?.library_view_mode || 'list');

  useEffectLib(() => {
    if (lib.length > 0 && !lib.some(e => e.course === activeCourse)) {
      setActiveCourse(lib[0].course);
    }
  }, [lib.map(e => e.course).join('|')]);

  // Persist view mode.
  useEffectLib(() => {
    if (viewMode !== state.config?.library_view_mode) {
      api.saveConfig({ library_view_mode: viewMode });
    }
  }, [viewMode]);

  const activeEntry = lib.find(e => e.course === activeCourse) || lib[0];
  const allCats = activeEntry ? Object.keys(activeEntry.categories) : [];
  const orderedCats = ['Lectures', 'Exercises']
    .concat(allCats.filter(c => c !== 'Lectures' && c !== 'Exercises' && c !== ''))
    .concat(allCats.includes('') ? ['(root)'] : []);
  const catCounts = {};
  if (activeEntry) {
    for (const c of allCats) catCounts[c || '(root)'] = (activeEntry.categories[c] || []).length;
  }

  const recordings = activeEntry
    ? (activeEntry.categories[activeCategory === '(root)' ? '' : activeCategory] || [])
    : [];

  const filteredRecordings = recordings.filter(r =>
    !search.trim() || r.name.toLowerCase().includes(search.trim().toLowerCase())
  );

  const groups = useMemoLib(() => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000;
    const yesterday = today - 86400;
    const buckets = { Today: [], Yesterday: [], Earlier: [] };
    for (const r of filteredRecordings) {
      if (r.mtime_epoch >= today) buckets.Today.push(r);
      else if (r.mtime_epoch >= yesterday) buckets.Yesterday.push(r);
      else buckets.Earlier.push(r);
    }
    return ['Today', 'Yesterday', 'Earlier']
      .filter(k => buckets[k].length > 0)
      .map(k => ({ label: k, items: buckets[k] }));
  }, [filteredRecordings.map(r => r.path).join('|')]);

  const fmtDuration = secs => {
    const s = Math.max(0, Math.floor(secs || 0));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return h > 0 ? `${h}h ${m}m` : `${m}m ${sec}s`;
  };

  const onImport      = () => api.importWav();
  const onOpenRoot    = () => api.openPath(state.app_dir);
  const onNewCourse   = async () => {
    const name = window.prompt('New course name:');
    if (name && name.trim()) {
      const r = await api.newCourse(name.trim());
      if (r && r.ok) setActiveCourse(name.trim());
    }
  };

  // Multi-select helpers.
  const onRowClick = (e, path) => {
    if (e.shiftKey || e.ctrlKey || e.metaKey) {
      setSelected(prev => {
        const next = new Set(prev);
        if (next.has(path)) next.delete(path); else next.add(path);
        return next;
      });
    } else {
      setSelected(new Set([path]));
    }
  };
  const onRowDoubleClick = (rec) => {
    api.openPath(rec.post_path || rec.live_path || rec.path);
  };
  const clearSelection = () => setSelected(new Set());

  const selectedRecs = filteredRecordings.filter(r => selected.has(r.path));
  const hasSel = selected.size > 0;
  const singleSel = selected.size === 1 ? [...selected][0] : null;

  const onPlay = () => {
    if (!singleSel) return;
    const rec = recordings.find(r => r.path === singleSel);
    if (rec && window.__appPlay) window.__appPlay(rec);
  };
  const onRepolish = async () => {
    for (const p of selected) {
      await api.rerunPostprocess(p);
    }
  };
  const onOpenTrans = () => {
    if (!singleSel) return;
    const r = recordings.find(x => x.path === singleSel);
    if (!r) return;
    api.openPath(r.post_path || r.live_path || r.path);
  };
  const onMove = async () => {
    if (!hasSel) return;
    const courses = (state.config && state.config.courses) || [];
    const target = window.prompt('Move ' + selected.size +
      ' recording(s) to course:\nOptions: ' + courses.join(', '));
    if (!target || !target.trim()) return;
    for (const p of selected) await api.moveRecording(p, target.trim());
    clearSelection();
  };
  const onDelete = async () => {
    if (!hasSel) return;
    if (!window.confirm('Permanently delete ' + selected.size +
      ' recording(s) and their transcripts?')) return;
    for (const p of selected) await api.deleteRecording(p);
    clearSelection();
  };

  // Empty state — no courses at all.
  if (lib.length === 0) {
    return (
      <AuFrame tab="library">
        <AuTopbar title="Library" sub="Every recording, organized by course."
                  actions={
                    <>
                      <button className="au-tb-btn" onClick={onImport}>
                        <span className="sw"><Ico.upload /></span>Import WAV
                      </button>
                      <button className="au-tb-btn" onClick={onOpenRoot}>
                        <span className="sw"><Ico.folder /></span>Open root
                      </button>
                    </>
                  } />
        <div className="au-empty" style={{ margin: 'auto', maxWidth: 380 }}>
          <div className="e-ico" style={{ width: 56, height: 56, borderRadius: 14 }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
              <rect x="3.5" y="5" width="17" height="14" rx="2" />
              <path d="M7 9h10M7 12h10M7 15h7" />
            </svg>
          </div>
          <h3>No recordings yet</h3>
          <p>Hit <b style={{ color: 'var(--text-2)' }}>Live</b> in the sidebar, pick a course, and press record. Lectures will appear here automatically.</p>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 16 }}>
            <button className="au-btn au-btn-primary"
                    onClick={() => window.__appOnSelect('live')}>
              <Ico.live /> Go to Live
            </button>
            <button className="au-btn" onClick={onImport}>
              <Ico.upload /> Import WAV
            </button>
          </div>
        </div>
      </AuFrame>
    );
  }

  return (
    <AuFrame tab="library">
      <AuTopbar
        title="Library"
        sub="Every recording, organized by course."
        actions={
          <>
            <div style={{ position: 'relative', marginRight: 6 }}>
              <input
                placeholder="Search recordings…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{
                  width: 240, height: 30, padding: '0 10px 0 30px',
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 6, color: 'var(--text)', fontSize: 12.5, outline: 'none',
                }}
              />
              <span style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-4)', pointerEvents: 'none', width: 14, height: 14, display: 'grid', placeItems: 'center' }}><Ico.search /></span>
            </div>
            <button className="au-tb-btn" onClick={onImport}>
              <span className="sw"><Ico.upload /></span>Import WAV
            </button>
            <button className="au-tb-btn" onClick={onOpenRoot}>
              <span className="sw"><Ico.folder /></span>Open root
            </button>
          </>
        }
      />

      <div className="au-page" style={{ padding: '20px 28px 24px', display: 'grid', gridTemplateColumns: '236px 1fr', gap: 22 }}>

        <aside style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
          <div className="au-h2" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '4px 6px 8px' }}>
            <span>Courses</span>
            <span style={{ fontSize: 11, color: 'var(--text-4)' }}>{lib.length}</span>
          </div>
          {lib.map(entry => (
            <CourseRow key={entry.course || '(root)'}
                       active={entry.course === activeCourse}
                       count={entry.total_recordings}
                       label={entry.course || '(at root)'}
                       duration={fmtDuration(entry.total_duration_s)}
                       onClick={() => { setActiveCourse(entry.course); setActiveCategory('Lectures'); clearSelection(); }} />
          ))}

          <button className="au-btn sm au-btn-ghost"
                  style={{ marginTop: 10, justifyContent: 'flex-start' }}
                  onClick={onNewCourse}>
            <Ico.plus /> New course
          </button>
        </aside>

        <section style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <h2 style={{ margin: 0, fontSize: 17, fontWeight: 600, letterSpacing: '-0.005em' }}
                className={/[֐-׿]/.test(activeCourse) ? 'bidi' : ''}
                dir={/[֐-׿]/.test(activeCourse) ? 'rtl' : 'ltr'}>
              {activeCourse || '(at root)'}
            </h2>
            {activeEntry && (
              <span className="au-pill">
                <span className="dot" />
                {activeEntry.total_recordings} recording{activeEntry.total_recordings === 1 ? '' : 's'} · {fmtDuration(activeEntry.total_duration_s)}
              </span>
            )}
            <div style={{ flex: 1 }} />
            <div className="au-seg">
              {orderedCats.map(c => (
                <button key={c} className={c === activeCategory ? 'is-on' : ''}
                        onClick={() => { setActiveCategory(c); clearSelection(); }}>
                  {c} · {catCounts[c] || 0}
                </button>
              ))}
            </div>
            <div className="au-seg">
              <button className={viewMode === 'list' ? 'is-on' : ''}
                      onClick={() => setViewMode('list')}>List</button>
              <button className={viewMode === 'cards' ? 'is-on' : ''}
                      onClick={() => setViewMode('cards')}>Cards</button>
            </div>
          </div>

          {viewMode === 'list' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {groups.length === 0 ? (
                <div style={{ padding: 24, color: 'var(--text-3)', fontSize: 13 }}>
                  No recordings in this category yet.
                </div>
              ) : groups.map(g => (
                <React.Fragment key={g.label}>
                  <DayDivider>{g.label}</DayDivider>
                  {g.items.map(r => (
                    <RecordingRow key={r.path}
                                  rec={r}
                                  selected={selected.has(r.path)}
                                  onClick={(e) => onRowClick(e, r.path)}
                                  onDoubleClick={() => onRowDoubleClick(r)}
                                  openMenu={openMenu === r.path}
                                  onMenuToggle={() => setOpenMenu(openMenu === r.path ? null : r.path)}
                                  api={api} />
                  ))}
                </React.Fragment>
              ))}
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12 }}>
              {filteredRecordings.length === 0 ? (
                <div style={{ padding: 24, color: 'var(--text-3)', fontSize: 13 }}>
                  No recordings in this category yet.
                </div>
              ) : filteredRecordings.map(r => (
                <RecordingCard key={r.path} rec={r}
                               selected={selected.has(r.path)}
                               onClick={(e) => onRowClick(e, r.path)}
                               onDoubleClick={() => onRowDoubleClick(r)}
                               api={api} />
              ))}
            </div>
          )}

          {/* Bulk action bar */}
          <div style={{
            marginTop: 22, padding: 12,
            background: 'var(--surface)', border: '1px solid var(--hairline)',
            borderRadius: 12,
            display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 24, height: 24, borderRadius: 6, background: 'var(--accent-soft)', color: 'var(--accent)', display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 600 }}>
                {selected.size}
              </span>
              <span style={{ fontSize: 12.5, color: 'var(--text-2)' }}>
                {hasSel ? 'selected' : 'no selection'}
              </span>
              {selected.size > 1 && (
                <span style={{ marginLeft: 6, fontSize: 11.5, color: 'var(--text-4)', cursor: 'pointer' }}
                      onClick={clearSelection}>clear</span>
              )}
            </div>
            <div style={{ width: 1, height: 18, background: 'var(--hairline)' }} />
            <button className="au-btn sm" disabled={!singleSel} onClick={onPlay}><Ico.play />Play</button>
            <button className="au-btn sm" disabled={!hasSel} onClick={onRepolish}><Ico.spark />Re-polish</button>
            <button className="au-btn sm" disabled={!singleSel} onClick={onOpenTrans}><Ico.external />Open transcript</button>
            <button className="au-btn sm" disabled={!hasSel} onClick={onMove}><Ico.folder />Move to course…</button>
            <div style={{ flex: 1 }} />
            <button className="au-btn sm"
                    disabled={!hasSel}
                    onClick={onDelete}
                    style={hasSel ? { color: 'var(--rec)', borderColor: 'rgba(240,101,106,0.35)' } : {}}>
              <Ico.trash />Delete
            </button>
          </div>
        </section>
      </div>
    </AuFrame>
  );
}

function CourseRow({ active, count, label, duration, onClick }) {
  const rtl = /[֐-׿]/.test(label);
  return (
    <div onClick={onClick} style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '8px 10px', borderRadius: 7,
      background: active ? 'var(--accent-soft)' : 'transparent',
      cursor: 'pointer', position: 'relative', minWidth: 0,
    }}>
      {active && <span style={{ position: 'absolute', left: -10, top: 9, bottom: 9, width: 2, borderRadius: '0 2px 2px 0', background: 'var(--accent)' }} />}
      <span style={{ color: active ? 'var(--accent)' : 'var(--text-3)', width: 14, height: 14, display: 'inline-grid', placeItems: 'center', flex: '0 0 14px' }}>
        <Ico.folder />
      </span>
      <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
        <div className={rtl ? 'bidi' : ''} dir={rtl ? 'rtl' : 'ltr'} style={{
          fontSize: 12.5, fontWeight: 500,
          color: active ? 'var(--text)' : 'var(--text-2)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{label}</div>
        <div style={{ fontSize: 11, color: 'var(--text-4)' }}>{count} rec · {duration}</div>
      </div>
    </div>
  );
}

function DayDivider({ children }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 4px 6px' }}>
      <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{children}</span>
      <span style={{ flex: 1, height: 1, background: 'var(--hairline)' }} />
    </div>
  );
}

function RowKebabMenu({ rec, api, onClose }) {
  return (
    <div className="au-menu" style={{ top: 38, right: 0 }}
         onClick={e => e.stopPropagation()}
         onMouseLeave={onClose}>
      <div className="au-menu-item"
           onClick={() => { onClose(); api.openPath(rec.post_path || rec.live_path || rec.path); }}>
        Open transcript
      </div>
      <div className="au-menu-item"
           onClick={() => { onClose(); api.openPath(rec.path); }}>
        Open WAV
      </div>
      <div className="au-menu-sep" />
      <div className="au-menu-item"
           onClick={async () => {
             onClose();
             const newName = window.prompt('Rename recording to:', rec.name);
             if (newName && newName.trim() && newName !== rec.name) {
               await api.renameRecording(rec.path, newName.trim());
             }
           }}>Rename…</div>
      <div className="au-menu-item"
           onClick={async () => {
             onClose();
             const courses = (window.__appState?.config?.courses) || [];
             const target = window.prompt('Move to course:\nOptions: ' + courses.join(', '));
             if (target && target.trim()) api.moveRecording(rec.path, target.trim());
           }}>Move to course…</div>
      <div className="au-menu-item"
           onClick={() => { onClose(); api.rerunPostprocess(rec.path); }}>
        Re-polish
      </div>
      <div className="au-menu-item"
           onClick={() => { onClose(); api.revealInFolder(rec.path); }}>
        Reveal in Explorer
      </div>
      <div className="au-menu-sep" />
      <div className="au-menu-item is-danger"
           onClick={() => {
             onClose();
             if (window.confirm('Permanently delete "' + rec.name + '" and its transcripts?')) {
               api.deleteRecording(rec.path);
             }
           }}>Delete…</div>
    </div>
  );
}

function RecordingRow({ rec, selected, onClick, onDoubleClick, openMenu, onMenuToggle, api }) {
  const bars = React.useMemo(
    () => Array.from({ length: 24 }, (_, i) =>
      0.2 + 0.8 * Math.abs(Math.sin(i * 0.9 + (rec.name || '').length))),
    [rec.name]
  );
  const onKebabClick = (e) => {
    e.stopPropagation();
    onMenuToggle();
  };
  return (
    <div onClick={onClick} onDoubleClick={onDoubleClick} style={{
      display: 'grid', gridTemplateColumns: '36px 1fr auto auto auto 28px',
      alignItems: 'center', gap: 14, padding: '12px 14px',
      borderRadius: 10,
      background: selected ? 'var(--accent-soft)' : 'var(--surface)',
      border: '1px solid ' + (selected ? 'var(--accent-rim)' : 'var(--hairline)'),
      cursor: 'pointer', position: 'relative',
    }}>
      <button className="au-iconbtn" style={{
        background: 'var(--surface-2)', color: 'var(--accent)',
        width: 32, height: 32, borderRadius: 8,
      }} onClick={e => { e.stopPropagation(); if (window.__appPlay) window.__appPlay(rec); }}
         title="Play in app">
        <Ico.play />
      </button>

      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {rec.name}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 3, fontSize: 11.5, color: 'var(--text-3)', flexWrap: 'wrap' }}>
          <span>{rec.mtime_human}</span>
          <span style={{ color: 'var(--text-4)' }}>·</span>
          <span>{rec.duration_human}</span>
          <span style={{ color: 'var(--text-4)' }}>·</span>
          <span>{rec.size_human}</span>
          {rec.warn && (
            <>
              <span style={{ color: 'var(--text-4)' }}>·</span>
              <span style={{ color: 'var(--warning)' }}>{rec.warn}</span>
            </>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 6 }}>
        {rec.has_live && (
          <span className="au-pill" style={{ height: 20, fontSize: 10.5 }}>
            <Ico.check />Live
          </span>
        )}
        {rec.is_polishing ? (
          <span className="au-pill is-warn" style={{ height: 20, fontSize: 10.5 }}>
            <span className="dot" />Polishing
          </span>
        ) : rec.has_post ? (
          <span className="au-pill is-accent" style={{ height: 20, fontSize: 10.5 }}>
            <Ico.spark />Polished
          </span>
        ) : null}
      </div>

      <div style={{ width: 80 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 1.5, height: 22 }}>
          {bars.map((h, i) => (
            <div key={i} style={{
              flex: '1 1 0', height: `${h * 100}%`, minHeight: 2,
              background: 'var(--border)', borderRadius: 1,
            }} />
          ))}
        </div>
      </div>

      <span style={{ fontSize: 11, color: 'var(--text-4)', fontFamily: 'var(--font-mono)' }}>
        {rec.mtime_short}
      </span>

      <button className="au-iconbtn" onClick={onKebabClick} title="More">
        <Ico.more />
      </button>
      {openMenu && (
        <RowKebabMenu rec={rec} api={api}
                      onClose={() => onMenuToggle()} />
      )}
    </div>
  );
}

function RecordingCard({ rec, selected, onClick, onDoubleClick, api }) {
  return (
    <div onClick={onClick} onDoubleClick={onDoubleClick} style={{
      padding: 14, borderRadius: 10,
      background: selected ? 'var(--accent-soft)' : 'var(--surface)',
      border: '1px solid ' + (selected ? 'var(--accent-rim)' : 'var(--hairline)'),
      cursor: 'pointer',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        {rec.has_live && (
          <span className="au-pill" style={{ height: 20, fontSize: 10.5 }}>
            <Ico.check />Live
          </span>
        )}
        {rec.is_polishing ? (
          <span className="au-pill is-warn" style={{ height: 20, fontSize: 10.5 }}>
            <span className="dot" />Polishing
          </span>
        ) : rec.has_post && (
          <span className="au-pill is-accent" style={{ height: 20, fontSize: 10.5 }}>
            <Ico.spark />Polished
          </span>
        )}
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 11, color: 'var(--text-4)', fontFamily: 'var(--font-mono)' }}>
          {rec.mtime_short}
        </span>
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text)', wordBreak: 'break-all', marginBottom: 6 }}>
        {rec.name}
      </div>
      <div style={{ fontSize: 11.5, color: 'var(--text-3)' }}>
        {rec.mtime_human} · {rec.duration_human} · {rec.size_human}
      </div>
    </div>
  );
}

Object.assign(window, { Library });
