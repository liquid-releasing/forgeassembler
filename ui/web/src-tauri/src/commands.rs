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
use std::sync::OnceLock;
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_dialog::DialogExt;
use tokio::process::Command;

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

    let output = cmd
        .output()
        .await
        .map_err(|e| format!("spawn forge-cli failed: {}", e))?;

    let _ = cancel_tx.send(());
    let _ = polling.await;
    let _ = tokio::fs::remove_file(&temp_path).await;

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
// Native dialogs (replaces the pywebview HTTP folder-picker bridge)
// ---------------------------------------------------------------------------

#[tauri::command]
pub async fn pick_folder(app: AppHandle) -> Result<Option<String>, String> {
    let folder = app.dialog().file().blocking_pick_folder();
    Ok(folder.map(|p| p.to_string()))
}

#[tauri::command]
pub async fn pick_file(
    app: AppHandle,
    title: Option<String>,
    filter_name: Option<String>,
    extensions: Option<Vec<String>>,
) -> Result<Option<String>, String> {
    let mut builder = app.dialog().file();
    if let Some(t) = title.as_deref() {
        builder = builder.set_title(t);
    }
    if let (Some(name), Some(exts)) = (filter_name.as_deref(), extensions.as_ref()) {
        let refs: Vec<&str> = exts.iter().map(|s| s.as_str()).collect();
        builder = builder.add_filter(name, &refs);
    }
    let file = builder.blocking_pick_file();
    Ok(file.map(|p| p.to_string()))
}

#[tauri::command]
pub async fn pick_save_path(
    app: AppHandle,
    default_name: Option<String>,
) -> Result<Option<String>, String> {
    let mut builder = app.dialog().file();
    if let Some(name) = default_name {
        builder = builder.set_file_name(&name);
    }
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
