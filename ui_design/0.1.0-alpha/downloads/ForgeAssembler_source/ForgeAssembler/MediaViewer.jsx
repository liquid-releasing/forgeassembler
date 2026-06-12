// MediaViewer — reusable video/audio thumbnail with transport.
//
// Sits next to ChapterFunscriptView (Edit tab) and reused on Stim/Multi-axis.
// Height matches its container so it can stand to the right of the chapter
// strip + funscript view. Width is fixed (compact thumbnail).
//
// Props:
//   currentMs       — playhead position
//   isPlaying       — bool
//   onPlayPause     — toggle
//   onSeek(ms)      — jump
//   onPrevChapter   — jump to prev chapter start
//   onNextChapter   — jump to next chapter start
//   onCreateChapter — create chapter at currentMs
//   chapter         — { id,title,color,start,end } currently scoped chapter
//   media           — { kind: 'video'|'audio', poster?, title }
//
// Buttons use emojis per request, with native title tooltips.

function MediaViewer({
  currentMs = 0, isPlaying = false,
  onPlayPause, onSeek,
  onPrev, onNext,
  prevTitle = "Previous chapter", nextTitle = "Next chapter",
  onCreateChapter, showCreateChapter = true,
  chapter, media = { kind: "video", title: "preview" },
  width = 240, height,
}) {
  // Back-compat: callers may still pass onPrevChapter/onNextChapter
  onPrev = onPrev || arguments[0]?.onPrevChapter;
  onNext = onNext || arguments[0]?.onNextChapter;
  const fmt = (ms) => {
    const s = Math.max(0, Math.floor(ms / 1000));
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  };

  const chapDur = chapter ? Math.max(1, chapter.end - chapter.start) : 1;
  const chapPos = chapter
    ? Math.min(1, Math.max(0, (currentMs - chapter.start) / chapDur))
    : 0;

  const stepFrame = (dir) => {
    // ~30fps step
    onSeek?.((currentMs || 0) + dir * 33);
  };
  const back5 = () => onSeek?.(Math.max(0, (currentMs || 0) - 5000));

  const btn = {
    width: 26, height: 26, borderRadius: 6,
    background: "var(--surface-2)",
    border: "1px solid var(--border)",
    color: "var(--text)",
    cursor: "pointer", fontSize: 13,
    display: "grid", placeItems: "center",
    fontFamily: "inherit", padding: 0,
  };
  const btnPrimary = {
    ...btn, width: 32, height: 32, borderRadius: 16,
    background: "var(--accent)", borderColor: "transparent",
    color: "#fff", fontSize: 14,
  };

  return (
    <div style={{
      width, height, flexShrink: 0,
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 8,
      display: "flex", flexDirection: "column",
      overflow: "hidden",
    }}>
      {/* Thumbnail */}
      <div style={{
        flex: 1, minHeight: 0,
        background: "linear-gradient(135deg, #16181d 0%, #1f242c 100%)",
        position: "relative", overflow: "hidden",
      }}>
        {media.kind === "audio"
          ? <AudioWave />
          : <VideoPoster title={media.title} />}

        {/* baton synced with funscript playhead */}
        <div style={{
          position: "absolute", top: 0, bottom: 0,
          left: `${chapPos * 100}%`,
          width: 1.5,
          background: "rgba(255,255,255,0.85)",
          boxShadow: "0 0 6px rgba(255,255,255,0.45)",
          pointerEvents: "none",
        }} />

        {/* corner labels */}
        <div style={{ position: "absolute", top: 6, left: 8,
          fontSize: 9, fontWeight: 700, letterSpacing: "0.08em",
          color: "rgba(255,255,255,0.7)", textTransform: "uppercase" }}>
          {media.kind === "audio" ? "Audio" : "Video"}
        </div>
        {chapter && (
          <div style={{ position: "absolute", bottom: 6, left: 8, right: 8,
            display: "flex", alignItems: "center", gap: 5,
            fontSize: 9.5, color: "rgba(255,255,255,0.8)" }}>
            <span style={{ width: 6, height: 6, borderRadius: 1,
              background: chapter.color }} />
            <span style={{ overflow: "hidden", textOverflow: "ellipsis",
              whiteSpace: "nowrap" }}>{chapter.title}</span>
          </div>
        )}
      </div>

      {/* Time readout */}
      <div className="mono" style={{
        padding: "5px 10px", fontSize: 10.5,
        color: "var(--text-muted)",
        borderTop: "1px solid var(--border)",
        display: "flex", justifyContent: "space-between",
      }}>
        <span>{fmt(currentMs)}</span>
        {chapter && <span>{fmt(chapter.end)}</span>}
      </div>

      {/* Transport row 1 — chapter nav + create */}
      <div style={{
        padding: "6px 8px", display: "flex", gap: 4, justifyContent: "center",
        borderTop: "1px solid var(--border)",
      }}>
        <button style={btn} title={prevTitle} onClick={onPrev}>⏮</button>
        <button style={btn} title="Frame back" onClick={() => stepFrame(-1)}>◀</button>
        <button style={btn} title="Back 5s" onClick={back5}>⏪</button>
        <button style={btnPrimary} title={isPlaying ? "Pause" : "Play"}
                onClick={onPlayPause}>{isPlaying ? "⏸" : "▶"}</button>
        <button style={btn} title="Frame forward" onClick={() => stepFrame(1)}>▶</button>
        <button style={btn} title={nextTitle} onClick={onNext}>⏭</button>
      </div>

      {/* Transport row 2 — chapter actions */}
      {showCreateChapter && (
        <div style={{
          padding: "0 8px 8px", display: "flex", gap: 4, justifyContent: "center",
        }}>
          <button style={{ ...btn, width: "auto", padding: "0 8px", fontSize: 10.5 }}
                  title="Create chapter at playhead" onClick={onCreateChapter}>
            ➕ Chapter
          </button>
        </div>
      )}
    </div>
  );
}

// Faux video poster: a faint film-strip pattern + center play glyph
function VideoPoster({ title }) {
  return (
    <svg width="100%" height="100%" viewBox="0 0 100 60" preserveAspectRatio="none"
         style={{ display: "block" }}>
      <defs>
        <pattern id="stripes" width="6" height="60" patternUnits="userSpaceOnUse">
          <rect width="2" height="6" x="0" y="2" fill="rgba(255,255,255,0.04)" />
          <rect width="2" height="6" x="0" y="52" fill="rgba(255,255,255,0.04)" />
        </pattern>
      </defs>
      <rect width="100" height="60" fill="url(#stripes)" />
      {/* abstract scene: a horizon with a soft glow */}
      <rect x="0" y="34" width="100" height="26" fill="rgba(217,87,33,0.10)" />
      <circle cx="72" cy="28" r="9" fill="rgba(255,180,120,0.18)" />
      <circle cx="72" cy="28" r="4" fill="rgba(255,200,140,0.35)" />
      <path d="M 0 42 Q 25 38 50 42 T 100 42 L 100 60 L 0 60 Z"
            fill="rgba(60,40,30,0.55)" />
    </svg>
  );
}

// Audio: stylized waveform poster
function AudioWave() {
  const bars = Array.from({ length: 48 });
  return (
    <svg width="100%" height="100%" viewBox="0 0 100 60" preserveAspectRatio="none"
         style={{ display: "block" }}>
      {bars.map((_, i) => {
        const x = (i / bars.length) * 100;
        const w = 100 / bars.length - 0.4;
        // pseudo-random envelope
        const h = 6 + Math.abs(Math.sin(i * 1.3) * 18) + Math.abs(Math.cos(i * 0.7) * 10);
        const y = (60 - h) / 2;
        return (
          <rect key={i} x={x} y={y} width={w} height={h} rx="0.5"
                fill="rgba(217,87,33,0.55)" />
        );
      })}
    </svg>
  );
}

window.MediaViewer = MediaViewer;
window.VideoPoster = VideoPoster;
window.AudioWave   = AudioWave;
