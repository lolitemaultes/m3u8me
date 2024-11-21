#!/usr/bin/env python3

import sys
import os
import json
import re
import time
from datetime import datetime
import logging
import tempfile
import shutil
import concurrent.futures
from urllib.parse import urljoin, urlparse
import subprocess
import requests
import m3u8
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QProgressBar, QFileDialog, QMessageBox, QTabWidget,
    QComboBox, QSpinBox, QCheckBox, QGridLayout, QScrollArea, QFrame,
    QGroupBox, QStyle, QStyleFactory
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QPalette, QColor, QFont

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_base_url(url, parsed_url):
    """Get the correct base URL for segment resolution."""
    # If the URL starts with a fragment identifier, use the parent URL
    if url.startswith('#'):
        return parsed_url.scheme + '://' + parsed_url.netloc + os.path.dirname(parsed_url.path) + '/'
    
    # If it's a full URL, get its directory
    if url.startswith('http'):
        return os.path.dirname(url) + '/'
    
    # Otherwise, assume it's relative to the parent URL
    return parsed_url.scheme + '://' + parsed_url.netloc + os.path.dirname(parsed_url.path) + '/'

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
        
        # Set stylesheet for custom styling
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
            }
            QProgressBar {
                border: 1px solid #666666;
                border-radius: 3px;
                text-align: center;
                height: 20px;
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
            }
            QTabBar::tab {
                background-color: #424242;
                color: white;
                padding: 8px 20px;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
            }
            QTabBar::tab:selected {
                background-color: #2979ff;
            }
            QCheckBox {
                color: white;
            }
            QCheckBox::indicator {
                width: 13px;
                height: 13px;
            }
            QCheckBox::indicator:unchecked {
                border: 1px solid #666666;
                background-color: #424242;
            }
            QCheckBox::indicator:checked {
                border: 1px solid #2979ff;
                background-color: #2979ff;
            }
        """)

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
        """)
        
        # URL and status layout
        info_layout = QVBoxLayout()
        
        self.url_label = QLabel(self.url[:50] + '...' if len(self.url) > 50 else self.url)
        self.url_label.setToolTip(self.url)
        self.url_label.setStyleSheet("font-weight: bold;")
        
        self.status_label = QLabel("Waiting...")
        self.status_label.setStyleSheet("color: #2979ff;")
        
        info_layout.addWidget(self.url_label)
        info_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignCenter)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedWidth(80)
        
        layout.addLayout(info_layout, stretch=2)
        layout.addWidget(self.progress_bar, stretch=3)
        layout.addWidget(self.cancel_btn)
        
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
        self.session = requests.Session()
        self.temp_dir = None
        self.retry_count = settings.get('retry_attempts', 3)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }

    def download_segment(self, segment_url, output_path, index, total):
        """Download a single segment with basic verification."""
        try:
            # Handle different URL formats
            if segment_url.startswith('//'):
                segment_url = 'https:' + segment_url
            elif not segment_url.startswith('http'):
                if not segment_url.startswith('/'):
                    segment_url = '/' + segment_url
                parsed_parent = urlparse(self.url)
                segment_url = f"{parsed_parent.scheme}://{parsed_parent.netloc}{segment_url}"

            response = self.session.get(
                segment_url,
                headers=self.headers,
                timeout=self.settings.get('segment_timeout', 30),
                verify=False  # Sometimes needed for certain CDNs
            )
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            if os.path.getsize(output_path) < 100:
                return False
                
            progress = int((index + 1) / total * 90)
            self.progress_updated.emit(
                self.url,
                progress,
                f"Downloading segment {index + 1}/{total}"
            )
            return True
        except Exception as e:
            logger.error(f"Error downloading segment {index + 1}: {str(e)}")
            return False

    def run(self):
        try:
            self.temp_dir = tempfile.mkdtemp()
            
            # Parse the initial URL
            parsed_url = urlparse(self.url)
            
            # Handle direct M3U8 content
            if self.url.startswith('#EXTM3U'):
                content = self.url
            else:
                # Get the playlist content
                response = self.session.get(
                    self.url,
                    headers=self.headers,
                    verify=False  # Sometimes needed for certain CDNs
                )
                response.raise_for_status()
                content = response.text

            playlist = m3u8.loads(content)
            
            # Handle master playlist
            if not playlist.segments and playlist.playlists:
                # Sort playlists by bandwidth
                playlists = sorted(
                    playlist.playlists,
                    key=lambda p: p.stream_info.bandwidth if p.stream_info else 0
                )
                
                if self.settings['quality'] == 'best':
                    selected_playlist = playlists[-1]
                elif self.settings['quality'] == 'worst':
                    selected_playlist = playlists[0]
                else:  # medium
                    selected_playlist = playlists[len(playlists)//2]
                
                # Get the selected playlist URL
                playlist_url = selected_playlist.uri
                if not playlist_url.startswith('http'):
                    base_url = get_base_url(self.url, parsed_url)
                    playlist_url = urljoin(base_url, playlist_url)
                
                # Get the media playlist
                response = self.session.get(playlist_url, headers=self.headers, verify=False)
                response.raise_for_status()
                playlist = m3u8.loads(response.text)
                # Update base URL for segments
                parsed_url = urlparse(playlist_url)

            if not playlist.segments:
                raise Exception("No segments found in playlist")

            # Get the correct base URL for segments
            base_url = get_base_url(self.url, parsed_url)
            
            # Download segments
            segment_files = []
            downloaded_segments = set()
            total_segments = len(playlist.segments)
            
            self.progress_updated.emit(self.url, 0, f"Starting download of {total_segments} segments")
            
            for i, segment in enumerate(playlist.segments):
                if not self.is_running:
                    raise Exception("Download cancelled")

                output_path = os.path.join(
                    self.temp_dir,
                    f"segment_{i:05d}.ts"
                )
                segment_files.append(output_path)
                
                # Handle different segment URI formats
                segment_url = urljoin(base_url, segment.uri)
                
                # Try to download segment with retries
                success = False
                for attempt in range(self.retry_count):
                    if self.download_segment(segment_url, output_path, i, total_segments):
                        success = True
                        downloaded_segments.add(i)
                        break
                    elif attempt < self.retry_count - 1:
                        time.sleep(1)
                
                if not success:
                    raise Exception(f"Failed to download segment {i + 1} after {self.retry_count} attempts")

            if len(downloaded_segments) != total_segments:
                raise Exception(f"Missing segments. Downloaded {len(downloaded_segments)}/{total_segments}")

            # Combine segments
            self.progress_updated.emit(self.url, 90, "Processing video...")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(
                self.save_path,
                f"video_{timestamp}"
            )
            
            if self.combine_segments(segment_files, output_file):
                self.download_complete.emit(self.url)
            else:
                raise Exception("Failed to process video")

        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            self.download_error.emit(self.url, str(e))
        finally:
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)

    def combine_segments(self, segment_files, output_file):
        """Combine segments into final video file with improved smoothness."""
        try:
            if not shutil.which('ffmpeg'):
                raise Exception("FFmpeg not found. Please install FFmpeg to continue.")
    
            # Create concat file
            concat_file = os.path.join(self.temp_dir, 'concat.txt')
            with open(concat_file, 'w', encoding='utf-8') as f:
                for segment in segment_files:
                    f.write(f"file '{segment}'\n")
    
            output_format = self.settings.get('output_format', 'mp4')
            output_file = f"{output_file}.{output_format}"
    
            # Single pass with optimized parameters
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c:v', 'libx264',      # Use H.264 codec
                '-preset', 'medium',     # Balance between speed and quality
                '-crf', '23',           # Constant rate factor (18-28 is good, lower is better quality)
                '-c:a', 'aac',          # AAC audio codec
                '-b:a', '192k',         # Higher audio bitrate for better quality
                '-vsync', 'cfr',        # Constant frame rate
                '-maxrate', '5000k',    
                '-bufsize', '10000k',
                '-movflags', '+faststart',
                '-profile:v', 'high',
                '-level', '4.1',
                '-vf', 'format=yuv420p'  # Ensure compatibility
            ]
    
            # Add format-specific optimizations
            if output_format == 'mp4':
                cmd.extend([
                    '-tune', 'film',     # Optimize for video content
                    '-map', '0:v:0',     # Map first video stream
                    '-map', '0:a:0?',    # Map first audio stream if it exists
                ])
            elif output_format == 'mkv':
                cmd.extend([
                    '-map', '0',         # Map all streams for MKV
                ])
    
            cmd.append(output_file)
    
            # Run FFmpeg
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
    
            if process.returncode != 0:
                error_msg = process.stderr.strip()
                raise Exception(f"FFmpeg error: {error_msg}")
    
            # Verify the output file
            if not os.path.exists(output_file) or os.path.getsize(output_file) < 1000:
                raise Exception("Output file is missing or too small")
    
            return True
    
        except Exception as e:
            logger.error(f"Error combining segments: {str(e)}")
            return False

    def stop(self):
        self.is_running = False

class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Video Settings
        video_group = QGroupBox("Video Settings")
        video_layout = QGridLayout()
        
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(['best', 'medium', 'worst'])
        video_layout.addWidget(QLabel("Quality:"), 0, 0)
        video_layout.addWidget(self.quality_combo, 0, 1)
        
        self.format_combo = QComboBox()
        self.format_combo.addItems(['mp4', 'ts', 'mkv'])
        video_layout.addWidget(QLabel("Output Format:"), 1, 0)
        video_layout.addWidget(self.format_combo, 1, 1)
        
        video_group.setLayout(video_layout)
        layout.addWidget(video_group)

        # Download Settings
        download_group = QGroupBox("Download Settings")
        download_layout = QGridLayout()
        
        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, 16)
        self.thread_spin.setValue(4)
        download_layout.addWidget(QLabel("Download Threads:"), 0, 0)
        download_layout.addWidget(self.thread_spin, 0, 1)
        
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 120)
        self.timeout_spin.setValue(30)
        download_layout.addWidget(QLabel("Segment Timeout (s):"), 1, 0)
        download_layout.addWidget(self.timeout_spin, 1, 1)
        
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 5)
        self.retry_spin.setValue(3)
        download_layout.addWidget(QLabel("Retry Attempts:"), 2, 0)
        download_layout.addWidget(self.retry_spin, 2, 1)
        
        self.concurrent_check = QCheckBox("Download Streams Concurrently")
        self.concurrent_check.setChecked(False)  # Default to sequential downloads
        download_layout.addWidget(self.concurrent_check, 3, 0, 1, 2)
        
        download_group.setLayout(download_layout)
        layout.addWidget(download_group)

        # Output Settings
        output_group = QGroupBox("Output Settings")
        output_layout = QGridLayout()
        
        self.auto_rename_check = QCheckBox("Auto-rename on conflict")
        self.auto_rename_check.setChecked(True)
        output_layout.addWidget(self.auto_rename_check, 0, 0)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
        
        layout.addStretch()

    def get_settings(self):
        return {
            'quality': self.quality_combo.currentText(),
            'output_format': self.format_combo.currentText(),
            'max_workers': self.thread_spin.value(),
            'segment_timeout': self.timeout_spin.value(),
            'retry_attempts': self.retry_spin.value(),
            'concurrent_downloads': self.concurrent_check.isChecked(),
            'auto_rename': self.auto_rename_check.isChecked()
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
        except:
            pass

class M3U8StreamDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("M3U8 Stream Downloader")
        self.setMinimumSize(900, 700)
        self.active_downloads = {}
        self.save_path = None
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Add header
        header_label = QLabel("M3U8 Stream Downloader")
        header_label.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #2979ff;
            padding: 10px;
        """)
        header_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(header_label)

        # Main content
        self.tab_widget = QTabWidget()
        self.download_tab = QWidget()
        self.settings_tab = SettingsTab()
        
        self.tab_widget.addTab(self.download_tab, "Downloads")
        self.tab_widget.addTab(self.settings_tab, "Settings")
        
        layout.addWidget(self.tab_widget)

        self.init_download_tab()
        self.setup_status_bar()

    def init_download_tab(self):
        layout = QVBoxLayout(self.download_tab)

        # URL input area
        url_group = QGroupBox("Add Stream")
        url_layout = QHBoxLayout()
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter M3U8 stream URL or paste M3U8 content")
        self.url_input.returnPressed.connect(lambda: self.add_download(self.url_input.text()))
        url_layout.addWidget(self.url_input)

        self.add_url_btn = QPushButton("Add URL")
        self.add_url_btn.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        self.add_url_btn.clicked.connect(lambda: self.add_download(self.url_input.text()))
        url_layout.addWidget(self.add_url_btn)

        self.bulk_upload_btn = QPushButton("Bulk Upload")
        self.bulk_upload_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        self.bulk_upload_btn.clicked.connect(self.bulk_upload)
        url_layout.addWidget(self.bulk_upload_btn)
        
        url_group.setLayout(url_layout)
        layout.addWidget(url_group)

        # Downloads area
        downloads_group = QGroupBox("Downloads")
        downloads_layout = QVBoxLayout()
        
        self.downloads_area = QScrollArea()
        self.downloads_area.setWidgetResizable(True)
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
        
        self.start_all_btn = QPushButton("Start All")
        self.start_all_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.start_all_btn.clicked.connect(self.start_all_downloads)
        self.start_all_btn.setEnabled(False)
        button_layout.addWidget(self.start_all_btn)
        
        self.stop_all_btn = QPushButton("Stop All")
        self.stop_all_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
        self.stop_all_btn.clicked.connect(self.stop_all_downloads)
        self.stop_all_btn.setEnabled(False)
        button_layout.addWidget(self.stop_all_btn)
        
        self.clear_completed_btn = QPushButton("Clear Completed")
        self.clear_completed_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        self.clear_completed_btn.clicked.connect(self.clear_completed_downloads)
        button_layout.addWidget(self.clear_completed_btn)
        
        control_group.setLayout(button_layout)
        layout.addWidget(control_group)

    def setup_status_bar(self):
        self.statusBar().showMessage("Ready")
        
        self.status_downloads = QLabel("Downloads: 0")
        self.status_active = QLabel("Active: 0")
        self.status_completed = QLabel("Completed: 0")
        
        self.statusBar().addPermanentWidget(self.status_downloads)
        self.statusBar().addPermanentWidget(self.status_active)
        self.statusBar().addPermanentWidget(self.status_completed)

    def update_status_bar(self):
        total = len(self.active_downloads)
        active = sum(1 for d in self.active_downloads.values() if d['status'] == 'downloading')
        completed = sum(1 for d in self.active_downloads.values() if d['status'] == 'completed')
        
        self.status_downloads.setText(f"Downloads: {total}")
        self.status_active.setText(f"Active: {active}")
        self.status_completed.setText(f"Completed: {completed}")
        
        if active > 0:
            self.statusBar().showMessage("Downloading...")
        elif completed == total and total > 0:
            self.statusBar().showMessage("All downloads completed")
        else:
            self.statusBar().showMessage("Ready")

    def add_download(self, url):
        if not url.strip():
            return

        if url in self.active_downloads:
            QMessageBox.warning(self, "Duplicate URL", "This URL is already in the download queue!")
            return

        download_widget = DownloadWidget(url)
        download_widget.cancel_btn.clicked.connect(lambda: self.remove_download(url))
        
        self.downloads_layout.insertWidget(self.downloads_layout.count() - 1, download_widget)
        self.active_downloads[url] = {
            'widget': download_widget,
            'worker': None,
            'status': 'waiting'
        }

        self.url_input.clear()
        self.start_all_btn.setEnabled(True)
        self.update_status_bar()

    def remove_download(self, url):
        if url in self.active_downloads:
            if self.active_downloads[url]['worker']:
                self.active_downloads[url]['worker'].stop()
            self.active_downloads[url]['widget'].deleteLater()
            del self.active_downloads[url]

        if not self.active_downloads:
            self.start_all_btn.setEnabled(False)
            self.stop_all_btn.setEnabled(False)
            
        self.update_status_bar()

    def bulk_upload(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select M3U8 Files",
            "",
            "M3U8 Files (*.m3u8);;Text Files (*.txt);;All Files (*.*)"
        )
        
        if not file_paths:
            return
            
        # Get save directory once for all files
        self.save_path = QFileDialog.getExistingDirectory(
            self,
            "Select Save Directory",
            options=QFileDialog.ShowDirsOnly
        )
        
        if not self.save_path:
            return
            
        for file_path in file_paths:
            try:
                if file_path.endswith('.txt'):
                    # Handle text files with URLs
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            url = line.strip()
                            if url and (url.startswith('http') or url.startswith('#EXTM3U')):
                                self.add_download(url)
                else:
                    # Handle M3U8 files
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        self.add_download(content)
            except Exception as e:
                logger.error(f"Error reading file {file_path}: {str(e)}")
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Failed to read {file_path}: {str(e)}"
                )

        if self.active_downloads:
            self.start_all_btn.setEnabled(True)
            self.update_status_bar()

    def start_download(self, url):
        if url not in self.active_downloads:
            return

        # Use the pre-selected save path for bulk downloads, or ask for one
        save_path = self.save_path or QFileDialog.getExistingDirectory(
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
        
        self.active_downloads[url]['worker'] = worker
        self.active_downloads[url]['status'] = 'downloading'
        self.active_downloads[url]['widget'].status_label.setText("Downloading...")
        worker.start()
        
        self.update_status_bar()

    def start_all_downloads(self):
        if not self.active_downloads:
            return

        # Get save directory once if not already selected
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
            # Start the first waiting download
            self.start_next_download()

    def start_next_download(self):
        for url in self.active_downloads:
            if self.active_downloads[url]['status'] == 'waiting':
                self.start_download(url)
                break

    def stop_all_downloads(self):
        for download in self.active_downloads.values():
            if download['worker']:
                download['worker'].stop()
                download['status'] = 'stopped'
                download['widget'].status_label.setText("Stopped")
                download['widget'].status_label.setStyleSheet("color: #ff5252;")

        self.stop_all_btn.setEnabled(False)
        self.start_all_btn.setEnabled(True)
        self.update_status_bar()

    def clear_completed_downloads(self):
        urls_to_remove = [
            url for url, download in self.active_downloads.items()
            if download['status'] in ['completed', 'error', 'stopped']
        ]
        
        for url in urls_to_remove:
            self.remove_download(url)

    def update_progress(self, url, progress, status):
        if url in self.active_downloads:
            self.active_downloads[url]['widget'].progress_bar.setValue(progress)
            self.active_downloads[url]['widget'].status_label.setText(status)
            
            # Update progress bar color based on progress
            if progress < 30:
                color = "#ff5252"  # Red
            elif progress < 70:
                color = "#ffd740"  # Yellow
            else:
                color = "#69f0ae"  # Green
                
            self.active_downloads[url]['widget'].progress_bar.setStyleSheet(
                f"""
                QProgressBar::chunk {{
                    background-color: {color};
                    border-radius: 2px;
                }}
                """
            )

    def download_finished(self, url):
        if url in self.active_downloads:
            self.active_downloads[url]['status'] = 'completed'
            self.active_downloads[url]['widget'].status_label.setText("Completed")
            self.active_downloads[url]['widget'].status_label.setStyleSheet("color: #69f0ae;")
            self.active_downloads[url]['widget'].progress_bar.setValue(100)
            
            settings = self.settings_tab.get_settings()
            if not settings['concurrent_downloads']:
                self.start_next_download()

        # Check if all downloads are complete
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
                    "Success",
                    f"All downloads completed successfully! ({total_completed} files)"
                )
            
        self.update_status_bar()

    def download_error(self, url, error):
        if url in self.active_downloads:
            self.active_downloads[url]['status'] = 'error'
            self.active_downloads[url]['widget'].status_label.setText("Error")
            self.active_downloads[url]['widget'].status_label.setStyleSheet("color: #ff5252;")
            
            detailed_error = f"Error downloading {url}:\n\n{error}"
            logger.error(detailed_error)
            
            QMessageBox.critical(self, "Download Error", detailed_error)

            settings = self.settings_tab.get_settings()
            if not settings['concurrent_downloads']:
                self.start_next_download()
                
        self.update_status_bar()

    def load_settings(self):
        self.settings_tab.load_settings()

    def save_settings(self):
        self.settings_tab.save_settings()

    def closeEvent(self, event):
        # Check for active downloads
        active_downloads = any(
            download['status'] == 'downloading' 
            for download in self.active_downloads.values()
        )
        
        if active_downloads:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "There are active downloads. Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.No:
                event.ignore()
                return
        
        self.save_settings()
        self.stop_all_downloads()
        super().closeEvent(event)

def main():
    # Enable high DPI support
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    # Check for FFmpeg
    if not shutil.which('ffmpeg'):
        QMessageBox.critical(
            None,
            "Error",
            "FFmpeg not found! Please install FFmpeg and make sure it's in your system PATH."
        )
        return
    
    try:
        CustomStyle.apply_dark_theme(app)
        window = M3U8StreamDownloader()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        QMessageBox.critical(
            None,
            "Error",
            f"An unexpected error occurred:\n\n{str(e)}"
        )

if __name__ == '__main__':
    main()
