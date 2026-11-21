"""
Main entry point for the LinSticky application.

This script handles the complete application lifecycle, including:
- Setting up the Python path.
- Initializing internationalization (i18n) with gettext.
- Selecting the GDK backend (Wayland or X11).
- Defining and running the main Adw.Application class.
- Ensuring single instance execution via a lock file.
"""
import sys
import os
import gettext
import locale
import builtins
import signal
import fcntl
import gi

# Ensure the project's root directory is in the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from config.config import load_app_info, LOCALE_MAP

# --- Internationalization (i18n) Setup ---
APP_INFO = load_app_info()
APP_ID = APP_INFO.get('service_name')
LOCALE_DIR = os.path.join(current_dir, 'locale')

try:
    from config.config_manager import ConfigManager
    config = ConfigManager.load()
    lang_code = config.get("language", "en")
    
    # Set environment variables for gettext to find the correct translation files.
    full_locale = LOCALE_MAP.get(lang_code, f"{lang_code}.UTF-8")
    os.environ["LANG"] = full_locale
    os.environ["LC_ALL"] = full_locale
    os.environ["LANGUAGE"] = lang_code 

    try:
        locale.setlocale(locale.LC_ALL, full_locale)
    except locale.Error:
        print(f"WARNING: Locale {full_locale} not supported by the system. Falling back.")

    # Install the translation for the chosen language.
    translation = gettext.translation(APP_ID, localedir=LOCALE_DIR, languages=[lang_code], fallback=True)
    translation.install() 
    builtins._ = translation.gettext
    
    print(f"SYSTEM: Language set to '{lang_code}' (Locale: {full_locale})")

except Exception as e:
    # If translation fails, provide a fallback `_` function that does nothing.
    builtins._ = lambda s: s
    print(f"WARNING: Translation setup failed: {e}. Using fallback language.")

# --- GDK Backend Selection ---
# Forcing a backend can be useful for debugging or ensuring compatibility.
# Wayland is preferred for modern systems, but X11 provides broader support.
try:
    if "--x11" in sys.argv or config.get("backend") == "x11":
        os.environ["GDK_BACKEND"] = "x11"
        print("SYSTEM: Environment forced to X11 backend.")
    else:
        os.environ["GDK_BACKEND"] = "wayland,x11"
        print("SYSTEM: Environment set to Wayland with X11 fallback.")
except Exception as e:
    print(f"CRITICAL: Backend selection failed: {e}")

# --- GTK and Adwaita Initialization ---
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gio
from db.db_controller import NotesDB
from application_manager import ApplicationManager


class StickyApp(Adw.Application):
    """
    The main application class for LinSticky.
    
    This class orchestrates the entire application, including database connections,
    window management, and handling system signals for graceful shutdown.
    It inherits from Adw.Application to ensure proper integration with the GNOME desktop.
    """
    def __init__(self):
        """Initializes the application, database, and the core application manager."""
        super().__init__(application_id=APP_ID)
        self.config = ConfigManager.load()
        self.db = NotesDB(path=self.config.get("db_path"))
        self.app_manager = ApplicationManager(self, self.db, self.config)
        self.lock_file = None
        self._ui_ready = False
        self.restart_requested = False

        # Register signal handlers for graceful shutdown (e.g., from systemctl or kill).
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._on_signal_quit, None)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._on_signal_quit, None)

    def do_activate(self):
        """
        Called when the application is activated.

        On the first activation this sets up the main UI components, including
        the main window and tray icon, and restores previously opened notes.
        Later activations (e.g. the user launching the app again) only bring
        the main window to the front.
        """
        if self._ui_ready:
            self.app_manager.show_main_window()
            return
        self._ui_ready = True

        self.app_manager.setup_ui_settings()
        self.app_manager.setup_main_window()
        self.app_manager.start_tray_subprocess()
        
        if hasattr(self.app_manager, 'restore_notes'):
            self.app_manager.restore_notes()

    def _on_signal_quit(self, *args):
        """
        Callback for UNIX signals (SIGTERM, SIGINT) to ensure a clean exit.
        """
        self.quit_app()
        return GLib.SOURCE_REMOVE

    def quit_app(self):
        """
        Safely shuts down all application components, saves data, and closes the database.
        """
        self.app_manager.quit_app_manager()
        if self.db:
            self.db.close()
        
        # Release the lock file
        if self.lock_file:
            try:
                fcntl.flock(self.lock_file, fcntl.LOCK_UN)
                self.lock_file.close()
                os.remove(self.lock_file.name)
            except Exception as e:
                print(f"WARNING: Failed to release lock file: {e}")
                
        self.quit()

    def restart(self):
        """
        Quits cleanly and starts the application again (see __main__).
        Used to apply settings such as the language, which are read at startup.
        """
        self.restart_requested = True
        self.quit_app()


def activate_running_instance() -> bool:
    """
    Asks an already running instance (over D-Bus) to show its main window.
    Returns True if a running instance was found and activated.
    """
    try:
        remote = Gio.Application(application_id=APP_ID)
        remote.register(None)
        if remote.get_is_remote():
            remote.activate()
            remote.get_dbus_connection().flush_sync(None)
            return True
    except Exception as e:
        print(f"WARNING: Could not contact the running instance: {e}")
    return False


def acquire_lock():
    """
    Attempts to acquire a file lock to ensure only one instance is running.
    Returns the file object if successful, or None if locked.
    """
    # Determine lock file path based on environment
    if "SNAP_USER_DATA" in os.environ:
        lock_path = os.path.join(os.environ["SNAP_USER_DATA"], ".linsticky.lock")
    else:
        lock_path = os.path.expanduser("~/.config/linsticky/.linsticky.lock")
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    try:
        lock_file = open(lock_path, 'w')
        # Try to acquire an exclusive lock without blocking
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except IOError:
        return None

if __name__ == "__main__":
    # Set application metadata for the desktop environment.
    GLib.set_prgname(APP_INFO.get('service_name'))
    GLib.set_application_name(APP_INFO.get('app_name'))
    
    # Try to acquire lock before starting the app
    lock = acquire_lock()
    if not lock:
        if activate_running_instance():
            print("INFO: Another instance is already running. Its main window was activated.")
        else:
            print("INFO: Another instance is already running. Exiting.")
        sys.exit(0)
    
    app = StickyApp()
    app.lock_file = lock # Store lock to release it on exit
    status = app.run(sys.argv)
    if app.restart_requested:
        # The lock, database and tray were released in quit_app(); replace this
        # process with a fresh one so the new settings are read from scratch.
        print("SYSTEM: Restarting...")
        sys.stdout.flush()
        os.execv(sys.executable, [sys.executable] + sys.argv)
    sys.exit(status)
