// Tauri commands — the Rust side of ForgeAssembler's platform adapter.
//
// Bridge strategy (cloned from FunscriptForge): spawn-per-call to the
// ForgeAssembler Python CLI (`cli.py`), capture JSON from stdout, return to
// React. The long-running `forge` command streams progress via a temp file
// that a parallel poller tails and re-emits as `fa:progress` Tauri events.
//
// Resolution: a packaged build uses the bundled `forge-cli` PyInstaller onedir
// + bundled ffmpeg; the dev loop falls back to the repo `.venv` + cli.py.

use serde::Serialize;
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Mutex, OnceLock};
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_dialog::DialogExt;
use tokio::process::Command;

// ---------------------------------------------------------------------------
// Cancelling a forge
// ---------------------------------------------------------------------------
//
// A forge is a two-hour job. It has to be stoppable, and stopping it is not
// as simple as dropping the future: `Command::output()` used to own the whole
// run, so there was no child to reach and nothing to kill. We spawn and keep
// the pid instead.
//
// The pid we keep is the CLI's -- Python. ffmpeg is its child, a separate
// process, which is why killing Python alone is not enough: measured twice in
// one session, ffmpeg's pid changed between forge stages while Python's did
// not. An orphaned ffmpeg keeps writing, and two writers on one output path
// is how you get a multi-gigabyte file that will not play.
static FORGE_PID: Mutex<Option<u32>> = Mutex::new(None);

// Set by `cancel_forge`, read by the runner when the child exits non-zero.
// Without it a cancel is indistinguishable from a crash, and the user gets
// "Forge failed" for something they chose to do.
static CANCEL_REQUESTED: AtomicBool = AtomicBool::new(false);

/// The sentinel `forge_project` returns when the run was deliberately stopped.
pub const CANCELLED: &str = "cancelled";

#[derive(Serialize)]
pub struct Pong {
    runtime: &'static str,
    version: &'static str,
}

#[tauri::command]
pub fn ping() -> Pong {
    Pong {
        runtime: "tauri",
        version: env!("CARGO_PKG_VERSION"),
    }
}

// ---------------------------------------------------------------------------
// CLI invocation resolution
// ---------------------------------------------------------------------------

const DEV_FORGEASSEMBLER_ROOT: &str = r"C:\Users\bruce\Projects\_lqr\forgeassembler";

struct CliInvocation {
    program: PathBuf,
    prefix_args: Vec<String>,
    cwd: PathBuf,
    extra_path: Option<PathBuf>,
}

static CLI: OnceLock<CliInvocation> = OnceLock::new();

fn dev_cli_invocation() -> CliInvocation {
    let root = std::env::var("FORGEASSEMBLER_ROOT")
        .unwrap_or_else(|_| DEV_FORGEASSEMBLER_ROOT.to_string());
    // Prefer an explicit override, then the repo's own `.venv`, then whatever
    // `python` resolves to on PATH (this repo has no committed .venv, so the
    // dev loop relies on the active interpreter on PATH).
    let python = std::env::var("FORGEASSEMBLER_PYTHON").unwrap_or_else(|_| {
        let venv = format!(r"{}\.venv\Scripts\python.exe", root);
        if std::path::Path::new(&venv).is_file() { venv } else { "python".to_string() }
    });
    CliInvocation {
        program: PathBuf::from(python),
        prefix_args: vec![format!(r"{}\cli.py", root)],
        cwd: PathBuf::from(&root),
        extra_path: None,
    }
}

/// Prefer a bundled `forge-cli` resource (production); fall back to the dev
/// `.venv` python + cli.py. Called once from lib.rs `setup()`.
pub fn init_cli_invocation(app: &AppHandle) {
    let resolved = (|| {
        let res = app.path().resource_dir().ok()?;
        let dir = res.join("forge-cli");
        let exe = dir.join(if cfg!(windows) { "forge-cli.exe" } else { "forge-cli" });
        if !exe.is_file() {
            return None;
        }
        let ffmpeg = res.join("ffmpeg");
        Some(CliInvocation {
            program: exe,
            prefix_args: vec![],
            cwd: dir,
            extra_path: ffmpeg.is_dir().then_some(ffmpeg),
        })
    })()
    .unwrap_or_else(dev_cli_invocation);
    let _ = CLI.set(resolved);
}

fn cli_invocation() -> &'static CliInvocation {
    CLI.get_or_init(dev_cli_invocation)
}

fn cli_command(args: &[&str]) -> Command {
    let inv = cli_invocation();
    let mut cmd = Command::new(&inv.program);
    cmd.args(&inv.prefix_args);
    for a in args {
        cmd.arg(a);
    }
    cmd.current_dir(&inv.cwd);
    if let Some(dir) = &inv.extra_path {
        // Prepend the bundled ffmpeg dir to PATH (the engine shells ffmpeg/ffprobe).
        let sep = if cfg!(windows) { ";" } else { ":" };
        let existing = std::env::var("PATH").unwrap_or_default();
        cmd.env("PATH", format!("{}{}{}", dir.display(), sep, existing));
    }
    cmd
}

// Generic backend runner: runs `<backend> <args…>`, returns stdout. Non-zero
// exits surface stderr in the error.
async fn run_cli(args: &[&str]) -> Result<String, String> {
    let output = cli_command(args)
        .output()
        .await
        .map_err(|e| format!("spawn forge-cli failed: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "cli {} exited non-zero: {}",
            args.first().unwrap_or(&""),
            stderr
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

// Run a CLI subcommand whose stdout is JSON; parse and return the Value.
async fn run_cli_json(args: &[&str]) -> Result<Value, String> {
    let stdout = run_cli(args).await?;
    serde_json::from_str(&stdout)
        .map_err(|e| format!("could not parse cli output for {:?}: {}", args.first(), e))
}

// Streaming variant: spawns the CLI with FORGEASSEMBLER_PROGRESS_FILE set to a
// unique temp path, and runs a parallel poller that tails the file, emitting
// each new line as a `fa:progress` Tauri event for the footer. Returns stdout
// once the process exits, exactly like run_cli.
async fn run_cli_with_progress(
    app: &AppHandle,
    event_name: &str,
    args: &[&str],
) -> Result<String, String> {
    let pid = std::process::id();
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_micros())
        .unwrap_or(0);
    let temp_path: PathBuf = std::env::temp_dir().join(format!("fa-progress-{}-{}.log", pid, ts));
    let _ = std::fs::write(&temp_path, "");

    let mut cmd = cli_command(args);
    cmd.env("FORGEASSEMBLER_PROGRESS_FILE", &temp_path);

    let (cancel_tx, mut cancel_rx) = tokio::sync::oneshot::channel::<()>();
    let app_for_task = app.clone();
    let event_name_owned = event_name.to_string();
    let temp_path_for_task = temp_path.clone();
    let polling = tokio::spawn(async move {
        let mut offset: usize = 0;
        let drain = |offset: &mut usize| {
            if let Ok(data) = std::fs::read(&temp_path_for_task) {
                if data.len() > *offset {
                    let new_text = String::from_utf8_lossy(&data[*offset..]);
                    for line in new_text.lines() {
                        let line = line.trim();
                        if !line.is_empty() {
                            let _ = app_for_task.emit(&event_name_owned, line.to_string());
                        }
                    }
                    *offset = data.len();
                }
            }
        };
        loop {
            drain(&mut offset);
            tokio::select! {
                _ = &mut cancel_rx => break,
                _ = tokio::time::sleep(std::time::Duration::from_millis(150)) => {},
            }
        }
        drain(&mut offset);
    });

    // Cleared BEFORE the spawn, not after: a cancel arriving in the gap
    // would otherwise be wiped and the user's click would do nothing.
    CANCEL_REQUESTED.store(false, Ordering::SeqCst);

    // `spawn` rather than `output` so there is a child to cancel. `output`
    // pipes both streams for you; `spawn` does not, and `wait_with_output`
    // returns empty stderr without this -- which would silently cost us
    // ffmpeg's own words on every failure.
    let child = cmd
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| format!("spawn forge-cli failed: {}", e))?;

    if let Some(pid) = child.id() {
        *FORGE_PID.lock().unwrap() = Some(pid);
    }

    let waited = child.wait_with_output().await;

    // Whatever happened, this forge is over: nothing may be left pointing at
    // a pid the OS is free to reissue to an unrelated process.
    *FORGE_PID.lock().unwrap() = None;

    let _ = cancel_tx.send(());
    let _ = polling.await;
    let _ = tokio::fs::remove_file(&temp_path).await;

    let output = waited.map_err(|e| format!("forge-cli failed: {}", e))?;

    if !output.status.success() {
        // A killed child exits non-zero, so this is the only place that can
        // tell a cancel from a crash.
        if CANCEL_REQUESTED.swap(false, Ordering::SeqCst) {
            return Err(CANCELLED.to_string());
        }
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "cli {} exited non-zero: {}",
            args.first().unwrap_or(&""),
            stderr
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

/// Stop the forge in flight. Returns false when there was nothing to stop.
///
/// Kills the process TREE. The CLI is Python and ffmpeg is its child, so
/// killing the pid alone leaves ffmpeg running against the output path --
/// the failure that once produced a 5.33GB file with no moov atom.
#[tauri::command]
pub async fn cancel_forge() -> Result<bool, String> {
    // Copy the pid out and drop the guard: a std Mutex guard must not be
    // held across an await.
    let pid = { *FORGE_PID.lock().unwrap() };
    let Some(pid) = pid else {
        return Ok(false);
    };

    // Set BEFORE the kill, so the runner -- which may wake the instant the
    // child dies -- cannot read it as a crash.
    CANCEL_REQUESTED.store(true, Ordering::SeqCst);

    #[cfg(windows)]
    let killed = Command::new("taskkill")
        .args(["/T", "/F", "/PID", &pid.to_string()])
        .output()
        .await
        .map(|o| o.status.success())
        .map_err(|e| format!("taskkill {}: {}", pid, e))?;

    // `pkill -P` first so ffmpeg goes before the parent that would otherwise
    // be gone and leave it reparented to init.
    #[cfg(not(windows))]
    let killed = Command::new("/bin/sh")
        .arg("-c")
        .arg(format!("pkill -TERM -P {pid}; kill -TERM {pid}"))
        .output()
        .await
        .map(|o| o.status.success())
        .map_err(|e| format!("kill {}: {}", pid, e))?;

    if !killed {
        // The process was already gone -- it finished while the click was in
        // flight. Not an error, but the forge was not cancelled either.
        CANCEL_REQUESTED.store(false, Ordering::SeqCst);
    }
    Ok(killed)
}

// ---------------------------------------------------------------------------
// CLI-backed commands
// ---------------------------------------------------------------------------

/// List available joiner types (`cli.py list-joiners --format json`).
#[tauri::command]
pub async fn list_joiners() -> Result<Value, String> {
    run_cli_json(&["list-joiners", "--format", "json"]).await
}

/// Auto-detect clips + funscripts + audio-estim in a folder
/// (`cli.py detect <folder> --format json`).
#[tauri::command]
pub async fn detect_folder(path: String) -> Result<Value, String> {
    run_cli_json(&["detect", &path, "--format", "json"]).await
}

/// Report the video encoder this machine will use, plus rough throughput
/// (`cli.py encoder --format json`), so the Forge tab can estimate time
/// from the real hardware instead of a fixed guess.
#[tauri::command]
pub async fn video_encoder() -> Result<Value, String> {
    run_cli_json(&["encoder", "--format", "json"]).await
}

/// List the `.forge` scenes in a folder (`cli.py detect-forge <folder>
/// --format json`). Shallow — no bundle is opened — so "Add folder" can
/// show what it found before importing any of them.
#[tauri::command]
pub async fn detect_forge_folder(path: String) -> Result<Value, String> {
    run_cli_json(&["detect-forge", &path, "--format", "json"]).await
}

/// Import a FunscriptForge `.forge` bundle as one Segment
/// (`cli.py import-forge <bundle> [--video PATH] --format json`). Returns the
/// channel map + (when relinkable) the Segment dict to append.
#[tauri::command]
pub async fn import_forge_bundle(bundle: String, video: Option<String>) -> Result<Value, String> {
    let mut args: Vec<String> = vec![
        "import-forge".into(), bundle, "--format".into(), "json".into(),
    ];
    if let Some(v) = video {
        args.push("--video".into());
        args.push(v);
    }
    let refs: Vec<&str> = args.iter().map(|s| s.as_str()).collect();
    run_cli_json(&refs).await
}

/// Validate a saved project without forging (`cli.py validate <project> --format json`).
#[tauri::command]
pub async fn validate_project(path: String) -> Result<Value, String> {
    run_cli_json(&["validate", &path, "--format", "json"]).await
}

/// Probe a media file's duration in milliseconds (`cli.py probe <video>`).
#[tauri::command]
pub async fn probe_duration(path: String) -> Result<i64, String> {
    let stdout = run_cli(&["probe", &path]).await?;
    stdout
        .trim()
        .parse::<i64>()
        .map_err(|e| format!("probe parse failed for {}: {}", path, e))
}

/// Duration AND frame rate: `{"duration_ms": N, "fps": F|null}`.
///
/// The Forge summary needs the frame rate to resolve a project set to
/// `source`, so it can name the file the forge will actually write rather
/// than one without a render tag.
#[tauri::command]
pub async fn probe_media(path: String) -> Result<Value, String> {
    run_cli_json(&["probe", &path, "--format", "json"]).await
}

/// Read back what a forge WROTE, for the Viewer tab (`cli.py viewer-load`).
/// `input` is whatever the user opened: the forged video, its `.forge`
/// bundle, the `.forgeproject`, or the output folder. With `channel` set to
/// `"<device>/<channel>"` it returns that one channel at full resolution
/// instead -- the monitor windows to a few seconds, where the timeline's
/// peak-preserving envelope is the wrong shape.
#[tauri::command]
pub async fn viewer_load(
    input: String,
    max_points: Option<i64>,
    audio_points: Option<i64>,
    channel: Option<String>,
) -> Result<Value, String> {
    let mp = max_points.unwrap_or(2000).to_string();
    let ap = audio_points.unwrap_or(16000).to_string();
    let mut args: Vec<&str> = vec![
        "viewer-load",
        &input,
        "--max-points",
        &mp,
        "--audio-points",
        &ap,
    ];
    if let Some(c) = channel.as_deref() {
        args.push("--channel");
        args.push(c);
    }
    run_cli_json(&args).await
}

/// The title layouts, themes and marks this build can render
/// (`cli.py title-catalog`).
#[tauri::command]
pub async fn title_catalog() -> Result<Value, String> {
    run_cli_json(&["title-catalog"]).await
}

/// Render one title card to a PNG (`cli.py title-preview`). `spec` is the
/// joiner's params as a JSON string -- the same dict the project file
/// holds, so the preview cannot read the settings differently from the
/// forge. Returns the CLI's JSON: the path written, the size, and the
/// colour the bridge behind the card will be painted.
#[tauri::command]
pub async fn title_preview(
    spec: String,
    out: String,
    width: i64,
    height: i64,
    over_frame: bool,
) -> Result<Value, String> {
    let w = width.to_string();
    let h = height.to_string();
    let mut args = vec![
        "title-preview",
        "--spec",
        &spec,
        "--out",
        &out,
        "--width",
        &w,
        "--height",
        &h,
    ];
    if over_frame {
        args.push("--over-frame");
    }
    run_cli_json(&args).await
}

/// Extract a thumbnail PNG from a video at a timestamp
/// (`cli.py thumbnail <video> --at <ms> --out <png>`). Returns the PNG path.
#[tauri::command]
pub async fn extract_thumbnail(video: String, at_ms: i64, out: String) -> Result<String, String> {
    let at = at_ms.to_string();
    run_cli(&["thumbnail", &video, "--at", &at, "--out", &out]).await?;
    Ok(out)
}

/// Forge a saved project. Streams stage lines as `fa:progress` events; resolves
/// with the CLI's stdout (a JSON summary of written outputs) when done.
#[tauri::command]
pub async fn forge_project(
    app: AppHandle,
    project_path: String,
    output: Option<String>,
    basename: Option<String>,
) -> Result<String, String> {
    let mut args: Vec<String> = vec!["forge".into(), project_path];
    if let Some(o) = output {
        args.push("--output".into());
        args.push(o);
    }
    if let Some(b) = basename {
        args.push("--basename".into());
        args.push(b);
    }
    let arg_refs: Vec<&str> = args.iter().map(|s| s.as_str()).collect();
    run_cli_with_progress(&app, "fa:progress", &arg_refs).await
}

// ---------------------------------------------------------------------------
// Direct file I/O — the project sidecar is plain JSON, no Python needed
// ---------------------------------------------------------------------------

/// Read a `.forgeproject.json` from disk and return its parsed contents.
#[tauri::command]
pub async fn load_project(path: String) -> Result<Value, String> {
    let raw = tokio::fs::read_to_string(&path)
        .await
        .map_err(|e| format!("read {}: {}", path, e))?;
    serde_json::from_str(&raw).map_err(|e| format!("parse {}: {}", path, e))
}

/// Summarise the COMBINED funscript for the Build tab's live strip
/// (`cli.py preview <project.json> --channel <ch>`).
///
/// Takes the project object rather than a path: the strip has to describe
/// what the user is editing right now, including edits not yet saved. The
/// project is written to a temp file for the CLI and removed afterwards.
#[tauri::command]
pub async fn preview_project(project: Value, channel: Option<String>) -> Result<Value, String> {
    let pid = std::process::id();
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_micros())
        .unwrap_or(0);
    let temp: PathBuf = std::env::temp_dir().join(format!("fa-preview-{}-{}.json", pid, ts));
    let text =
        serde_json::to_string(&project).map_err(|e| format!("serialize project: {}", e))?;
    tokio::fs::write(&temp, text)
        .await
        .map_err(|e| format!("write preview project: {}", e))?;

    let ch = channel.unwrap_or_else(|| "main".to_string());
    let out = run_cli_json(&["preview", &temp.to_string_lossy(), "--channel", &ch]).await;
    let _ = tokio::fs::remove_file(&temp).await;
    out
}

/// Read one analysis sidecar (`audio.json`, `beats.json`, `chapters.json`, …)
/// that a `.forge` bundle carried, from the bundle's extraction cache.
///
/// Returns `None` rather than erroring when the file is absent: a lean bundle
/// legitimately has no sidecars, and the preview falls back to deriving what
/// it needs from the video. Only a present-but-unreadable file is an error
/// worth surfacing.
#[tauri::command]
pub async fn read_sidecar(path: String) -> Result<Option<Value>, String> {
    if !Path::new(&path).is_file() {
        return Ok(None);
    }
    let raw = tokio::fs::read_to_string(&path)
        .await
        .map_err(|e| format!("read sidecar {}: {}", path, e))?;
    serde_json::from_str(&raw)
        .map(Some)
        .map_err(|e| format!("parse sidecar {}: {}", path, e))
}

/// Write a project object to disk as pretty-printed JSON.
#[tauri::command]
pub async fn save_project(path: String, project: Value) -> Result<(), String> {
    let text =
        serde_json::to_string_pretty(&project).map_err(|e| format!("serialize project: {}", e))?;
    if let Some(parent) = Path::new(&path).parent() {
        let _ = tokio::fs::create_dir_all(parent).await;
    }
    tokio::fs::write(&path, text)
        .await
        .map_err(|e| format!("write {}: {}", path, e))
}

// ---------------------------------------------------------------------------
// Native dialogs
// ---------------------------------------------------------------------------

/// Open a dialog at `dir`, but only when it is still a directory.
///
/// A remembered folder can be on a drive that is not attached -- this
/// project's media lives across D: and E: -- and handing a dead path to
/// the native dialog is how you get a picker that opens at nothing.
/// Checking costs one stat and otherwise falls back to the OS default,
/// which is exactly the behaviour these pickers had before.
fn with_start_dir<R: tauri::Runtime>(
    builder: tauri_plugin_dialog::FileDialogBuilder<R>,
    dir: Option<&str>,
) -> tauri_plugin_dialog::FileDialogBuilder<R> {
    match dir {
        Some(d) if !d.is_empty() && Path::new(d).is_dir() => builder.set_directory(d),
        _ => builder,
    }
}

#[tauri::command]
pub async fn pick_folder(
    app: AppHandle,
    start_dir: Option<String>,
) -> Result<Option<String>, String> {
    let builder = with_start_dir(app.dialog().file(), start_dir.as_deref());
    let folder = builder.blocking_pick_folder();
    Ok(folder.map(|p| p.to_string()))
}

/// One entry in a file dialog's type dropdown.
#[derive(serde::Deserialize)]
pub struct DialogFilter {
    pub name: String,
    pub extensions: Vec<String>,
}

/// Apply `filters` in order. The first becomes the dialog's default, so
/// the caller's preferred type is the one the user sees first.
fn with_filters<R: tauri::Runtime>(
    mut builder: tauri_plugin_dialog::FileDialogBuilder<R>,
    filters: Option<&Vec<DialogFilter>>,
) -> tauri_plugin_dialog::FileDialogBuilder<R> {
    if let Some(list) = filters {
        for f in list {
            let refs: Vec<&str> = f.extensions.iter().map(|s| s.as_str()).collect();
            builder = builder.add_filter(&f.name, &refs);
        }
    }
    builder
}

#[tauri::command]
pub async fn pick_file(
    app: AppHandle,
    title: Option<String>,
    filter_name: Option<String>,
    extensions: Option<Vec<String>>,
    filters: Option<Vec<DialogFilter>>,
    start_dir: Option<String>,
) -> Result<Option<String>, String> {
    let mut builder = with_start_dir(app.dialog().file(), start_dir.as_deref());
    if let Some(t) = title.as_deref() {
        builder = builder.set_title(t);
    }
    // The single-filter form is still here: most callers want one type,
    // and rewriting them to a list would be churn for its own sake.
    if let (Some(name), Some(exts)) = (filter_name.as_deref(), extensions.as_ref()) {
        let refs: Vec<&str> = exts.iter().map(|s| s.as_str()).collect();
        builder = builder.add_filter(name, &refs);
    }
    builder = with_filters(builder, filters.as_ref());
    let file = builder.blocking_pick_file();
    Ok(file.map(|p| p.to_string()))
}

#[tauri::command]
pub async fn pick_save_path(
    app: AppHandle,
    default_name: Option<String>,
    filters: Option<Vec<DialogFilter>>,
    start_dir: Option<String>,
) -> Result<Option<String>, String> {
    let mut builder = with_start_dir(app.dialog().file(), start_dir.as_deref());
    if let Some(name) = default_name {
        builder = builder.set_file_name(&name);
    }
    // A filter here is not decoration: it is what makes the shell put the
    // extension back when the user types a bare name.
    builder = with_filters(builder, filters.as_ref());
    let path = builder.blocking_save_file();
    Ok(path.map(|p| p.to_string()))
}

// ---------------------------------------------------------------------------
// Shell helpers
// ---------------------------------------------------------------------------

/// Reveal a file (selected) or a folder in the OS file manager.
#[tauri::command]
pub async fn reveal_path(path: String) -> Result<(), String> {
    let p = Path::new(&path);
    #[cfg(windows)]
    {
        let mut cmd = std::process::Command::new("explorer");
        if p.is_file() {
            cmd.arg("/select,").arg(&path);
        } else {
            cmd.arg(&path);
        }
        let _ = cmd.spawn().map_err(|e| format!("reveal {}: {}", path, e))?;
    }
    #[cfg(target_os = "macos")]
    {
        let mut cmd = std::process::Command::new("open");
        if p.is_file() {
            cmd.arg("-R").arg(&path);
        } else {
            cmd.arg(&path);
        }
        let _ = cmd.spawn().map_err(|e| format!("reveal {}: {}", path, e))?;
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        let target = if p.is_file() {
            p.parent().map(|d| d.to_path_buf()).unwrap_or_else(|| p.to_path_buf())
        } else {
            p.to_path_buf()
        };
        let _ = std::process::Command::new("xdg-open")
            .arg(&target)
            .spawn()
            .map_err(|e| format!("reveal {}: {}", path, e))?;
    }
    Ok(())
}

/// Open an external http(s) URL in the user's default browser.
#[tauri::command]
pub async fn open_external(url: String) -> Result<(), String> {
    let lower = url.to_ascii_lowercase();
    if !(lower.starts_with("https://") || lower.starts_with("http://")) {
        return Err(format!("refusing to open non-http(s) url: {}", url));
    }
    #[cfg(windows)]
    let mut cmd = {
        let mut c = std::process::Command::new("rundll32");
        c.arg("url.dll,FileProtocolHandler").arg(&url);
        c
    };
    #[cfg(target_os = "macos")]
    let mut cmd = {
        let mut c = std::process::Command::new("open");
        c.arg(&url);
        c
    };
    #[cfg(all(unix, not(target_os = "macos")))]
    let mut cmd = {
        let mut c = std::process::Command::new("xdg-open");
        c.arg(&url);
        c
    };
    cmd.spawn().map_err(|e| format!("open {}: {}", url, e))?;
    Ok(())
}
