use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::Command;

#[tauri::command]
fn service_status() -> Result<Value, String> {
    run_service(&["status"])
}

#[tauri::command]
fn service_start() -> Result<Value, String> {
    run_service(&["start"])
}

#[tauri::command]
fn service_stop() -> Result<Value, String> {
    run_service(&["stop"])
}

#[tauri::command]
fn service_logs(lines: Option<u32>) -> Result<Value, String> {
    let line_count = lines.unwrap_or(80).to_string();
    run_service(&["logs", "--lines", &line_count])
}

#[tauri::command]
fn open_project_dir(name: String) -> Result<(), String> {
    let allowed = ["data", "exports", "logs"];
    if !allowed.contains(&name.as_str()) {
        return Err("不支持的目录。".into());
    }
    let path = project_root()?.join(name);
    std::fs::create_dir_all(&path).map_err(|err| err.to_string())?;
    open_path(&path)
}

fn run_service(args: &[&str]) -> Result<Value, String> {
    let root = project_root()?;
    let script = root.join("scripts").join("desktop_service.py");
    if !script.exists() {
        return Err("缺少 scripts/desktop_service.py。请确认桌面包完整。".into());
    }
    let python = python_command();
    let output = Command::new(python)
        .arg(script)
        .args(args)
        .arg("--root")
        .arg(root)
        .output()
        .map_err(|err| format!("无法执行 Python 服务脚本：{err}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if stdout.is_empty() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("服务脚本无输出：{stderr}"));
    }
    serde_json::from_str(&stdout).map_err(|err| format!("服务状态 JSON 解析失败：{err}: {stdout}"))
}

fn project_root() -> Result<PathBuf, String> {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .ok_or_else(|| "无法定位项目根目录。".to_string())
}

fn python_command() -> &'static str {
    if cfg!(windows) {
        "python"
    } else {
        "python3"
    }
}

fn open_path(path: &Path) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        Command::new("explorer")
            .arg(path)
            .spawn()
            .map_err(|err| err.to_string())?;
    }
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(path)
            .spawn()
            .map_err(|err| err.to_string())?;
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        Command::new("xdg-open")
            .arg(path)
            .spawn()
            .map_err(|err| err.to_string())?;
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            service_status,
            service_start,
            service_stop,
            service_logs,
            open_project_dir
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
