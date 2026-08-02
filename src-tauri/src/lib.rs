use serde_json::Value;
use std::{fs, io::Write, path::PathBuf, process::{Command, Stdio}};
use tauri::Manager;

const PROJECT_DIRECTORIES: [&str; 7] = ["sources/templates", "sources/glyphs/regular", "vectors/regular", "templates", "previews", "generated/regular", "validation"];

fn project_file(root: &str) -> Result<PathBuf, String> {
    let root = PathBuf::from(root);
    if !root.is_absolute() { return Err("Project path must be absolute".into()); }
    Ok(root.join("project.json"))
}

fn write_project(path: &str, project: &Value) -> Result<(), String> {
    let destination = project_file(path)?;
    let bytes = serde_json::to_vec_pretty(project).map_err(|e| e.to_string())?;
    let temporary = destination.with_extension("json.tmp");
    fs::write(&temporary, bytes).map_err(|e| e.to_string())?;
    fs::rename(temporary, destination).map_err(|e| e.to_string())
}

#[tauri::command]
fn create_project(path: String, project: Value) -> Result<(), String> {
    let root = PathBuf::from(&path);
    fs::create_dir_all(&root).map_err(|e| e.to_string())?;
    if project_file(&path)?.exists() { return Err("This folder already contains a project.json file".into()); }
    for directory in PROJECT_DIRECTORIES { fs::create_dir_all(root.join(directory)).map_err(|e| e.to_string())?; }
    write_project(&path, &project)
}

#[tauri::command]
fn save_project(path: String, project: Value) -> Result<(), String> { write_project(&path, &project) }

#[tauri::command]
fn load_project(path: String) -> Result<Value, String> {
    let source = project_file(&path)?;
    if !source.is_file() { return Err("The selected folder does not contain project.json".into()); }
    let contents = fs::read_to_string(source).map_err(|e| format!("Could not read project.json: {e}"))?;
    let project: Value = serde_json::from_str(&contents).map_err(|e| format!("project.json is invalid: {e}"))?;
    let object = project.as_object().ok_or("project.json must contain a JSON object")?;
    for field in ["schemaVersion", "id", "familyName", "styles"] {
        if !object.contains_key(field) { return Err(format!("project.json is missing the required field '{field}'")); }
    }
    if project["schemaVersion"] != 1 { return Err(format!("Unsupported project schema version: {}", project["schemaVersion"])); }
    Ok(project)
}

fn compiler_command(app: &tauri::AppHandle) -> Result<(PathBuf, Vec<String>, Option<PathBuf>), String> {
    let executable_name = if cfg!(windows) { "handfont-compiler.exe" } else { "handfont-compiler" };
    let resource_compiler = app.path().resource_dir().map_err(|error| error.to_string())?
        .join("compiler").join(executable_name);
    if resource_compiler.is_file() { return Ok((resource_compiler, Vec::new(), None)); }

    let portable_compiler = std::env::current_exe().map_err(|error| error.to_string())?
        .parent().ok_or("Could not resolve the application folder")?
        .join("compiler").join(executable_name);
    if portable_compiler.is_file() { return Ok((portable_compiler, Vec::new(), None)); }

    let compiler_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("compiler");
    let python = compiler_root.join(".venv").join("Scripts").join("python.exe");
    if python.is_file() {
        return Ok((python, vec!["-m".into(), "handfont_compiler".into()], Some(compiler_root)));
    }
    Err("The bundled font compiler could not be found. Reinstall the app or use the complete portable folder.".into())
}

fn run_compiler_blocking(app: tauri::AppHandle, request: Value) -> Result<Value, String> {
    let (program, arguments, working_directory) = compiler_command(&app)?;
    let mut command = Command::new(program);
    command.args(arguments);
    if let Some(directory) = working_directory { command.current_dir(directory); }
    let mut child = command
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped())
        .spawn().map_err(|e| format!("Could not start the local compiler: {e}"))?;
    let input = serde_json::to_vec(&request).map_err(|e| e.to_string())?;
    child.stdin.as_mut().ok_or("Could not open compiler input")?.write_all(&input).map_err(|e| e.to_string())?;
    let output = child.wait_with_output().map_err(|e| e.to_string())?;
    let result: Value = serde_json::from_slice(&output.stdout).map_err(|_| {
        let error = String::from_utf8_lossy(&output.stderr);
        format!("The compiler returned an invalid response: {error}")
    })?;
    Ok(result)
}

#[tauri::command]
async fn run_compiler(app: tauri::AppHandle, request: Value) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || run_compiler_blocking(app, request))
        .await
        .map_err(|error| format!("The compiler worker stopped unexpectedly: {error}"))?
}

#[tauri::command]
fn read_project_binary(project_path: String, file_path: String) -> Result<Vec<u8>, String> {
    let root = PathBuf::from(project_path).canonicalize().map_err(|e| format!("Could not resolve project folder: {e}"))?;
    let file = PathBuf::from(file_path).canonicalize().map_err(|e| format!("Could not resolve generated file: {e}"))?;
    if !file.starts_with(&root) { return Err("Generated file is outside the current project".into()); }
    fs::read(file).map_err(|e| format!("Could not read generated font: {e}"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![create_project, load_project, read_project_binary, run_compiler, save_project])
        .run(tauri::generate_context!())
        .expect("error while running Handfont");
}
