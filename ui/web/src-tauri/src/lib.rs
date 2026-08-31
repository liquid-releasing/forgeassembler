mod commands;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            // Resolve the Python backend once: bundled forge-cli resource in a
            // packaged build, else the dev .venv + cli.py.
            commands::init_cli_invocation(app.handle());
            #[cfg(debug_assertions)]
            {
                use tauri::Manager;
                if let Some(window) = app.get_webview_window("main") {
                    window.open_devtools();
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::ping,
            commands::list_joiners,
            commands::detect_folder,
            commands::import_forge_bundle,
            commands::validate_project,
            commands::forge_project,
            commands::load_project,
            commands::save_project,
            commands::read_sidecar,
            commands::probe_duration,
            commands::extract_thumbnail,
            commands::pick_folder,
            commands::pick_file,
            commands::pick_save_path,
            commands::reveal_path,
            commands::open_external,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
