// Cáscara de escritorio: lanza el motor (Python), espera a que responda y muestra la interfaz que él sirve.
// No tiene lógica de producto: la interfaz y el motor son los mismos que en Linux y Docker.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    fs::{self, File},
    io::{Read, Write},
    net::{TcpListener, TcpStream},
    os::windows::{io::AsRawHandle, process::CommandExt},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    time::{Duration, Instant},
};

use tauri::{Manager, RunEvent};

const PREFERRED_PORT: u16 = 8770; // el origen (puerto) guarda el estado de la interfaz: conviene que no cambie entre sesiones
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const START_TIMEOUT: Duration = Duration::from_secs(90);

struct Engine(Mutex<Option<Child>>);

struct Layout {
    python: PathBuf,
    engine_dir: PathBuf,
    ui_dir: PathBuf,
    embedded: bool,
}

fn has_runtime(dir: &Path) -> bool {
    dir.join("python").join("python.exe").is_file() && dir.join("engine").join("server.py").is_file()
}

/// Versión portable/instalada: `runtime/` junto al .exe. Desarrollo: el repo (Python del sistema y la interfaz compilada).
fn find_layout() -> Result<Layout, String> {
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let exe_dir = exe.parent().ok_or("sin carpeta del ejecutable")?.to_path_buf();
    for rt in [exe_dir.join("runtime"), exe_dir.join("resources").join("runtime")] {
        if has_runtime(&rt) {
            return Ok(Layout { python: rt.join("python").join("python.exe"), engine_dir: rt.join("engine"), ui_dir: rt.join("ui"), embedded: true });
        }
    }
    let mut dir = Some(exe_dir.as_path());
    while let Some(d) = dir {
        if d.join("engine").join("server.py").is_file() {
            return Ok(Layout { python: PathBuf::from("python"), engine_dir: d.join("engine"), ui_dir: d.join("proto").join("player").join("dist"), embedded: false });
        }
        dir = d.parent();
    }
    Err("No encontré el motor (carpeta runtime junto a la aplicación).".into())
}

fn log_dir() -> PathBuf {
    let base = std::env::var_os("LOCALAPPDATA").map(PathBuf::from).unwrap_or_else(std::env::temp_dir);
    base.join("ShedStemStudio").join("logs")
}

fn pick_port() -> u16 {
    if TcpListener::bind(("127.0.0.1", PREFERRED_PORT)).is_ok() {
        return PREFERRED_PORT;
    }
    TcpListener::bind(("127.0.0.1", 0)).and_then(|l| l.local_addr()).map(|a| a.port()).unwrap_or(PREFERRED_PORT)
}

/// Job Object: si la cáscara muere de golpe, Windows mata también al motor.
fn kill_on_close(child: &Child) {
    use windows_sys::Win32::System::JobObjects::*;
    unsafe {
        let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if job.is_null() {
            return;
        }
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(job, JobObjectExtendedLimitInformation, &info as *const _ as *const _, std::mem::size_of_val(&info) as u32);
        AssignProcessToJobObject(job, child.as_raw_handle() as _);
        // el handle queda abierto hasta que termina la cáscara
    }
}

fn spawn_engine(l: &Layout, port: u16) -> Result<Child, String> {
    let dir = log_dir();
    fs::create_dir_all(&dir).map_err(|e| format!("No pude crear {}: {e}", dir.display()))?;
    let log = dir.join("engine.log");
    let out = File::create(&log).map_err(|e| format!("No pude abrir {}: {e}", log.display()))?;
    let err = out.try_clone().map_err(|e| e.to_string())?;
    let child = Command::new(&l.python)
        .arg("-u")
        .arg(l.engine_dir.join("server.py"))
        .arg(port.to_string())
        .current_dir(&l.engine_dir)
        .env("STEMSHED_HOST", "127.0.0.1")
        .env("STEMSHED_ORIGINS", format!("http://127.0.0.1:{port}"))
        .env("STEMSHED_UI", &l.ui_dir)
        .env("STEMSHED_SCHEDULER", "1")
        .env("PYTHONUTF8", "1")
        .stdin(Stdio::null())
        .stdout(out)
        .stderr(err)
        .creation_flags(CREATE_NO_WINDOW)
        .spawn()
        .map_err(|e| format!("No pude lanzar Python ({}): {e}", l.python.display()))?;
    kill_on_close(&child);
    Ok(child)
}

fn engine_answers(port: u16) -> bool {
    let Ok(mut s) = TcpStream::connect_timeout(&([127, 0, 0, 1], port).into(), Duration::from_millis(400)) else { return false };
    let _ = s.set_read_timeout(Some(Duration::from_secs(2)));
    if s.write_all(format!("GET /engine/status HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n\r\n").as_bytes()).is_err() {
        return false;
    }
    let mut buf = String::new();
    let _ = s.read_to_string(&mut buf);
    buf.starts_with("HTTP/1.") && buf.contains(" 200 ") && buf.contains("\"engine\": \"ok\"")
}

fn show_error(app: &tauri::AppHandle, text: &str) {
    if let Some(w) = app.get_webview_window("main") {
        let msg = serde_json::to_string(text).unwrap_or_else(|_| "\"error\"".into());
        let _ = w.eval(format!("document.getElementById('m').className='error';document.getElementById('msg').textContent={msg};"));
    }
}

fn boot(app: tauri::AppHandle) {
    let layout = match find_layout() {
        Ok(l) => l,
        Err(e) => return show_error(&app, &e),
    };
    let port = pick_port();
    let child = match spawn_engine(&layout, port) {
        Ok(c) => c,
        Err(e) => return show_error(&app, &e),
    };
    *app.state::<Engine>().0.lock().unwrap() = Some(child);

    let started = Instant::now();
    loop {
        if engine_answers(port) {
            break;
        }
        let exited = app.state::<Engine>().0.lock().unwrap().as_mut().and_then(|c| c.try_wait().ok().flatten());
        if exited.is_some() || started.elapsed() > START_TIMEOUT {
            let why = if exited.is_some() { "El motor se cerró al arrancar." } else { "El motor no respondió a tiempo." };
            return show_error(&app, &format!("{why}\nRegistro: {}\n(Python: {}{})", log_dir().join("engine.log").display(), layout.python.display(), if layout.embedded { ", embebido" } else { ", del sistema" }));
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    if let Some(w) = app.get_webview_window("main") {
        if let Ok(url) = format!("http://127.0.0.1:{port}/").parse() {
            let _ = w.navigate(url);
        }
    }
}

fn stop_engine(app: &tauri::AppHandle) {
    if let Some(mut c) = app.state::<Engine>().0.lock().unwrap().take() {
        // Árbol completo (separadores, Ollama que lanzó el motor); el Job Object cubre el caso de cierre brusco.
        let _ = Command::new("taskkill").args(["/PID", &c.id().to_string(), "/T", "/F"]).creation_flags(CREATE_NO_WINDOW).status();
        let _ = c.kill();
        let _ = c.wait();
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.set_focus();
            }
        }))
        .manage(Engine(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            std::thread::spawn(move || boot(handle));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("no se pudo crear la aplicación")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop_engine(app);
            }
        });
}
