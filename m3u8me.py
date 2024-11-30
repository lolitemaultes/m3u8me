#!/usr/bin/env python3

import aiohttp
import asyncio
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

import sys
import os
import json
import re
import queue
import time
import logging
import tempfile
import shutil
import threading
import concurrent.futures
import threading
import subprocess
import importlib.util
import undetected_chromedriver as uc
from datetime import datetime
from collections import deque
from urllib.parse import urljoin, urlparse, quote, quote_plus, urlencode
from pathlib import Path
from queue import Queue

import requests
import m3u8
import psutil
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QProgressBar, QFileDialog, QMessageBox, QTabWidget,
    QComboBox, QSpinBox, QCheckBox, QGridLayout, QScrollArea, QFrame,
    QGroupBox, QStyle, QStyleFactory, QToolTip, QSystemTrayIcon, QMenu, QStackedLayout, QSizePolicy
)
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QSize, QTimer, QSettings
)
from PyQt5.QtNetwork import QLocalSocket, QLocalServer
from PyQt5.QtGui import QPalette, QColor, QFont, QIcon, QPixmap

# Add the function here
def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

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

class RateLimiter:
    def __init__(self, max_per_second=2):
        self.delay = 1.0 / max_per_second
        self.last_call = 0
        self.lock = threading.Lock()
        
    def wait(self):
        with self.lock:
            elapsed = time.time() - self.last_call
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            self.last_call = time.time()

rate_limiter = RateLimiter(max_per_second=2)

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
        
        # Dark theme color palette
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(28, 28, 28))
        dark_palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.Base, QColor(35, 35, 35))
        dark_palette.setColor(QPalette.AlternateBase, QColor(42, 42, 42))
        dark_palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.Text, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.Button, QColor(45, 45, 45))
        dark_palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
        dark_palette.setColor(QPalette.Link, QColor(66, 133, 244))
        dark_palette.setColor(QPalette.Highlight, QColor(66, 133, 244))
        dark_palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        
        app.setPalette(dark_palette)
        
        # Enhanced stylesheet with modern, clean design
        app.setStyleSheet("""
            QMainWindow {
                background-color: #1c1c1c;
            }
            
            /* Main container styling */
            QWidget {
                margin: 0;
                padding: 0;
            }
            
            /* Group box styling */
            QGroupBox {
                border: 1px solid #3d3d3d;
                border-radius: 8px;
                margin-top: 1.5em;
                padding: 15px;
                background-color: #2a2a2a;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 5px;
                color: #ffffff;
                font-weight: bold;
            }
            
            /* Button styling */
            QPushButton {
                background-color: #2fd492;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                min-width: 100px;
                margin: 2px;
            }
            
            QPushButton:hover {
                background-color: #25a270;
            }
            
            QPushButton:pressed {
                background-color: #1c8159;
            }
            
            QPushButton:disabled {
                background-color: #383838;
                color: #888888;
            }
            
            /* Input field styling */
            QLineEdit {
                padding: 8px;
                border-radius: 6px;
                border: 1px solid #3d3d3d;
                background-color: #333333;
                color: white;
                selection-background-color: #4285f4;
                margin: 2px;
            }
            
            QLineEdit:focus {
                border: 1px solid #4285f4;
            }
            
            /* Progress bar styling */
            QProgressBar {
                border: none;
                border-radius: 4px;
                background-color: #333333;
                height: 20px;
                text-align: center;
                margin: 2px;
            }
            
            QProgressBar::chunk {
                border-radius: 4px;
                background-color: #4285f4;
            }
            
            /* Tab widget styling */
            QTabWidget::pane {
                border: 1px solid #3d3d3d;
                border-radius: 8px;
                top: -1px;
                background-color: #2a2a2a;
            }
            
            QTabBar::tab {
                background-color: #333333;
                color: white;
                padding: 10px 20px;
                margin: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            
            QTabBar::tab:selected {
                background-color: #4285f4;
            }
            
            QTabBar::tab:hover:!selected {
                background-color: #3d3d3d;
            }
            
            /* Scroll area styling */
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            
            QScrollBar:vertical {
                border: none;
                background-color: #2a2a2a;
                width: 10px;
                margin: 0;
            }
            
            QScrollBar::handle:vertical {
                background-color: #4d4d4d;
                border-radius: 5px;
                min-height: 20px;
            }
            
            QScrollBar::handle:vertical:hover {
                background-color: #5d5d5d;
            }
            
            /* Status bar styling */
            QStatusBar {
                background-color: #252525;
                color: white;
                border-top: 1px solid #3d3d3d;
            }
            
            QStatusBar QLabel {
                padding: 3px 6px;
            }
            
            /* Combobox styling */
            QComboBox {
                padding: 6px;
                border-radius: 6px;
                border: 1px solid #3d3d3d;
                background-color: #333333;
                color: white;
                min-width: 100px;
            }
            
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                margin-right: 5px;
            }
            
            /* Download widget styling */
            DownloadWidget {
                background-color: #2d2d2d;
                border-radius: 8px;
                padding: 12px;
                margin: 8px 4px;
            }
            
            DownloadWidget QLabel {
                color: white;
                font-size: 13px;
            }
            
            /* Logo container styling */
            #logo_container {
                margin: 20px;
                padding: 10px;
                background-color: transparent;
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
        self.max_concurrent_segments = settings.get('max_workers', 30)
        self.session = self._configure_session()
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': 'https://tralvoxmoon.xyz',
            'Referer': 'https://tralvoxmoon.xyz/',
            'Connection': 'keep-alive',
            'Range': 'bytes=0-',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache'
        }

    def _configure_session(self):
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': 'https://tralvoxmoon.xyz',
            'Referer': 'https://tralvoxmoon.xyz/',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
            'TE': 'trailers'
        })
        
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=self.max_concurrent_segments,
            pool_maxsize=self.max_concurrent_segments,
            max_retries=self.retry_count,
            pool_block=False
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def stop(self):
        self.is_running = False

    def run(self):
        try:
            self.temp_dir = tempfile.mkdtemp()
            content = self.url.strip().rstrip(':')
            base_url = None
    
            # Handle direct M3U8 content vs URL
            if content.startswith('#EXTM3U'):
                playlist = m3u8.loads(content)
            else:
                try:
                    response = self.session.get(
                        content,
                        headers=self.headers,
                        verify=False,
                        timeout=30
                    )
                    response.raise_for_status()
                    playlist = m3u8.loads(response.text)
                    base_url = content
                except Exception as e:
                    raise Exception(f"Failed to fetch M3U8: {str(e)}")
    
            # Handle multi-quality streams
            if not playlist.segments and playlist.playlists:
                # Filter and sort playlists by resolution
                available_streams = []
                for p in playlist.playlists:
                    bandwidth = getattr(p.stream_info, 'bandwidth', 0)
                    resolution = getattr(p.stream_info, 'resolution', None)
                    if resolution:
                        width, height = resolution
                        available_streams.append({
                            'uri': p.uri,
                            'resolution': f"{width}x{height}",
                            'height': height,
                            'bandwidth': bandwidth
                        })
                    elif bandwidth:
                        available_streams.append({
                            'uri': p.uri,
                            'resolution': f"Bandwidth: {bandwidth//1000}kbps",
                            'height': 0,
                            'bandwidth': bandwidth
                        })
    
                if not available_streams:
                    raise Exception("No valid streams found in playlist")
    
                # Sort by height and bandwidth
                available_streams.sort(key=lambda x: (x['height'], x['bandwidth']), reverse=True)
    
                # Quality selection based on settings
                quality = self.settings.get('quality', 'Super Duper!')
                if quality == 'Super Duper!':
                    selected_stream = next(
                        (s for s in available_streams if s['height'] == 1080), 
                        available_streams[0]
                    )
                elif quality == 'WTF!!?':
                    selected_stream = available_streams[-1]
                else:  # Ehh...
                    selected_stream = available_streams[len(available_streams)//2]
    
                # Resolve the playlist URL
                selected_url = selected_stream['uri']
                if not selected_url.startswith('http'):
                    if base_url:
                        base_path = '/'.join(base_url.split('/')[:-1])
                        selected_url = f"{base_path}/{selected_url}"
                    else:
                        raise Exception("Cannot resolve relative URL for non-HTTP playlist")
    
                # Fetch the selected quality playlist
                try:
                    response = self.session.get(
                        selected_url,
                        headers=self.headers,
                        verify=False,
                        timeout=30
                    )
                    response.raise_for_status()
                    playlist = m3u8.loads(response.text)
                    base_url = selected_url
                except Exception as e:
                    raise Exception(f"Failed to fetch quality stream: {str(e)}")
    
            if not playlist.segments:
                raise Exception("No segments found in the final playlist")
    
            # Prepare segment download queue and tracking
            segment_queue = queue.Queue()
            results = {}
            failed_segments = set()
            download_errors = []
            completed_segments = 0
            
            # Thread-safe counter using Lock
            counter_lock = threading.Lock()
            
            def increment_counter():
                nonlocal completed_segments
                with counter_lock:
                    completed_segments += 1
                    return completed_segments
    
            # Populate queue
            for i, segment in enumerate(playlist.segments):
                segment_url = segment.uri
                if not segment_url.startswith('http'):
                    if base_url:
                        base_path = '/'.join(base_url.split('/')[:-1])
                        segment_url = f"{base_path}/{segment_url}"
                    
                output_path = os.path.join(self.temp_dir, f"segment_{i:05d}.ts")
                segment_queue.put((i, segment_url, output_path))
                results[i] = None
    
            total_segments = len(playlist.segments)
            max_workers = min(self.max_concurrent_segments, total_segments)
            active_workers = threading.Event()
            active_workers.set()
    
            def download_worker():
                while active_workers.is_set():
                    try:
                        try:
                            i, segment_url, output_path = segment_queue.get(timeout=1)
                        except queue.Empty:
                            continue
            
                        try:
                            if self.download_segment_with_retry(segment_url, output_path):
                                results[i] = output_path
                                current_completed = increment_counter()
            
                                progress = min(int((current_completed / total_segments) * 80), 79)
                                self.progress_updated.emit(
                                    self.url,
                                    progress,
                                    f"Downloading segments... {current_completed}/{total_segments} ({max_workers} threads)"
                                )
                            else:
                                with counter_lock:
                                    failed_segments.add(i)
                                    download_errors.append(f"Segment {i}: Download cancelled")
            
                        except Exception as e:
                            with counter_lock:
                                failed_segments.add(i)
                                download_errors.append(f"Segment {i}: {str(e)}")
            
                        finally:
                            segment_queue.task_done()
            
                    except Exception as e:
                        logger.error(f"Worker thread error: {str(e)}")
                        continue
    
            # Start worker threads
            threads = []
            for _ in range(max_workers):
                thread = threading.Thread(target=download_worker)
                thread.daemon = True
                thread.start()
                threads.append(thread)
    
            # Wait for downloads to complete
            while active_workers.is_set():
                total_processed = completed_segments + len(failed_segments)
                if total_processed >= total_segments:
                    break
                if not self.is_running:
                    active_workers.clear()
                    break
                time.sleep(0.5)
    
            # Clean shutdown
            active_workers.clear()
            for thread in threads:
                thread.join(timeout=2)
    
            if not self.is_running:
                raise Exception("Download cancelled by user")
    
            if failed_segments:
                raise Exception(f"Failed to download {len(failed_segments)} segments:\n" + 
                              "\n".join(download_errors[:5]) +
                              (f"\n... and {len(download_errors) - 5} more errors" if len(download_errors) > 5 else ""))
    
            # Get ordered list of segment files
            segment_files = [results[i] for i in range(total_segments) if i not in failed_segments]
    
            if not segment_files:
                raise Exception("No segments were downloaded successfully")
    
            # Combine segments
            self.progress_updated.emit(self.url, 80, "Combining segments...")
            if not self.combine_segments(segment_files, os.path.join(self.save_path, "output")):
                raise Exception("Failed to combine segments")
    
            self.progress_updated.emit(self.url, 100, "Download complete!")
            self.download_complete.emit(self.url)
    
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            self.download_error.emit(self.url, str(e))
        finally:
            if self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir, ignore_errors=True)
                except:
                    pass

    def download_segment_with_retry(self, url, output_path):
        domains = ['tralvoxmoon.xyz', 'velloxfire.pro']
        rate_limiter = RateLimiter(max_per_second=2)
        
        for attempt in range(self.retry_count):
            try:
                rate_limiter.wait()
                
                for domain in domains:
                    current_url = url.replace(urlparse(url).netloc, domain)
                    
                    if attempt > 0:
                        time.sleep(1 * (2 ** (attempt - 1)))
                    
                    response = self.session.get(
                        current_url,
                        verify=False,
                        timeout=30,
                        stream=True
                    )
                    
                    if response.status_code == 200:
                        with open(output_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if not self.is_running:
                                    return False
                                if chunk:
                                    f.write(chunk)
                        return True
                        
            except Exception as e:
                if attempt == self.retry_count - 1:
                    raise e
                continue
                
        raise Exception(f"Failed to download segment after {self.retry_count} attempts")

    def combine_segments(self, segment_files, output_file):
        try:
            if not shutil.which('ffmpeg'):
                raise Exception("FFmpeg not found. Please install FFmpeg to continue.")
    
            output_format = self.settings.get('output_format', 'mp4')
            quality = self.settings.get('quality', 'Super Duper!')
            temp_file = os.path.join(self.temp_dir, f"temp_fixed.ts")
            output_file = f"{output_file}.{output_format}"
    
            # STEP 1: Concatenate segments
            self.progress_updated.emit(self.url, 80, "Combining segments...")
            
            with open(temp_file, 'wb') as outfile:
                for i, segment in enumerate(segment_files):
                    if not self.is_running:
                        return False
                    with open(segment, 'rb') as infile:
                        outfile.write(infile.read())
                    progress = min(80 + int((i / len(segment_files)) * 10), 89)
                    self.progress_updated.emit(self.url, progress, f"Combining segments... {progress}%")
    
            # STEP 2: Convert with optimized settings
            self.progress_updated.emit(self.url, 90, "Processing video...")
    
            # Determine encoding settings based on quality
            if quality == 'Super Duper!':
                preset = 'veryfast'  # Changed from slow/medium for better speed
                crf = '20'
            elif quality == 'WTF!!?':
                preset = 'ultrafast'
                crf = '28'
            else:  # Ehh...
                preset = 'veryfast'
                crf = '23'
    
            cmd = [
                'ffmpeg', '-y',
                '-fflags', '+genpts+igndts',
                '-i', temp_file,
                '-c:v', 'libx264',
                '-preset', preset,
                '-crf', crf,
                '-c:a', 'aac',
                '-movflags', '+faststart',
                '-progress', 'pipe:1',  # Output progress to stdout
                output_file
            ]
    
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
    
            start_time = time.time()
            timeout = 1800  # 30 minute timeout
            last_progress_time = time.time()
            progress_timeout = 300  # 5 minute progress timeout
            last_frame = 0
            total_duration = None
    
            while True:
                if not self.is_running:
                    process.terminate()
                    return False
    
                # Check timeouts
                current_time = time.time()
                if current_time - start_time > timeout:
                    process.terminate()
                    raise Exception("Processing timeout exceeded (30 minutes)")
                if current_time - last_progress_time > progress_timeout:
                    process.terminate()
                    raise Exception("No progress detected for 5 minutes")
    
                # Check if process completed
                retcode = process.poll()
                if retcode is not None:
                    if retcode != 0:
                        _, stderr = process.communicate()
                        raise Exception(f"FFmpeg error: {stderr}")
                    break
    
                # Read progress
                output = process.stdout.readline()
                if not output:
                    continue
    
                if 'frame=' in output:
                    last_progress_time = current_time
                    try:
                        frame = int(output.split('frame=')[1].split()[0])
                        if frame > last_frame:  # Only update progress if frame count increased
                            last_frame = frame
                            # Cap progress at 99% until fully complete
                            progress = min(90 + int((frame / 1000) * 9), 99)
                            self.progress_updated.emit(
                                self.url, 
                                progress,
                                f"Processing video... (Frame {frame})"
                            )
                    except:
                        pass
    
                time.sleep(0.1)  # Prevent CPU overuse
    
            # Final verification
            if not os.path.exists(output_file):
                raise Exception("Output file was not created")
                
            if os.path.getsize(output_file) < 1000:
                raise Exception("Output file is too small - likely corrupted")
    
            self.progress_updated.emit(self.url, 100, "Processing complete!")
            return True
    
        except Exception as e:
            logger.error(f"Error combining segments: {str(e)}")
            raise  # Re-raise to handle in calling function
            
        finally:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass

class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plugin_manager = PluginManager()
        self.original_settings = {}
        self.init_ui()
        self.load_settings()  # Load initial settings
        self.save_original_settings()  # Save initial state

    def init_ui(self):
        # Create a scroll area to contain everything
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # Main container widget that will go inside scroll area
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        
        # Video Settings
        video_group = QGroupBox("Video Settings")
        video_layout = QGridLayout()
        
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(['Super Duper!', 'Ehh...', 'WTF!!?'])
        video_layout.addWidget(QLabel("Quality:"), 0, 0)
        video_layout.addWidget(self.quality_combo, 0, 1)
        
        self.format_combo = QComboBox()
        self.format_combo.addItems(['mp4', 'mkv', 'ts'])
        video_layout.addWidget(QLabel("Output Format:"), 1, 0)
        video_layout.addWidget(self.format_combo, 1, 1)
        
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(['Standard', 'High Quality', 'Small Size'])
        video_layout.addWidget(QLabel("Quality Preset:"), 2, 0)
        video_layout.addWidget(self.preset_combo, 2, 1)
        
        video_group.setLayout(video_layout)
        layout.addWidget(video_group)

        # Download Settings
        download_group = QGroupBox("Download Settings")
        download_layout = QGridLayout()
        
        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, 30)
        self.thread_spin.setValue(16)
        download_layout.addWidget(QLabel("Download Threads:"), 0, 0)
        download_layout.addWidget(self.thread_spin, 0, 1)
        
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 120)
        self.timeout_spin.setValue(50)
        download_layout.addWidget(QLabel("Segment Timeout (s):"), 1, 0)
        download_layout.addWidget(self.timeout_spin, 1, 1)
        
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 5)
        self.retry_spin.setValue(5)
        download_layout.addWidget(QLabel("Retry Attempts:"), 2, 0)
        download_layout.addWidget(self.retry_spin, 2, 1)
        
        self.concurrent_check = QCheckBox("Download Streams Concurrently")
        self.concurrent_check.setChecked(False)
        download_layout.addWidget(self.concurrent_check, 3, 0, 1, 2)
        
        download_group.setLayout(download_layout)
        layout.addWidget(download_group)

        # Plugin Management
        plugin_group = QGroupBox("Plugin Management")
        plugin_layout = QVBoxLayout()
        
        button_layout = QHBoxLayout()
        install_btn = QPushButton("Install Plugin")
        install_btn.clicked.connect(self.install_plugin)
        refresh_btn = QPushButton("Refresh Plugins")
        refresh_btn.clicked.connect(self.refresh_plugins)
        button_layout.addWidget(install_btn)
        button_layout.addWidget(refresh_btn)
        plugin_layout.addLayout(button_layout)
        
        self.plugin_list = QScrollArea()
        self.plugin_list.setWidgetResizable(True)
        self.plugin_list_widget = QWidget()
        self.plugin_list_layout = QVBoxLayout(self.plugin_list_widget)
        self.plugin_list.setWidget(self.plugin_list_widget)
        plugin_layout.addWidget(self.plugin_list)
        
        plugin_group.setLayout(plugin_layout)
        layout.addWidget(plugin_group)

        # Output Settings
        output_group = QGroupBox("Output Settings")
        output_layout = QVBoxLayout()
        
        self.auto_rename_check = QCheckBox("Auto-rename on conflict")
        self.auto_rename_check.setChecked(True)
        output_layout.addWidget(self.auto_rename_check)
        
        self.preserve_source_check = QCheckBox("Preserve source quality")
        self.preserve_source_check.setChecked(True)
        output_layout.addWidget(self.preserve_source_check)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # Apply Button
        button_layout = QHBoxLayout()
        self.apply_btn = QPushButton("Apply Changes")
        self.apply_btn.clicked.connect(self.apply_settings)
        self.apply_btn.setEnabled(False)
        button_layout.addStretch()
        button_layout.addWidget(self.apply_btn)
        layout.addLayout(button_layout)

        # Put the container in the scroll area
        scroll.setWidget(container)
        
        # Main layout for the tab
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll)
        
        self.refresh_plugins()

    def apply_preset(self, preset):
        if preset == 'High Quality':
            self.quality_combo.setCurrentText('Super Duper!')
            self.format_combo.setCurrentText('mkv')
            self.preserve_source_check.setChecked(True)
        elif preset == 'Small Size':
            self.quality_combo.setCurrentText('Ehh...')
            self.format_combo.setCurrentText('mp4')
            self.preserve_source_check.setChecked(False)
        else:  # Standard
            self.quality_combo.setCurrentText('Super Duper!')
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
            widget = self.plugin_list_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        
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

    def check_settings_changed(self):
        """Check if current settings differ from original"""
        current_settings = self.get_settings()
        self.apply_btn.setEnabled(current_settings != self.original_settings)

    def save_original_settings(self):
        """Save the current settings as original state"""
        self.original_settings = self.get_settings()

    def apply_settings(self):
        """Apply the current settings"""
        self.save_settings()
        self.save_original_settings()
        self.apply_btn.setEnabled(False)
        QMessageBox.information(
            self,
            "Settings Applied",
            "Settings have been applied successfully.",
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
            'preserve_source': self.preserve_source_check.isChecked(),
            'preset': self.preset_combo.currentText()
        }

    def save_settings(self):
        settings = self.get_settings()
        try:
            with open('m3u8_settings.json', 'w') as f:
                json.dump(settings, f)
        except Exception as e:
            logger.error(f"Error saving settings: {str(e)}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save settings: {str(e)}",
                QMessageBox.Ok
            )

    def load_settings(self):
        try:
            with open('m3u8_settings.json', 'r') as f:
                settings = json.load(f)
                
            self.quality_combo.setCurrentText(settings.get('quality', 'Super Duper!'))
            self.format_combo.setCurrentText(settings.get('output_format', 'mp4'))
            self.thread_spin.setValue(settings.get('max_workers', 4))
            self.timeout_spin.setValue(settings.get('segment_timeout', 30))
            self.retry_spin.setValue(settings.get('retry_attempts', 3))
            self.concurrent_check.setChecked(settings.get('concurrent_downloads', False))
            self.auto_rename_check.setChecked(settings.get('auto_rename', True))
            self.preserve_source_check.setChecked(settings.get('preserve_source', True))
            self.preset_combo.setCurrentText(settings.get('preset', 'Standard'))
        except:
            # If settings file doesn't exist or is invalid, use defaults
            pass

class SearchWorker(QThread):
    resultFound = pyqtSignal(dict)
    searchComplete = pyqtSignal()
    searchError = pyqtSignal(str)
    progressUpdate = pyqtSignal(int, int)  # current, total

    def __init__(self, query):
        super().__init__()
        self.query = query
        self.is_running = True

    def run(self):
        try:
            self.temp_dir = tempfile.mkdtemp()
    
            # Clean up the input
            content = self.url.strip().rstrip(':')
            
            # Parse the M3U8 content
            try:
                playlist = m3u8.loads(content)
            except Exception as e:
                raise Exception(f"Failed to parse M3U8: {str(e)}")
    
            # Handle multi-quality streams
            if not playlist.segments and playlist.playlists:
                # Filter and sort playlists by resolution
                available_streams = []
                for p in playlist.playlists:
                    if hasattr(p.stream_info, 'resolution'):
                        width, height = p.stream_info.resolution
                        bandwidth = p.stream_info.bandwidth
                        available_streams.append({
                            'playlist': p,
                            'resolution': f"{width}x{height}",
                            'height': height,
                            'bandwidth': bandwidth,
                            'uri': p.uri
                        })
    
                # Sort by height and bandwidth (for same resolution)
                available_streams.sort(key=lambda x: (x['height'], x['bandwidth']), reverse=True)
    
                # Quality selection based on settings
                quality = self.settings.get('quality', 'best')
                selected_stream = None
    
                if quality == 'best':
                    # Look specifically for 1080p first
                    for stream in available_streams:
                        if stream['height'] == 1080:
                            selected_stream = stream
                            break
                    # If no 1080p, take the highest available
                    if not selected_stream and available_streams:
                        selected_stream = available_streams[0]
                elif quality == 'worst':
                    selected_stream = available_streams[-1]
                else:  # medium
                    selected_stream = available_streams[len(available_streams)//2]
    
                if not selected_stream:
                    raise Exception("No suitable quality stream found")
    
                selected_url = selected_stream['uri']
                resolution = selected_stream['resolution']
                
                self.progress_updated.emit(
                    self.url, 
                    0, 
                    f"Selected quality: {resolution} ({selected_stream['bandwidth'] // 1000}kbps)"
                )
    
                try:
                    response = self.session.get(
                        selected_url,
                        headers=self.headers,
                        verify=False,
                        timeout=30
                    )
                    response.raise_for_status()
                    playlist = m3u8.loads(response.text)
                except Exception as e:
                    raise Exception(f"Failed to fetch quality stream: {str(e)}")
    
            if not playlist.segments:
                raise Exception("No segments found in playlist")
    
            # Download segments
            segment_files = []
            total_segments = len(playlist.segments)
            
            for i, segment in enumerate(playlist.segments):
                if not self.is_running:
                    raise Exception("Download cancelled by user")
    
                output_path = os.path.join(self.temp_dir, f"segment_{i:05d}.ts")
                segment_url = segment.uri
    
                # Ensure segment URL is absolute
                if not segment_url.startswith('http'):
                    base_url = os.path.dirname(selected_url) if 'selected_url' in locals() else ''
                    segment_url = f"{base_url}/{segment_url}" if base_url else segment_url
    
                try:
                    response = self.session.get(
                        segment_url,
                        headers=self.headers,
                        verify=False,
                        timeout=30
                    )
                    response.raise_for_status()
                    
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                    
                    segment_files.append(output_path)
                    progress = min(int((i / total_segments) * 80), 79)
                    self.progress_updated.emit(
                        self.url,
                        progress,
                        f"Downloading {resolution} segments... {i+1}/{total_segments}"
                    )
                    
                except Exception as e:
                    raise Exception(f"Failed to download segment {i+1}: {str(e)}")
    
            # Combine segments into intermediate file
            self.progress_updated.emit(self.url, 80, "Combining segments...")
            intermediate_file = os.path.join(self.temp_dir, "intermediate.ts")
            
            with open(intermediate_file, 'wb') as outfile:
                for segment_file in segment_files:
                    with open(segment_file, 'rb') as infile:
                        outfile.write(infile.read())
    
            # Convert to desired format while preserving quality
            self.progress_updated.emit(self.url, 90, f"Converting {resolution} video to final format...")
            
            output_format = self.settings.get('output_format', 'mp4')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            quality_info = f"_{resolution}"
            output_file = os.path.join(self.save_path, f"video_{timestamp}{quality_info}.{output_format}")
    
            # High quality conversion
            cmd = [
                'ffmpeg', '-y',
                '-i', intermediate_file,
                '-c:v', 'copy',         # Copy video stream to preserve quality
                '-c:a', 'aac',          # Convert audio to AAC for compatibility
                '-b:a', '384k',         # High quality audio
                '-movflags', '+faststart',  # Enable streaming
                '-metadata', f'resolution={resolution}',  # Add resolution to metadata
                output_file
            ]
    
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
    
            if process.returncode != 0:
                raise Exception(f"Failed to convert video: {process.stderr}")
    
            # Verify the output file
            if not os.path.exists(output_file) or os.path.getsize(output_file) < 1000:
                raise Exception("Output file is invalid")
    
            self.progress_updated.emit(self.url, 100, f"Download complete! ({resolution})")
            self.download_complete.emit(self.url)
    
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            self.download_error.emit(self.url, str(e))
        finally:
            if self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir, ignore_errors=True)
                except:
                    pass

class M3U8StreamDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        # Initialize all instance variables first
        self.force_quit = False
        self.setWindowTitle("M3U8 Stream Downloader")
        self.setMinimumSize(900, 700)
        self.active_downloads = {}
        self.save_path = None
        
        # Create UI elements
        self.url_input = QLineEdit()
        self.downloads_area = QScrollArea()
        self.downloads_widget = QWidget()
        self.downloads_layout = QVBoxLayout(self.downloads_widget)
        
        # Initialize buttons
        self.start_all_btn = QPushButton("Start All")
        self.stop_all_btn = QPushButton("Stop All")
        self.clear_completed_btn = QPushButton("Clear Completed")
        self.add_url_btn = QPushButton("Add URL")
        self.bulk_upload_btn = QPushButton("Bulk Upload")
        
        # Initialize tabs
        self.download_tab = QWidget()
        self.settings_tab = SettingsTab()
        self.tab_widget = QTabWidget()
        
        # Status labels
        self.status_downloads = QLabel("Downloads: 0")
        self.status_active = QLabel("Active: 0")
        self.status_completed = QLabel("Completed: 0")
        
        # Then create the UI
        self.init_ui()
        self.setup_status_bar()
        self.tray_icon = SystemTrayApp(self)
        
        # Finally, do system checks and load settings
        self.check_first_run()
        self.process_arguments()
        self.load_settings()
        self.check_ffmpeg()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(15)

        # Logo container
        logo_container = QWidget()
        logo_container.setObjectName("logo_container")
        logo_container.setFixedHeight(120)
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 10, 0, 10)
        
        logo_label = QLabel()
        try:
            logo_pixmap = QPixmap(get_resource_path("Resources/m3u8me.png"))
            scaled_pixmap = logo_pixmap.scaled(480, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
        except:
            logo_label.setText("M3U8ME")
            logo_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #4285f4;")
        
        logo_label.setAlignment(Qt.AlignCenter)
        logo_layout.addStretch()
        logo_layout.addWidget(logo_label)
        logo_layout.addStretch()
        
        layout.addWidget(logo_container)

        # Set up URL input
        self.url_input.setPlaceholderText("URLs go here, or you can piss off and bulk upload...")
        self.url_input.returnPressed.connect(self.add_url_from_input)

        # Initialize tabs
        self.init_download_tab()
        self.tab_widget.addTab(self.download_tab, "Downloads")
        self.tab_widget.addTab(self.settings_tab, "Settings")
        
        layout.addWidget(self.tab_widget)

        # Connect button signals
        self.start_all_btn.clicked.connect(self.start_all_downloads)
        self.stop_all_btn.clicked.connect(self.stop_all_downloads)
        self.clear_completed_btn.clicked.connect(self.clear_completed_downloads)
        self.add_url_btn.clicked.connect(self.add_url_from_input)
        self.bulk_upload_btn.clicked.connect(self.bulk_upload)

        # Set initial button states
        self.start_all_btn.setEnabled(False)
        self.stop_all_btn.setEnabled(False)

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

    def init_download_tab(self):
        layout = QVBoxLayout(self.download_tab)

        # URL input area
        url_group = QGroupBox("Add Stream")
        url_layout = QHBoxLayout()
        
        self.url_input.setPlaceholderText("URLs go here, or you can piss off and bulk upload...")
        self.url_input.returnPressed.connect(self.add_url_from_input)
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.add_url_btn)
        url_layout.addWidget(self.bulk_upload_btn)
        
        url_group.setLayout(url_layout)
        layout.addWidget(url_group)

        # Downloads area
        downloads_group = QGroupBox("Downloads")
        downloads_layout = QVBoxLayout()
        
        self.downloads_area.setWidgetResizable(True)
        self.downloads_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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

        settings = self.settings_tab.get_settings()
        
        worker = StreamDownloader(url, self.save_path, settings)
        worker.progress_updated.connect(self.update_progress)
        worker.download_complete.connect(self.download_finished)
        worker.download_error.connect(self.download_error)
        
        self.active_downloads[url].update({
            'worker': worker,
            'status': 'downloading'})
        
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

    def process_arguments(self, args=None):
        if args is None:
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
