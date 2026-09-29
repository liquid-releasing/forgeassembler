/* @esm-converted */
import React from 'react';
const { useCallback, useEffect, useState } = React;
import { ViewerPanel } from 'forgemoment';
import { FATabBody, FATabHeader } from './AppShell';
import { Button } from './primitives';
import { openPath, pickFile, revealPath, viewerLoad } from './api/forge';
import { toMediaUrl } from './lib/mediaUrl';
import { lastFolder, rememberFileFolder } from './lib/lastFolders';
import { PROJECT_EXT } from './lib/projectFile';

// Viewer — review what the forge actually WROTE.
//
// Every other surface in this app describes the output before it exists: the
// Build canvas, the compilation preview, the band under it. They are all
// derived from the project, so all of them agree with each other by
// construction — and none of them can catch a title card that rendered
// invisible against its own background, or a scene that starts three seconds
// late. Both of those shipped, and both were found by opening the file
// outside the app.
//
// So this tab reads the FILES. The surface is forgemoment's ViewerPanel,
// shared with FunscriptForge and ForgePlayer; what lives here is where
// ForgeAssembler's output is and what to say when there isn't any yet.

// What the engine will accept as "the output" — all four name the same thing,
// and `resolve_source` works out which was opened.
const OPEN_FILTERS = [
  { name: 'Forged output', extensions: ['mp4', 'mkv', 'mov', 'm4v', 'forge', PROJECT_EXT] },
  { name: 'Video', extensions: ['mp4', 'mkv', 'mov', 'm4v'] },
  { name: 'Forge scene', extensions: ['forge'] },
];

export function ViewerTab({ project, forgedPath = null }) {
  // What we're reviewing. Defaults to this project's own output — the forged
  // video if this session produced one, else the folder it would have gone
  // into, which is enough for the engine to find a previous forge.
  const ownOutput = forgedPath || project?.output?.folder || null;
  const [path, setPath] = useState(ownOutput);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  // Follow this project's output until the user opens something else. Without
  // the `path === null` arm a fresh project would keep showing the previous
  // one's forge, which is exactly the kind of quiet lie this tab exists to
  // catch elsewhere.
  useEffect(() => { setPath((p) => (p == null ? ownOutput : p)); }, [ownOutput]);

  useEffect(() => {
    if (!path) { setData(null); return undefined; }
    let live = true;
    setLoading(true);
    setErr(null);
    viewerLoad(path)
      .then((res) => { if (live) { setData(res || null); setLoading(false); } })
      .catch((e) => {
        if (live) { setErr(String(e?.message || e)); setData(null); setLoading(false); }
      });
    return () => { live = false; };
  }, [path]);

  const loadChannel = useCallback(
    (device, channel) => viewerLoad(path, { channel: `${device}/${channel}` }),
    [path],
  );

  async function openSomethingElse() {
    const picked = await pickFile({
      title: 'Open a forged output to review',
      filters: OPEN_FILTERS,
      startDir: lastFolder('viewerOpen') || project?.output?.folder || null,
    });
    if (!picked) return;
    rememberFileFolder('viewerOpen', picked);
    setPath(picked);
  }

  const openButton = (
    <Button kind="ghost" size="sm" icon="folder-open" onClick={openSomethingElse}>
      Open output…
    </Button>
  );

  if (!path || (!loading && (!data || !data.available))) {
    return (
      <FATabBody>
        <FATabHeader
          eyebrow="Review"
          title="Viewer"
          subtitle="Read back what the forge wrote — every channel of one device across the whole timeline, against the video it belongs to."
        />
        <div style={{ padding: '18px 0', maxWidth: 620 }}>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6, margin: 0 }}>
            {!path
              ? 'Nothing to review yet. Forge this compilation on the Forge tab, then come back — or open a forged output from anywhere.'
              : 'No forged output found there. The Viewer reads the funscripts a forge wrote: the .forge scene, or the channel files beside the video.'}
          </p>
          {path && (
            <p className="mono" style={{ marginTop: 12, fontSize: 11, color: 'var(--text-dim)',
                                          wordBreak: 'break-all' }}>
              Looked in: {path}
            </p>
          )}
          {(err || data?.error) && (
            <p className="mono" style={{ marginTop: 6, fontSize: 11, color: 'var(--text-dim)' }}>
              {err ? `load error: ${err}` : `reason: ${data.error}`}
            </p>
          )}
          <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
            {openButton}
            {path && (
              <Button kind="ghost" size="sm" icon="folder"
                      onClick={() => revealPath(path).catch(() => {})}>
                Show in folder
              </Button>
            )}
          </div>
        </div>
      </FATabBody>
    );
  }

  if (loading) {
    return (
      <FATabBody>
        <FATabHeader eyebrow="Review" title="Viewer" subtitle="Reading the forged output…" />
      </FATabBody>
    );
  }

  return (
    <ViewerPanel
      devices={data.devices || []}
      durationMs={data.durationMs || 0}
      chapters={data.chapters || []}
      audio={data.audio || null}
      beats={data.beats || null}
      mediaUrl={toMediaUrl(data.mediaPath)}
      mediaTitle={data.sourceName || project?.name || 'Forged output'}
      loadChannel={loadChannel}
      headerExtra={openButton}
      source={{
        label: data.source === 'forge' ? 'Scene' : 'Output',
        name: data.sourceName,
        path: data.sourcePath,
        // The strip named the artifact but did nothing with it. A `.forge`
        // scene is registered to ForgePlayer, so opening it is one click from
        // reviewing it -- and the box-and-arrow goes to the folder, which is
        // where the funscripts and station folders are.
        onOpen: data.sourcePath
          ? () => { openPath(data.sourcePath).catch(() => {}); }
          : null,
        onReveal: data.sourcePath
          ? () => { revealPath(data.sourcePath).catch(() => {}); }
          : null,
      }}
    />
  );
}

Object.assign(window, { ViewerTab });
