#!/usr/bin/env python3

import sys
import os
import json
import re
import time
import logging
import tempfile
import shutil
import concurrent.futures
import threading
import subprocess
import importlib.util
from datetime import datetime
from collections import deque
from urllib.parse import urljoin, urlparse
from pathlib import Path

import requests
import m3u8
import psutil
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QProgressBar, QFileDialog, QMessageBox, QTabWidget,
    QComboBox, QSpinBox, QCheckBox, QGridLayout, QScrollArea, QFrame,
    QGroupBox, QStyle, QStyleFactory, QToolTip, QSystemTrayIcon, QMenu
)
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QSize, QTimer, QSettings
)
from PyQt5.QtNetwork import QLocalSocket, QLocalServer
from PyQt5.QtGui import QPalette, QColor, QFont, QIcon, QPixmap

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_base_url(url, parsed_url):
    """Get the correct base URL for segment resolution."""
    if url.startswith('#'):
        return parsed_url.scheme + '://' + parsed_url.netloc + os.path.dirname(parsed_url.path) + '/'
    if url.startswith('http'):
        return os.path.dirname(url) + '/'
    return parsed_url.scheme + '://' + parsed_url.netloc + os.path.dirname(parsed_url.path) + '/'

class PluginManager:
    def __init__(self):
        self.plugins = {}
        self.plugin_folder = Path("plugins")
        self.plugin_folder.mkdir(exist_ok=True)
        self.load_plugins()

    def load_plugins(self):
        """Load all plugins from the plugins directory."""
        self.plugins = {}
        for plugin_file in self.plugin_folder.glob("*.m3uplug"):
            try:
                spec = importlib.util.spec_from_file_location(
                    plugin_file.stem, 
                    plugin_file
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                if hasattr(module, 'PLUGIN_INFO'):
                    self.plugins[plugin_file.stem] = {
                        'module': module,
                        'info': module.PLUGIN_INFO,
                        'path': plugin_file
                    }
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_file}: {str(e)}")

    def install_plugin(self, plugin_path):
        """Install a plugin from a file."""
        try:
            plugin_file = Path(plugin_path)
            if not plugin_file.suffix == '.m3uplug':
                raise ValueError("Invalid plugin file")

            # Verify plugin structure
            spec = importlib.util.spec_from_file_location(
                plugin_file.stem, 
                plugin_file
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, 'PLUGIN_INFO'):
                raise ValueError("Invalid plugin format")

            # Copy to plugins folder
            dest = self.plugin_folder / plugin_file.name
            shutil.copy2(plugin_file, dest)
            
            return True, "Plugin installed successfully"
        except Exception as e:
            return False, f"Failed to install plugin: {str(e)}"

    def uninstall_plugin(self, plugin_name):
        """Uninstall a plugin."""
        try:
            if plugin_name in self.plugins:
                plugin_path = self.plugins[plugin_name]['path']
                plugin_path.unlink()
                del self.plugins[plugin_name]
                return True, "Plugin uninstalled successfully"
            return False, "Plugin not found"
        except Exception as e:
            return False, f"Failed to uninstall plugin: {str(e)}"

    def get_installed_plugins(self):
        """Get list of installed plugins."""
        return {
            name: plugin['info'] 
            for name, plugin in self.plugins.items()
        }

class CustomStyle:
    @staticmethod
    def apply_dark_theme(app):
        app.setStyle(QStyleFactory.create("Fusion"))
        
        # Dark theme palette
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.Base, QColor(35, 35, 35))
        dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.Text, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
        dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        
        app.setPalette(dark_palette)
        
        # Enhanced stylesheet
        app.setStyleSheet("""
            QMainWindow {
                background-color: #353535;
            }
            QPushButton {
                background-color: #2979ff;
                border: none;
                color: white;
                padding: 5px 15px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
            QPushButton:disabled {
                background-color: #666666;
            }
            QLineEdit {
                padding: 5px;
                border-radius: 3px;
                border: 1px solid #666666;
                background-color: #424242;
                color: white;
                selection-background-color: #2979ff;
            }
            QProgressBar {
                border: 1px solid #666666;
                border-radius: 3px;
                text-align: center;
                height: 20px;
                background-color: #353535;
            }
            QProgressBar::chunk {
                background-color: #2979ff;
                border-radius: 2px;
            }
            QLabel {
                color: white;
            }
            QGroupBox {
                border: 1px solid #666666;
                border-radius: 5px;
                margin-top: 1em;
                padding-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
            QComboBox {
                padding: 5px;
                border-radius: 3px;
                border: 1px solid #666666;
                background-color: #424242;
                color: white;
                min-width: 6em;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QSpinBox {
                padding: 5px;
                border-radius: 3px;
                border: 1px solid #666666;
                background-color: #424242;
                color: white;
            }
            QScrollArea {
                border: 1px solid #666666;
                border-radius: 3px;
            }
            QTabWidget::pane {
                border: 1px solid #666666;
                border-radius: 3px;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #424242;
                color: white;
                padding: 8px 20px;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #2979ff;
            }
            QTabBar::tab:hover:!selected {
                background-color: #1565c0;
            }
            QCheckBox {
                color: white;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
                border-radius: 3px;
            }
            QCheckBox::indicator:unchecked {
                border: 1px solid #666666;
                background-color: #424242;
            }
            QCheckBox::indicator:checked {
                border: 1px solid #2979ff;
                background-color: #2979ff;
            }
            QToolTip {
                background-color: #424242;
                color: white;
                border: 1px solid #666666;
                border-radius: 3px;
                padding: 5px;
            }
        """)

class SystemTrayApp(QSystemTrayIcon):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setIcon(QIcon("icon.ico"))
        self.setVisible(True)
        
        self.menu = QMenu()
        
        self.open_window_action = self.menu.addAction("Open Window")
        self.open_window_action.triggered.connect(self.show_window)
        
        self.downloads_action = self.menu.addAction("Downloads")
        self.downloads_action.triggered.connect(self.show_downloads)
        
        self.settings_action = self.menu.addAction("Settings")
        self.settings_action.triggered.connect(self.show_settings)
        
        self.menu.addSeparator()
        
        self.quit_action = self.menu.addAction("Quit Application")
        self.quit_action.triggered.connect(self.quit_app)
        
        self.setContextMenu(self.menu)
        self.activated.connect(self.tray_activated)

    def show_window(self):
        self.parent.show()
        self.parent.activateWindow()

    def show_downloads(self):
        self.parent.show()
        self.parent.activateWindow()
        self.parent.tab_widget.setCurrentIndex(0)

    def show_settings(self):
        self.parent.show()
        self.parent.activateWindow()
        self.parent.tab_widget.setCurrentIndex(1)

    def quit_app(self):
        self.parent.force_quit = True
        self.parent.close()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()

class FileAssociationHandler:
    @staticmethod
    def setup_file_associations():
        """Set up file associations for M3U8 files."""
        try:
            # Check if running on Windows
            if sys.platform == 'win32':
                import winreg
                exe_path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
                
                # Windows registry setup
                with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, '.m3u8') as key:
                    winreg.SetValue(key, '', winreg.REG_SZ, 'M3U8ME.m3u8file')
                    
                with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, 'M3U8ME.m3u8file') as key:
                    winreg.SetValue(key, '', winreg.REG_SZ, 'M3U8 Playlist File')
                    
                    with winreg.CreateKey(key, 'DefaultIcon') as icon_key:
                        icon_path = os.path.join(os.path.dirname(exe_path), 'icon.ico')
                        winreg.SetValue(icon_key, '', winreg.REG_SZ, icon_path)
                    
                    with winreg.CreateKey(key, 'shell\\open\\command') as cmd_key:
                        cmd = f'"{exe_path}" "%1"'
                        winreg.SetValue(cmd_key, '', winreg.REG_SZ, cmd)
                
                with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, 'm3u8me') as key:
                    winreg.SetValue(key, '', winreg.REG_SZ, 'URL:M3U8ME Protocol')
                    winreg.SetValueEx(key, 'URL Protocol', 0, winreg.REG_SZ, '')
                    
                    with winreg.CreateKey(key, 'DefaultIcon') as icon_key:
                        icon_path = os.path.join(os.path.dirname(exe_path), 'icon.ico')
                        winreg.SetValue(icon_key, '', winreg.REG_SZ, icon_path)
                    
                    with winreg.CreateKey(key, 'shell\\open\\command') as cmd_key:
                        cmd = f'"{exe_path}" "%1"'
                        winreg.SetValue(cmd_key, '', winreg.REG_SZ, cmd)
            
            elif sys.platform == 'linux':
                # Linux desktop entry setup
                exe_path = os.path.abspath(sys.argv[0])
                icon_path = os.path.join(os.path.dirname(exe_path), 'icon.png')
                desktop_dir = os.path.expanduser('~/.local/share/applications')
                os.makedirs(desktop_dir, exist_ok=True)
                
                desktop_entry = f"""[Desktop Entry]
Name=M3U8ME
Comment=M3U8 Stream Downloader
Exec={exe_path} %f
Icon={icon_path}
Terminal=false
Type=Application
Categories=AudioVideo;Network;
MimeType=application/x-mpegURL;x-scheme-handler/m3u8me;
"""
                
                desktop_file = os.path.join(desktop_dir, 'm3u8me.desktop')
                with open(desktop_file, 'w') as f:
                    f.write(desktop_entry)
                
                # Update MIME database
                mime_dir = os.path.expanduser('~/.local/share/mime/packages')
                os.makedirs(mime_dir, exist_ok=True)
                
                mime_xml = """<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-mpegURL">
    <comment>M3U8 Playlist</comment>
    <glob pattern="*.m3u8"/>
  </mime-type>
</mime-info>
"""
                
                mime_file = os.path.join(mime_dir, 'm3u8me.xml')
                with open(mime_file, 'w') as f:
                    f.write(mime_xml)
                
                # Update databases
                subprocess.run(['update-mime-database', os.path.expanduser('~/.local/share/mime')], check=False)
                subprocess.run(['update-desktop-database', desktop_dir], check=False)
                
            elif sys.platform == 'darwin':
                # macOS associations setup
                # Note: macOS associations typically require app bundling
                logger.warning("File associations on macOS require app bundling")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to set up file associations: {str(e)}")
            return False

class DownloadWidget(QFrame):
    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url
        self.init_ui()
        
    def init_ui(self):
        layout = QHBoxLayout(self)
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        
        self.setStyleSheet("""
            QFrame {
                background-color: #424242;
                border-radius: 5px;
                padding: 10px;
                margin: 5px;
            }
            QLabel {
                color: white;
            }
        """)
        
        # URL and status layout
        info_layout = QVBoxLayout()
        
        display_url = self.url[:50] + '...' if len(self.url) > 50 else self.url
        self.url_label = QLabel(display_url)
        self.url_label.setToolTip(self.url)
        self.url_label.setStyleSheet("font-weight: bold;")
        
        self.status_label = QLabel("Waiting to start...")
        self.status_label.setStyleSheet("color: #2979ff;")
        
        info_layout.addWidget(self.url_label)
        info_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #666666;
                border-radius: 3px;
                text-align: center;
                height: 20px;
                background-color: #353535;
            }
            QProgressBar::chunk {
                background-color: #2979ff;
                border-radius: 2px;
            }
        """)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedWidth(80)
        self.cancel_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserStop))
        
        layout.addLayout(info_layout, stretch=2)
        layout.addWidget(self.progress_bar, stretch=3)
        layout.addWidget(self.cancel_btn)

    def update_status(self, status, color="#2979ff"):
        self.status_label.setText(status)
        self.status_label.setStyleSheet(f"color: {color};")

class StreamDownloader(QThread):
    progress_updated = pyqtSignal(str, int, str)
    download_complete = pyqtSignal(str)
    download_error = pyqtSignal(str, str)

    def __init__(self, url, save_path, settings):
        super().__init__()
        self.url = url
        self.save_path = save_path
        self.settings = settings
        self.is_running = True
        self.temp_dir = None
        self.retry_count = settings.get('retry_attempts', 3)
        self.max_concurrent_segments = self._calculate_optimal_workers()
        self.chunk_size = self._calculate_optimal_chunk_size()
        self.segment_queue = deque()
        self.download_lock = threading.Lock()
        self.progress_lock = threading.Lock()
        self.completed_segments = set()
        self.session = self._configure_session()
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }

    def _calculate_optimal_workers(self):
        try:
            cpu_count = psutil.cpu_count(logical=False) or 2
            memory = psutil.virtual_memory()
            available_memory_gb = memory.available / (1024 * 1024 * 1024)
            cpu_based = cpu_count * 2
            memory_based = int(available_memory_gb * 4)
            optimal_workers = min(cpu_based, memory_based)
            return max(4, min(optimal_workers, 64))
        except:
            return 8

    def _calculate_optimal_chunk_size(self):
        try:
            memory = psutil.virtual_memory()
            available_memory_mb = memory.available / (1024 * 1024)
            if available_memory_mb > 8192:
                return 4 * 1024 * 1024
            elif available_memory_mb > 4096:
                return 2 * 1024 * 1024
            else:
                return 1 * 1024 * 1024
        except:
            return 1 * 1024 * 1024

    def _configure_session(self):
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=self.max_concurrent_segments,
            pool_maxsize=self.max_concurrent_segments,
            max_retries=self.retry_count,
            pool_block=False
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        session.timeout = (5, 30)
        return session

    def download_segment(self, segment_url, output_path, index, total):
        temp_path = f"{output_path}.temp"
        
        for attempt in range(self.retry_count):
            try:
                if not self.is_running:
                    return False

                if segment_url.startswith('//'):
                    segment_url = 'https:' + segment_url
                elif not segment_url.startswith('http'):
                    if not segment_url.startswith('/'):
                        segment_url = '/' + segment_url
                    parsed_parent = urlparse(self.url)
                    segment_url = f"{parsed_parent.scheme}://{parsed_parent.netloc}{segment_url}"

                with self.session.get(
                    segment_url,
                    headers=self.headers,
                    timeout=self.settings.get('segment_timeout', 30),
                    verify=False,
                    stream=True
                ) as response:
                    response.raise_for_status()
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded_size = 0
                    
                    with open(temp_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=self.chunk_size):
                            if not self.is_running:
                                return False
                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)
                                
                                if total_size > 0:
                                    segment_progress = int((downloaded_size / total_size) * 100)
                                    with self.progress_lock:
                                        self.progress_updated.emit(
                                            self.url,
                                            int((index + segment_progress/100) / total * 90),
                                            f"Downloading segment {index + 1}/{total}"
                                        )

                if os.path.exists(temp_path):
                    file_size = os.path.getsize(temp_path)
                    if file_size < 100:
                        raise Exception(f"Segment {index} is too small: {file_size} bytes")
                    
                    os.replace(temp_path, output_path)
                    
                    with self.download_lock:
                        self.completed_segments.add(index)
                        progress = int(len(self.completed_segments) / total * 90)
                        self.progress_updated.emit(
                            self.url,
                            progress,
                            f"Downloaded {len(self.completed_segments)}/{total} segments"
                        )
                    return True
                else:
                    raise Exception(f"Failed to download segment {index}")

            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{self.retry_count} failed for segment {index}: {str(e)}")
                if attempt < self.retry_count - 1:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                return False
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                        
        return False

    def combine_segments(self, segment_files, output_file):
        try:
            if not shutil.which('ffmpeg'):
                raise Exception("FFmpeg not found. Please install FFmpeg to continue.")

            concat_file = os.path.join(self.temp_dir, 'concat.txt')
            with open(concat_file, 'w', encoding='utf-8') as f:
                for segment in segment_files:
                    f.write(f"file '{segment}'\n")

            output_format = self.settings.get('output_format', 'mp4')
            output_file = f"{output_file}.{output_format}"

            encoding_params = {
                'mp4': {
                    'vcodec': 'copy',
                    'acodec': 'copy',
                    'extra': [
                        '-movflags', '+faststart',
                        '-max_muxing_queue_size', '4096',
                        '-fflags', '+genpts',
                        '-avoid_negative_ts', 'make_zero',
                        '-async', '1'
                    ]
                },
                'mkv': {
                    'vcodec': 'copy',
                    'acodec': 'copy',
                    'extra': [
                        '-max_muxing_queue_size', '4096',
                        '-map', '0',
                        '-fflags', '+genpts',
                        '-async', '1'
                    ]
                },
                'ts': {
                    'vcodec': 'copy',
                    'acodec': 'copy',
                    'extra': [
                        '-copyts',
                        '-muxdelay', '0',
                        '-muxpreload', '0',
                        '-fflags', '+genpts',
                        '-avoid_negative_ts', 'make_zero'
                    ]
                }
            }

            params = encoding_params.get(output_format)
            
            cmd = [
                'ffmpeg', '-y',
                '-hide_banner',
                '-loglevel', 'warning',
                '-stats',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c:v', params['vcodec'],
                '-c:a', params['acodec']
            ]
            
            cmd.extend(params['extra'])
            cmd.append(output_file)

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            while True:
                if not self.is_running:
                    process.terminate()
                    raise Exception("Processing cancelled by user")
                    
                output = process.stderr.readline()
                if output == '' and process.poll() is not None:
                    break
                    
                if 'time=' in output:
                    try:
                        time_str = output.split('time=')[1].split()[0]
                        h, m, s = map(float, time_str.split(':'))
                        progress = min(99, 90 + int(h * 3600 + m * 60 + s) % 10)
                        self.progress_updated.emit(self.url, progress, "Processing video...")
                    except:
                        pass

            if process.returncode != 0:
                raise Exception(f"FFmpeg error: {process.stderr.read().strip()}")

            if not os.path.exists(output_file) or os.path.getsize(output_file) < 1000:
                raise Exception("Output file is missing or too small")

            return True

        except Exception as e:
            logger.error(f"Error combining segments: {str(e)}")
            return False

    def run(self):
        try:
            self.temp_dir = tempfile.mkdtemp()
            parsed_url = urlparse(self.url)

            if self.url.startswith('#EXTM3U'):
                content = self.url
            else:
                response = self.session.get(
                    self.url,
                    headers=self.headers,
                    verify=False,
                    timeout=30
                )
                response.raise_for_status()
                content = response.text

            playlist = m3u8.loads(content)

            if not playlist.segments and playlist.playlists:
                playlists = sorted(
                    playlist.playlists,
                    key=lambda p: p.stream_info.bandwidth if p.stream_info else 0
                )
                
                quality = self.settings.get('quality', 'best')
                if quality == 'best':
                    selected_playlist = playlists[-1]
                elif quality == 'worst':
                    selected_playlist = playlists[0]
                else:
                    selected_playlist = playlists[len(playlists)//2]

                playlist_url = selected_playlist.uri
                if not playlist_url.startswith('http'):
                    base_url = get_base_url(self.url, parsed_url)
                    playlist_url = urljoin(base_url, playlist_url)

                response = self.session.get(
                    playlist_url,
                    headers=self.headers,
                    verify=False,
                    timeout=30
                )
                response.raise_for_status()
                playlist = m3u8.loads(response.text)
                parsed_url = urlparse(playlist_url)

            if not playlist.segments:
                raise Exception("No segments found in playlist")

            base_url = get_base_url(self.url, parsed_url)
            total_segments = len(playlist.segments)

            segment_tasks = []
            for i, segment in enumerate(playlist.segments):
                output_path = os.path.join(self.temp_dir, f"segment_{i:05d}.ts")
                segment_url = urljoin(base_url, segment.uri)
                segment_tasks.append((segment_url, output_path, i))

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_concurrent_segments) as executor:
                futures = {
                    executor.submit(
                        self.download_segment,
                        url,
                        path,
                        idx,
                        total_segments
                    ): idx for url, path, idx in segment_tasks
                }

                for future in concurrent.futures.as_completed(futures):
                    if not self.is_running:
                        executor.shutdown(wait=False)
                        raise Exception("Download cancelled by user")

                    idx = futures[future]
                    try:
                        if not future.result():
                            raise Exception(f"Failed to download segment {idx}")
                    except Exception as e:
                        logger.error(f"Error downloading segment {idx}: {str(e)}")
                        raise

            if len(self.completed_segments) != total_segments:
                raise Exception(f"Missing segments. Downloaded {len(self.completed_segments)}/{total_segments}")

            self.progress_updated.emit(self.url, 90, "Processing video...")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            quality_info = f"_{self.settings.get('quality', 'best')}"
            output_file = os.path.join(
                self.save_path,
                f"video_{timestamp}{quality_info}"
            )

            segment_files = [
                os.path.join(self.temp_dir, f"segment_{i:05d}.ts")
                for i in range(total_segments)
            ]

            if self.combine_segments(segment_files, output_file):
                self.download_complete.emit(self.url)
            else:
                raise Exception("Failed to process video")

        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            self.download_error.emit(self.url, str(e))
        finally:
            if self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir, ignore_errors=True)
                except:
                    pass
            try:
                self.session.close()
            except:
                pass

    def stop(self):
        self.is_running = False
        try:
            self.session.close()
        except:
            pass

class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plugin_manager = PluginManager()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Video Settings
        video_group = QGroupBox("Video Settings")
        video_layout = QGridLayout()
        
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(['best', 'medium', 'worst'])
        self.quality_combo.setToolTip("Select the video quality for multi-quality streams")
        video_layout.addWidget(QLabel("Quality:"), 0, 0)
        video_layout.addWidget(self.quality_combo, 0, 1)
        
        self.format_combo = QComboBox()
        self.format_combo.addItems(['mp4', 'mkv', 'ts'])
        self.format_combo.setItemData(0, "Best for compatibility and streaming (recommended)", Qt.ToolTipRole)
        self.format_combo.setItemData(1, "Good for high quality and multiple audio tracks", Qt.ToolTipRole)
        self.format_combo.setItemData(2, "Raw stream without re-encoding (faster but larger)", Qt.ToolTipRole)
        video_layout.addWidget(QLabel("Output Format:"), 1, 0)
        video_layout.addWidget(self.format_combo, 1, 1)
        
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(['Standard', 'High Quality', 'Small Size'])
        self.preset_combo.setToolTip("Predefined quality settings for different use cases")
        video_layout.addWidget(QLabel("Quality Preset:"), 2, 0)
        video_layout.addWidget(self.preset_combo, 2, 1)
        self.preset_combo.currentTextChanged.connect(self.apply_preset)
        
        video_group.setLayout(video_layout)
        layout.addWidget(video_group)

        # Download Settings
        download_group = QGroupBox("Download Settings")
        download_layout = QGridLayout()
        
        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, 16)
        self.thread_spin.setValue(4)
        self.thread_spin.setToolTip("Number of concurrent segment downloads")
        download_layout.addWidget(QLabel("Download Threads:"), 0, 0)
        download_layout.addWidget(self.thread_spin, 0, 1)
        
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 120)
        self.timeout_spin.setValue(30)
        self.timeout_spin.setToolTip("Timeout in seconds for each segment download")
        download_layout.addWidget(QLabel("Segment Timeout (s):"), 1, 0)
        download_layout.addWidget(self.timeout_spin, 1, 1)
        
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 5)
        self.retry_spin.setValue(3)
        self.retry_spin.setToolTip("Number of retry attempts for failed downloads")
        download_layout.addWidget(QLabel("Retry Attempts:"), 2, 0)
        download_layout.addWidget(self.retry_spin, 2, 1)
        
        self.concurrent_check = QCheckBox("Download Streams Concurrently")
        self.concurrent_check.setChecked(False)
        self.concurrent_check.setToolTip("Download multiple streams at the same time")
        download_layout.addWidget(self.concurrent_check, 3, 0, 1, 2)
        
        download_group.setLayout(download_layout)
        layout.addWidget(download_group)

        # Plugin Management
        plugin_group = QGroupBox("Plugin Management")
        plugin_layout = QVBoxLayout()
        
        # Plugin list
        self.plugin_list = QScrollArea()
        self.plugin_list.setWidgetResizable(True)
        self.plugin_list_widget = QWidget()
        self.plugin_list_layout = QVBoxLayout(self.plugin_list_widget)
        self.plugin_list.setWidget(self.plugin_list_widget)
        
        # Plugin controls
        plugin_buttons = QHBoxLayout()
        
        install_btn = QPushButton("Install Plugin")
        install_btn.clicked.connect(self.install_plugin)
        plugin_buttons.addWidget(install_btn)
        
        refresh_btn = QPushButton("Refresh Plugins")
        refresh_btn.clicked.connect(self.refresh_plugins)
        plugin_buttons.addWidget(refresh_btn)
        
        plugin_layout.addLayout(plugin_buttons)
        plugin_layout.addWidget(self.plugin_list)
        plugin_group.setLayout(plugin_layout)
        layout.addWidget(plugin_group)
        
        self.refresh_plugins()
        
        # Output Settings
        output_group = QGroupBox("Output Settings")
        output_layout = QGridLayout()
        
        self.auto_rename_check = QCheckBox("Auto-rename on conflict")
        self.auto_rename_check.setChecked(True)
        self.auto_rename_check.setToolTip("Automatically rename files if they already exist")
        output_layout.addWidget(self.auto_rename_check, 0, 0)
        
        self.preserve_source_check = QCheckBox("Preserve source quality")
        self.preserve_source_check.setChecked(True)
        self.preserve_source_check.setToolTip("Maintain original video quality when possible")
        output_layout.addWidget(self.preserve_source_check, 1, 0)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
        
        # Add a spacer at the bottom
        layout.addStretch()

    def apply_preset(self, preset):
        if preset == 'High Quality':
            self.quality_combo.setCurrentText('best')
            self.format_combo.setCurrentText('mkv')
            self.preserve_source_check.setChecked(True)
        elif preset == 'Small Size':
            self.quality_combo.setCurrentText('medium')
            self.format_combo.setCurrentText('mp4')
            self.preserve_source_check.setChecked(False)
        else:  # Standard
            self.quality_combo.setCurrentText('best')
            self.format_combo.setCurrentText('mp4')
            self.preserve_source_check.setChecked(True)

    def install_plugin(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Plugin File",
            "",
            "M3U8ME Plugins (*.m3uplug)"
        )
        
        if file_path:
            success, message = self.plugin_manager.install_plugin(file_path)
            
            if success:
                self.refresh_plugins()
                reply = QMessageBox.question(
                    self,
                    "Plugin Installed",
                    "Plugin installed successfully. Restart application to apply changes?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                
                if reply == QMessageBox.Yes:
                    QApplication.quit()
            else:
                QMessageBox.critical(
                    self,
                    "Installation Failed",
                    message,
                    QMessageBox.Ok
                )

    def refresh_plugins(self):
        for i in reversed(range(self.plugin_list_layout.count())):
            self.plugin_list_layout.itemAt(i).widget().deleteLater()
        
        plugins = self.plugin_manager.get_installed_plugins()
        for name, info in plugins.items():
            plugin_widget = QFrame()
            plugin_widget.setFrameStyle(QFrame.Box | QFrame.Raised)
            plugin_layout = QHBoxLayout(plugin_widget)
            
            # Plugin info
            info_layout = QVBoxLayout()
            name_label = QLabel(f"<b>{info.get('name', name)}</b>")
            desc_label = QLabel(info.get('description', 'No description'))
            version_label = QLabel(f"Version: {info.get('version', '1.0')}")
            
            info_layout.addWidget(name_label)
            info_layout.addWidget(desc_label)
            info_layout.addWidget(version_label)
            
            # Uninstall button
            uninstall_btn = QPushButton("Uninstall")
            uninstall_btn.clicked.connect(
                lambda n=name: self.uninstall_plugin(n)
            )
            
            plugin_layout.addLayout(info_layout)
            plugin_layout.addWidget(uninstall_btn)
            
            self.plugin_list_layout.addWidget(plugin_widget)
        
        self.plugin_list_layout.addStretch()

    def uninstall_plugin(self, plugin_name):
        reply = QMessageBox.question(
            self,
            "Confirm Uninstall",
            f"Are you sure you want to uninstall {plugin_name}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            success, message = self.plugin_manager.uninstall_plugin(plugin_name)
            
            if success:
                self.refresh_plugins()
                QMessageBox.information(
                    self,
                    "Plugin Uninstalled",
                    "Plugin uninstalled successfully. Please restart the application.",
                    QMessageBox.Ok
                )
            else:
                QMessageBox.critical(
                    self,
                    "Uninstall Failed",
                    message,
                    QMessageBox.Ok
                )

    def get_settings(self):
        return {
            'quality': self.quality_combo.currentText(),
            'output_format': self.format_combo.currentText(),
            'max_workers': self.thread_spin.value(),
            'segment_timeout': self.timeout_spin.value(),
            'retry_attempts': self.retry_spin.value(),
            'concurrent_downloads': self.concurrent_check.isChecked(),
            'auto_rename': self.auto_rename_check.isChecked(),
            'preserve_source': self.preserve_source_check.isChecked()
        }

    def save_settings(self):
        settings = self.get_settings()
        try:
            with open('m3u8_settings.json', 'w') as f:
                json.dump(settings, f)
        except Exception as e:
            logger.error(f"Error saving settings: {str(e)}")

    def load_settings(self):
        try:
            with open('m3u8_settings.json', 'r') as f:
                settings = json.load(f)
                
            self.quality_combo.setCurrentText(settings.get('quality', 'best'))
            self.format_combo.setCurrentText(settings.get('output_format', 'mp4'))
            self.thread_spin.setValue(settings.get('max_workers', 4))
            self.timeout_spin.setValue(settings.get('segment_timeout', 30))
            self.retry_spin.setValue(settings.get('retry_attempts', 3))
            self.concurrent_check.setChecked(settings.get('concurrent_downloads', False))
            self.auto_rename_check.setChecked(settings.get('auto_rename', True))
            self.preserve_source_check.setChecked(settings.get('preserve_source', True))
        except:
            pass

class M3U8StreamDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        # First initialize all instance variables
        self.force_quit = False
        self.setWindowTitle("M3U8 Stream Downloader")
        self.setMinimumSize(900, 700)
        self.active_downloads = {}
        self.save_path = None
        self.url_input = None
        self.downloads_area = None
        self.downloads_widget = None
        self.downloads_layout = None
        self.start_all_btn = None
        self.stop_all_btn = None
        self.clear_completed_btn = None
        self.tab_widget = None
        self.download_tab = QWidget()
        self.settings_tab = SettingsTab()
        
        # Then create the UI
        self.init_ui()
        self.setup_status_bar()
        self.tray_icon = SystemTrayApp(self)
        
        # Finally, do system checks and load settings
        self.check_first_run()
        self.process_arguments()
        self.load_settings()
        self.check_ffmpeg()

    # Signal-connected methods defined first
    def add_url_from_input(self):
        url = self.url_input.text().strip()
        if not url:
            return
            
        if not (url.startswith('http') or url.startswith('#EXTM3U')):
            QMessageBox.warning(
                self,
                "Invalid URL",
                "Please enter a valid HTTP(S) URL or M3U8 content",
                QMessageBox.Ok
            )
            return
            
        self.add_download(url)
        self.url_input.clear()
        self.url_input.setFocus()

    def bulk_upload(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select M3U8 Files or URL List",
            "",
            "M3U8 Files (*.m3u8);;Text Files (*.txt);;All Files (*.*)"
        )
        
        if not file_paths:
            return
            
        if not self.save_path:
            self.save_path = QFileDialog.getExistingDirectory(
                self,
                "Select Save Directory",
                options=QFileDialog.ShowDirsOnly
            )
            
            if not self.save_path:
                return

        added = 0
        skipped = 0
        errors = 0
        
        for file_path in file_paths:
            try:
                if file_path.endswith('.txt'):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            url = line.strip()
                            if url and (url.startswith('http') or url.startswith('#EXTM3U')):
                                if url not in self.active_downloads:
                                    self.add_download(url)
                                    added += 1
                                else:
                                    skipped += 1
                else:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content not in self.active_downloads:
                            self.add_download(content)
                            added += 1
                        else:
                            skipped += 1
                            
            except Exception as e:
                logger.error(f"Error reading file {file_path}: {str(e)}")
                errors += 1

        message = f"Added {added} new downloads\n"
        if skipped > 0:
            message += f"Skipped {skipped} duplicate URLs\n"
        if errors > 0:
            message += f"Failed to read {errors} files"
            
        QMessageBox.information(
            self,
            "Bulk Upload Complete",
            message,
            QMessageBox.Ok
        )

        if self.active_downloads:
            self.start_all_btn.setEnabled(True)
            self.update_status_bar()

    def start_all_downloads(self):
        if not self.active_downloads:
            return

        if not self.save_path:
            self.save_path = QFileDialog.getExistingDirectory(
                self,
                "Select Save Directory",
                options=QFileDialog.ShowDirsOnly
            )
            if not self.save_path:
                return

        settings = self.settings_tab.get_settings()
        concurrent = settings['concurrent_downloads']

        self.start_all_btn.setEnabled(False)
        self.stop_all_btn.setEnabled(True)

        if concurrent:
            for url in list(self.active_downloads.keys()):
                if self.active_downloads[url]['status'] == 'waiting':
                    self.start_download(url)
        else:
            self.start_next_download()

    def stop_all_downloads(self):
        active_count = 0
        for download in self.active_downloads.values():
            if download['status'] == 'downloading':
                if download['worker']:
                    download['worker'].stop()
                download['status'] = 'stopped'
                download['widget'].update_status("Stopped", "#ff5252")
                active_count += 1

        if active_count > 0:
            QMessageBox.information(
                self,
                "Downloads Stopped",
                f"Stopped {active_count} active downloads",
                QMessageBox.Ok
            )

        self.stop_all_btn.setEnabled(False)
        self.start_all_btn.setEnabled(True)
        self.update_status_bar()

    def clear_completed_downloads(self):
        completed_count = sum(1 for d in self.active_downloads.values() 
                            if d['status'] in ['completed', 'error', 'stopped'])
        
        if completed_count == 0:
            return
            
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            f"Remove {completed_count} completed/stopped downloads?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            urls_to_remove = [
                url for url, download in self.active_downloads.items()
                if download['status'] in ['completed', 'error', 'stopped']
            ]
            
            for url in urls_to_remove:
                self.remove_download(url)
            
            QMessageBox.information(
                self,
                "Clear Complete",
                f"Removed {len(urls_to_remove)} downloads",
                QMessageBox.Ok
            )

    def create_buttons(self):
        """Create control buttons and connect signals"""
        # Add URL button
        self.add_url_btn = QPushButton("Add URL")
        self.add_url_btn.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        self.add_url_btn.setToolTip("Add a single URL to the download queue")
        self.add_url_btn.clicked.connect(self.add_url_from_input)

        # Bulk upload button
        self.bulk_upload_btn = QPushButton("Bulk Upload")
        self.bulk_upload_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        self.bulk_upload_btn.setToolTip("Upload multiple URLs from a file")
        self.bulk_upload_btn.clicked.connect(self.bulk_upload)

        # Control buttons
        self.start_all_btn = QPushButton("Start All")
        self.start_all_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.start_all_btn.setToolTip("Start all pending downloads")
        self.start_all_btn.clicked.connect(self.start_all_downloads)
        self.start_all_btn.setEnabled(False)

        self.stop_all_btn = QPushButton("Stop All")
        self.stop_all_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
        self.stop_all_btn.setToolTip("Stop all active downloads")
        self.stop_all_btn.clicked.connect(self.stop_all_downloads)
        self.stop_all_btn.setEnabled(False)

        self.clear_completed_btn = QPushButton("Clear Completed")
        self.clear_completed_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        self.clear_completed_btn.setToolTip("Remove completed downloads from the list")
        self.clear_completed_btn.clicked.connect(self.clear_completed_downloads)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
    
        # Logo
        logo_container = QWidget()
        logo_container.setFixedHeight(100)
        logo_layout = QHBoxLayout(logo_container)
        
        logo_label = QLabel()
        try:
            logo_pixmap = QPixmap("logo.png")
            scaled_pixmap = logo_pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
        except:
            logo_label.setText("M3U8ME")
            logo_label.setStyleSheet("font-size: 24pt; font-weight: bold;")
            
        logo_label.setAlignment(Qt.AlignCenter)
        
        logo_layout.addStretch()
        logo_layout.addWidget(logo_label)
        logo_layout.addStretch()
        
        layout.addWidget(logo_container)
    
        # Create control buttons before initializing tabs
        self.create_buttons()
        
        # Main content
        self.tab_widget = QTabWidget()
        self.init_download_tab()
        
        self.tab_widget.addTab(self.download_tab, "Downloads")
        self.tab_widget.addTab(self.settings_tab, "Settings")
        
        layout.addWidget(self.tab_widget)
        
    def init_download_tab(self):
        layout = QVBoxLayout(self.download_tab)

        # URL input area
        url_group = QGroupBox("Add Stream")
        url_layout = QHBoxLayout()
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter M3U8 stream URL or paste M3U8 content")
        self.url_input.returnPressed.connect(self.add_url_from_input)
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.add_url_btn)
        url_layout.addWidget(self.bulk_upload_btn)
        
        url_group.setLayout(url_layout)
        layout.addWidget(url_group)

        # Downloads area
        downloads_group = QGroupBox("Downloads")
        downloads_layout = QVBoxLayout()
        
        self.downloads_area = QScrollArea()
        self.downloads_area.setWidgetResizable(True)
        self.downloads_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.downloads_widget = QWidget()
        self.downloads_layout = QVBoxLayout(self.downloads_widget)
        self.downloads_layout.addStretch()
        self.downloads_area.setWidget(self.downloads_widget)
        downloads_layout.addWidget(self.downloads_area)
        
        downloads_group.setLayout(downloads_layout)
        layout.addWidget(downloads_group)

        # Control buttons
        control_group = QGroupBox()
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.start_all_btn)
        button_layout.addWidget(self.stop_all_btn)
        button_layout.addWidget(self.clear_completed_btn)
        
        control_group.setLayout(button_layout)
        layout.addWidget(control_group)

    def setup_status_bar(self):
        self.statusBar().showMessage("Ready")
        
        self.status_downloads = QLabel("Downloads: 0")
        self.status_downloads.setToolTip("Total number of downloads")
        
        self.status_active = QLabel("Active: 0")
        self.status_active.setToolTip("Currently downloading")
        
        self.status_completed = QLabel("Completed: 0")
        self.status_completed.setToolTip("Successfully completed downloads")
        
        separator = QLabel(" | ")
        separator.setStyleSheet("color: #666666;")
        
        self.statusBar().addPermanentWidget(self.status_downloads)
        self.statusBar().addPermanentWidget(separator)
        self.statusBar().addPermanentWidget(self.status_active)
        self.statusBar().addPermanentWidget(QLabel(" | "))
        self.statusBar().addPermanentWidget(self.status_completed)

    def add_download(self, url):
        if url in self.active_downloads:
            QMessageBox.warning(
                self,
                "Duplicate URL",
                "This URL is already in the download queue!",
                QMessageBox.Ok
            )
            return

        download_widget = DownloadWidget(url)
        download_widget.cancel_btn.clicked.connect(lambda: self.remove_download(url))
        
        self.downloads_layout.insertWidget(
            self.downloads_layout.count() - 1,
            download_widget
        )
        
        self.active_downloads[url] = {
            'widget': download_widget,
            'worker': None,
            'status': 'waiting'
        }

        self.start_all_btn.setEnabled(True)
        self.update_status_bar()

    def remove_download(self, url):
        if url not in self.active_downloads:
            return
            
        download = self.active_downloads[url]
        if download['status'] == 'downloading':
            reply = QMessageBox.question(
                self,
                "Confirm Cancel",
                "This download is still in progress. Are you sure you want to cancel it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        if download['worker']:
            download['worker'].stop()
            
        download['widget'].deleteLater()
        del self.active_downloads[url]

        if not self.active_downloads:
            self.start_all_btn.setEnabled(False)
            self.stop_all_btn.setEnabled(False)
            
        self.update_status_bar()

    def start_download(self, url):
        if url not in self.active_downloads:
            return

        save_path = self.save_path
        if not save_path:
            save_path = QFileDialog.getExistingDirectory(
                self,
                "Select Save Directory",
                options=QFileDialog.ShowDirsOnly
            )
            
            if not save_path:
                return
            
            self.save_path = save_path

        settings = self.settings_tab.get_settings()
        
        worker = StreamDownloader(url, save_path, settings)
        worker.progress_updated.connect(self.update_progress)
        worker.download_complete.connect(self.download_finished)
        worker.download_error.connect(self.download_error)
        
        self.active_downloads[url].update({
            'worker': worker,
            'status': 'downloading'
        })
        
        self.active_downloads[url]['widget'].update_status(
            "Initializing download...",
            "#2979ff"
        )
        
        worker.start()
        self.stop_all_btn.setEnabled(True)
        self.update_status_bar()

    def start_next_download(self):
        for url in self.active_downloads:
            if self.active_downloads[url]['status'] == 'waiting':
                self.start_download(url)
                break

    def update_progress(self, url, progress, status):
        if url not in self.active_downloads:
            return

        download = self.active_downloads[url]
        download['widget'].progress_bar.setValue(progress)
        download['widget'].update_status(status)
        
        if progress < 30:
            color = "#ff5252"
        elif progress < 70:
            color = "#ffd740"
        else:
            color = "#69f0ae"
            
        download['widget'].progress_bar.setStyleSheet(
            f"""
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 2px;
            }}
            """
        )

        self.update_status_bar()

    def download_finished(self, url):
        if url not in self.active_downloads:
            return

        download = self.active_downloads[url]
        download['status'] = 'completed'
        download['widget'].update_status("Completed", "#69f0ae")
        download['widget'].progress_bar.setValue(100)
        download['widget'].progress_bar.setStyleSheet(
            """
            QProgressBar::chunk {
                background-color: #69f0ae;
                border-radius: 2px;
            }
            """
        )
        
        settings = self.settings_tab.get_settings()
        if not settings['concurrent_downloads']:
            self.start_next_download()

        active_downloads = any(
            download['status'] == 'downloading' 
            for download in self.active_downloads.values()
        )
        
        if not active_downloads:
            self.start_all_btn.setEnabled(True)
            self.stop_all_btn.setEnabled(False)
            
            total_completed = sum(
                1 for d in self.active_downloads.values() 
                if d['status'] == 'completed'
            )
            
            if total_completed > 0:
                QMessageBox.information(
                    self,
                    "Downloads Complete",
                    f"All downloads completed successfully! ({total_completed} files)",
                    QMessageBox.Ok
                )
            
        self.update_status_bar()

    def download_error(self, url, error):
        if url not in self.active_downloads:
            return

        download = self.active_downloads[url]
        download['status'] = 'error'
        download['widget'].update_status("Error", "#ff5252")
        
        detailed_error = f"Error downloading {url}:\n\n{error}"
        logger.error(detailed_error)
        
        QMessageBox.critical(
            self,
            "Download Error",
            detailed_error,
            QMessageBox.Ok
        )

        settings = self.settings_tab.get_settings()
        if not settings['concurrent_downloads']:
            self.start_next_download()
                
        self.update_status_bar()

    def update_status_bar(self):
        total = len(self.active_downloads)
        active = sum(1 for d in self.active_downloads.values() if d['status'] == 'downloading')
        completed = sum(1 for d in self.active_downloads.values() if d['status'] == 'completed')
        errors = sum(1 for d in self.active_downloads.values() if d['status'] == 'error')
        
        self.status_downloads.setText(f"Downloads: {total}")
        self.status_active.setText(f"Active: {active}")
        self.status_completed.setText(f"Completed: {completed}")
        
        if active > 0:
            self.statusBar().showMessage("Downloading...")
        elif completed == total and total > 0:
            self.statusBar().showMessage("All downloads completed")
        elif errors > 0:
            self.statusBar().showMessage(f"Completed with {errors} errors")
        else:
            self.statusBar().showMessage("Ready")

    def check_first_run(self):
        settings = QSettings('M3U8ME', 'M3U8StreamDownloader')
        if not settings.value('first_run_complete', False, type=bool):
            reply = QMessageBox.question(
                self,
                "First Run Setup",
                "Would you like to set M3U8ME as the default application for .m3u8 files?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                if FileAssociationHandler.setup_file_associations():
                    QMessageBox.information(
                        self,
                        "Setup Complete",
                        "M3U8ME has been set as the default application for .m3u8 files.",
                        QMessageBox.Ok
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "Setup Failed",
                        "Failed to set up file associations. Try running the application as administrator.",
                        QMessageBox.Ok
                    )
            
            settings.setValue('first_run_complete', True)

    def process_arguments(self):
        args = sys.argv[1:]
        for arg in args:
            if arg.startswith('m3u8me:'):
                url = arg.replace('m3u8me:', '')
                self.add_download(url)
            elif arg.lower().endswith('.m3u8'):
                try:
                    with open(arg, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self.add_download(content)
                except Exception as e:
                    logger.error(f"Failed to open file: {str(e)}")
                    QMessageBox.warning(
                        self,
                        "Error",
                        f"Failed to open file: {str(e)}",
                        QMessageBox.Ok
                    )

    def check_ffmpeg(self):
        if not shutil.which('ffmpeg'):
            QMessageBox.critical(
                self,
                "FFmpeg Not Found",
                "FFmpeg is required but not found on your system. Please install FFmpeg and make sure it's in your system PATH.",
                QMessageBox.Ok
            )
            sys.exit(1)
        
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True
            )
            if 'ffmpeg version' not in result.stdout:
                raise Exception("Invalid FFmpeg installation")
                
            version_line = result.stdout.split('\n')[0]
            logger.info(f"FFmpeg found: {version_line}")
        except Exception as e:
            QMessageBox.warning(
                self,
                "FFmpeg Check Failed",
                f"Error verifying FFmpeg installation: {str(e)}\nSome features may not work correctly.",
                QMessageBox.Ok
            )

    def load_settings(self):
        self.settings_tab.load_settings()

    def save_settings(self):
        self.settings_tab.save_settings()

    def closeEvent(self, event):
        if self.force_quit:
            self.save_settings()
            self.stop_all_downloads()
            event.accept()
        else:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "M3U8ME",
                "Application minimized to tray. Double-click the tray icon to restore.",
                QSystemTrayIcon.Information,
                2000
            )

def handle_new_instance(server, window):
    socket = server.nextPendingConnection()
    if socket.waitForReadyRead(1000):
        data = socket.readAll().data().decode()
        if data:
            args = data.split()
            window.process_arguments(args)
        window.show()
        window.activateWindow()

def main():
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    socket = QLocalSocket()
    socket.connectToServer('M3U8ME-SingleInstance')
    
    if socket.waitForConnected(500):
        socket.write(' '.join(sys.argv[1:]).encode())
        socket.waitForBytesWritten()
        sys.exit(0)
    else:
        server = QLocalServer()
        server.listen('M3U8ME-SingleInstance')
        
    try:
        CustomStyle.apply_dark_theme(app)
        window = M3U8StreamDownloader()
        
        if server:
            server.newConnection.connect(lambda: handle_new_instance(server, window))
            
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        QMessageBox.critical(
            None,
            "Fatal Error",
            f"An unexpected error occurred:\n\n{str(e)}\n\nThe application will now close.",
            QMessageBox.Ok
        )
        sys.exit(1)

if __name__ == '__main__':
    main()
