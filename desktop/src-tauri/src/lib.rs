use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::Command;
use tauri::{AppHandle, Manager};

const NO_SUPPORTED_PYTHON_MESSAGE: &str =
    "未找到受支持的 Python 版本。请安装 Python 3.10-3.12，推荐 Python 3.12。";

#[derive(Debug, Serialize, Deserialize)]
struct CommandResult {
    ok: bool,
    status: String,
    pid: Option<u32>,
    port: Option<u16>,
    url: Option<String>,
    message: Option<String>,
    error: Option<String>,
    #[serde(default)]
    lines: Vec<String>,
}

#[derive(Debug, Serialize)]
struct UiResult {
    ok: bool,
    message: String,
}

#[tauri::command]
fn service_status(app: AppHandle) -> Result<CommandResult, String> {
    run_service(&app, &["status"])
}

#[tauri::command]
fn service_start(app: AppHandle) -> Result<CommandResult, String> {
    run_service(&app, &["start"])
}

#[tauri::command]
fn service_stop(app: AppHandle) -> Result<CommandResult, String> {
    run_service(&app, &["stop"])
}

#[tauri::command]
fn service_logs(app: AppHandle, lines: Option<u32>) -> Result<CommandResult, String> {
    let line_count = lines.unwrap_or(120).to_string();
    run_service(&app, &["logs", "--lines", &line_count])
}

#[tauri::command]
fn open_review_ui(app: AppHandle) -> Result<UiResult, String> {
    let status = run_service(&app, &["status"])?;
    let url = match (status.status.as_str(), status.url.as_deref()) {
        ("running", Some(url)) => url,
        _ => return Err("请先启动服务".to_string()),
    };
    open_path_or_url(url)?;
    Ok(UiResult {
        ok: true,
        message: format!("已打开复核界面：{url}"),
    })
}

#[tauri::command]
fn open_data_dir(app: AppHandle) -> Result<UiResult, String> {
    open_project_dir(&app, "data", "data 目录")
}

#[tauri::command]
fn open_exports_dir(app: AppHandle) -> Result<UiResult, String> {
    open_project_dir(&app, "exports", "exports 目录")
}

#[tauri::command]
fn open_logs_dir(app: AppHandle) -> Result<UiResult, String> {
    open_project_dir(&app, "logs", "logs 目录")
}

fn run_service(app: &AppHandle, args: &[&str]) -> Result<CommandResult, String> {
    let root = project_root(app)?;
    let script = root.join("scripts").join("desktop_service.py");
    if !script.exists() {
        return Err("缺少 scripts/desktop_service.py，请确认桌面发布包完整。".to_string());
    }

    let mut launch_errors: Vec<String> = Vec::new();
    for candidate in python_command_candidates(app, &root) {
        let mut command = Command::new(&candidate.program);
        command
            .args(&candidate.args)
            .arg(&script)
            .args(args)
            .arg("--root")
            .arg(&root)
            .env("PYTHONIOENCODING", "utf-8");

        let output = match command.output() {
            Ok(output) => output,
            Err(err) => {
                launch_errors.push(format!("{}：{err}", candidate.display()));
                continue;
            }
        };

        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();

        if stdout.is_empty() {
            launch_errors.push(if stderr.is_empty() {
                format!("{}：服务脚本没有返回任何输出。", candidate.display())
            } else {
                format!("{}：{stderr}", candidate.display())
            });
            continue;
        }

        return parse_service_output(output.status.success(), &stdout, &stderr);
    }

    if launch_errors.is_empty() {
        Err(NO_SUPPORTED_PYTHON_MESSAGE.to_string())
    } else {
        Err(format!(
            "{NO_SUPPORTED_PYTHON_MESSAGE}\n检测结果：{}",
            launch_errors.join("；")
        ))
    }
}

fn parse_service_output(success: bool, stdout: &str, stderr: &str) -> Result<CommandResult, String> {
    let value: Value = serde_json::from_str(stdout)
        .map_err(|err| format!("服务脚本返回的 JSON 无法解析：{err}。输出：{stdout}"))?;
    let result: CommandResult = serde_json::from_value(value)
        .map_err(|err| format!("服务脚本返回结构不正确：{err}。输出：{stdout}"))?;

    if success && result.ok {
        Ok(result)
    } else {
        let message = result
            .error
            .as_deref()
            .or(result.message.as_deref())
            .filter(|text| !text.is_empty())
            .unwrap_or("服务脚本执行失败");
        let detail = if stderr.is_empty() {
            message.to_string()
        } else {
            format!("{message}\n{stderr}")
        };
        Err(detail)
    }
}

fn open_project_dir(app: &AppHandle, name: &str, label: &str) -> Result<UiResult, String> {
    let path = project_root(app)?.join(name);
    std::fs::create_dir_all(&path).map_err(|err| format!("无法创建{label}：{err}"))?;
    open_path_or_url(&path)?;
    Ok(UiResult {
        ok: true,
        message: format!("已打开{label}：{}", path.display()),
    })
}

fn project_root(app: &AppHandle) -> Result<PathBuf, String> {
    if let Ok(path) = app.path().resolve("LegalFactReview", tauri::path::BaseDirectory::Resource) {
        if path.join("scripts").join("desktop_service.py").exists() {
            return Ok(path);
        }
    }
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .ok_or_else(|| "无法定位项目根目录。".to_string())
}

#[derive(Clone)]
struct PythonCommand {
    program: String,
    args: Vec<String>,
}

impl PythonCommand {
    fn display(&self) -> String {
        if self.args.is_empty() {
            self.program.clone()
        } else {
            format!("{} {}", self.program, self.args.join(" "))
        }
    }
}

fn python_command_candidates(app: &AppHandle, root: &Path) -> Vec<PythonCommand> {
    let mut candidates = Vec::new();
    for path in bundled_python_candidates(app, root) {
        if path.exists() {
            candidates.push(PythonCommand {
                program: path.display().to_string(),
                args: vec![],
            });
        }
    }
    if cfg!(windows) {
        candidates.extend([
            PythonCommand {
                program: "py".to_string(),
                args: vec!["-3.12".to_string()],
            },
            PythonCommand {
                program: "py".to_string(),
                args: vec!["-3.11".to_string()],
            },
            PythonCommand {
                program: "py".to_string(),
                args: vec!["-3.10".to_string()],
            },
            PythonCommand {
                program: "python".to_string(),
                args: vec![],
            },
        ]);
    } else {
        candidates.extend([
            PythonCommand {
                program: "python3.12".to_string(),
                args: vec![],
            },
            PythonCommand {
                program: "python3.11".to_string(),
                args: vec![],
            },
            PythonCommand {
                program: "python3.10".to_string(),
                args: vec![],
            },
            PythonCommand {
                program: "python3".to_string(),
                args: vec![],
            },
        ]);
    }
    candidates
}

fn bundled_python_candidates(app: &AppHandle, root: &Path) -> Vec<PathBuf> {
    let mut paths = Vec::new();
    if let Ok(path) = app.path().resolve("python/python.exe", tauri::path::BaseDirectory::Resource) {
        paths.push(path);
    }
    paths.push(root.join("python").join("python.exe"));
    paths.push(root.parent().unwrap_or(root).join("python").join("python.exe"));
    paths
}

fn open_path_or_url<T: AsRef<std::ffi::OsStr>>(target: T) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        Command::new("explorer")
            .arg(target)
            .spawn()
            .map_err(|err| format!("打开失败：{err}"))?;
    }
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(target)
            .spawn()
            .map_err(|err| format!("打开失败：{err}"))?;
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        Command::new("xdg-open")
            .arg(target)
            .spawn()
            .map_err(|err| format!("打开失败：{err}"))?;
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
            open_review_ui,
            open_data_dir,
            open_exports_dir,
            open_logs_dir
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
