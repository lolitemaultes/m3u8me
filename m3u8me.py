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
    QGroupBox, QStyle, QStyleFactory, QToolTip
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt5.QtGui import QPalette, QColor, QFont, QIcon

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_base_url(url, parsed_url):
    """Get the correct base URL for segment resolution."""
    if url.startswith('#'):
        return parsed_url.scheme + '://' + parsed_url.netloc + os.path.dirname(parsed_url.path) + '/'
    if url.startswith('http'):
        return os.path.dirname(url) + '/'
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
        
        # Enhanced stylesheet without transitions
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
        
        # Truncate long URLs
        display_url = self.url[:50] + '...' if len(self.url) > 50 else self.url
        self.url_label = QLabel(display_url)
        self.url_label.setToolTip(self.url)
        self.url_label.setStyleSheet("font-weight: bold;")
        
        self.status_label = QLabel("Waiting to start...")
        self.status_label.setStyleSheet("color: #2979ff;")
        
        info_layout.addWidget(self.url_label)
        info_layout.addWidget(self.status_label)
        
        # Progress bar with enhanced styling
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
        
        # Cancel button with icon - Fixed icon setting
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
        """Download a single segment with improved error handling and verification."""
        for attempt in range(self.retry_count):
            try:
                if not self.is_running:
                    return False

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
                    verify=False
                )
                response.raise_for_status()
                
                # Verify content type
                content_type = response.headers.get('content-type', '')
                if not any(valid_type in content_type.lower() 
                          for valid_type in ['video', 'audio', 'octet-stream', 'mpegts']):
                    logger.warning(f"Unexpected content type for segment {index}: {content_type}")
                
                # Write segment data
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                
                # Verify file size
                file_size = os.path.getsize(output_path)
                if file_size < 100:
                    raise Exception(f"Segment {index} is too small: {file_size} bytes")
                
                self.progress_updated.emit(
                    self.url,
                    int((index + 1) / total * 90),
                    f"Downloading segment {index + 1}/{total}"
                )
                return True
                
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{self.retry_count} failed for segment {index}: {str(e)}")
                if attempt < self.retry_count - 1:
                    time.sleep(1 * (attempt + 1))  # Exponential backoff
                    continue
                return False
        return False

    def combine_segments(self, segment_files, output_file):
        """Combine segments into final video file with improved format handling and quality."""
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
    
            # Format-specific encoding parameters
            encoding_params = {
                'mp4': {
                    'vcodec': 'libx264',
                    'acodec': 'aac',
                    'extra': [
                        '-movflags', '+faststart',
                        '-profile:v', 'high',
                        '-level', '4.1',
                        '-crf', '23',
                        '-preset', 'medium',
                        '-tune', 'film',
                        '-brand', 'mp42',
                        '-max_muxing_queue_size', '4096'
                    ]
                },
                'mkv': {
                    'vcodec': 'libx264',
                    'acodec': 'copy',
                    'extra': [
                        '-crf', '23',
                        '-preset', 'medium',
                        '-max_muxing_queue_size', '4096',
                        '-map', '0',
                        '-dn'  # Disable data stream copying
                    ]
                },
                'ts': {
                    'vcodec': 'copy',
                    'acodec': 'copy',
                    'extra': [
                        '-copyts',
                        '-muxdelay', '0',
                        '-muxpreload', '0',
                        '-map', '0',
                        '-dn',
                        '-f', 'mpegts',
                        '-mpegts_flags', '+initial_discontinuity'
                    ]
                }
            }

            params = encoding_params.get(output_format)
            
            # Base command
            cmd = [
                'ffmpeg', '-y',
                '-hide_banner',
                '-loglevel', 'warning',
                '-stats', '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c:v', params['vcodec'],
                '-c:a', params['acodec'],
            ]
            
            # Add format-specific extra parameters
            cmd.extend(params['extra'])
            
            # Add common parameters for better output quality
            if output_format != 'ts':
                cmd.extend([
                    '-vsync', 'cfr',
                    '-af', 'aresample=async=1:min_hard_comp=0.100000',
                    '-vf', 'format=yuv420p',
                    '-metadata', f'encoding_tool=M3U8 Downloader {datetime.now().strftime("%Y-%m-%d")}'
                ])

            # Add output file
            cmd.append(output_file)
    
            # Run FFmpeg with progress monitoring
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Monitor FFmpeg progress
            while True:
                if not self.is_running:
                    process.terminate()
                    raise Exception("Processing cancelled by user")
                    
                output = process.stderr.readline()
                if output == '' and process.poll() is not None:
                    break
                    
                if 'time=' in output:
                    try:
                        time_str = re.search(r'time=(\d+:\d+:\d+.\d+)', output).group(1)
                        h, m, s = map(float, time_str.split(':'))
                        progress = min(99, 90 + int(float(h) * 3600 + float(m) * 60 + float(s)) % 10)
                        self.progress_updated.emit(self.url, progress, "Processing video...")
                    except:
                        pass
            
            process.wait()
            
            if process.returncode != 0:
                error_msg = process.stderr.read().strip()
                raise Exception(f"FFmpeg error: {error_msg}")
            
            # Verify output file
            if not os.path.exists(output_file) or os.path.getsize(output_file) < 1000:
                raise Exception("Output file is missing or too small")
                
            # Final verification for non-TS formats
            if output_format != 'ts':
                verify_cmd = [
                    'ffmpeg', '-v', 'error',
                    '-i', output_file,
                    '-f', 'null', '-'
                ]
                verify_process = subprocess.run(
                    verify_cmd,
                    capture_output=True,
                    text=True
                )
                if verify_process.stderr:
                    raise Exception(f"Output file verification failed: {verify_process.stderr}")
    
            return True
    
        except Exception as e:
            logger.error(f"Error combining segments: {str(e)}")
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
                # Get the playlist content with retry logic
                for attempt in range(self.retry_count):
                    try:
                        response = self.session.get(
                            self.url,
                            headers=self.headers,
                            verify=False,
                            timeout=30
                        )
                        response.raise_for_status()
                        content = response.text
                        break
                    except Exception as e:
                        if attempt == self.retry_count - 1:
                            raise Exception(f"Failed to fetch playlist: {str(e)}")
                        time.sleep(1 * (attempt + 1))

            playlist = m3u8.loads(content)
            
            # Handle master playlist
            if not playlist.segments and playlist.playlists:
                # Sort playlists by bandwidth
                playlists = sorted(
                    playlist.playlists,
                    key=lambda p: p.stream_info.bandwidth if p.stream_info else 0
                )
                
                # Select quality based on settings
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
                
                # Get the media playlist with retry logic
                for attempt in range(self.retry_count):
                    try:
                        response = self.session.get(
                            playlist_url,
                            headers=self.headers,
                            verify=False,
                            timeout=30
                        )
                        response.raise_for_status()
                        playlist = m3u8.loads(response.text)
                        break
                    except Exception as e:
                        if attempt == self.retry_count - 1:
                            raise Exception(f"Failed to fetch media playlist: {str(e)}")
                        time.sleep(1 * (attempt + 1))
                        
                # Update base URL for segments
                parsed_url = urlparse(playlist_url)

            if not playlist.segments:
                raise Exception("No segments found in playlist")

            # Calculate total download size (if possible)
            total_size = 0
            if hasattr(playlist.segments[0], 'byterange'):
                for segment in playlist.segments:
                    total_size += segment.byterange.length if segment.byterange else 0

            # Get the correct base URL for segments
            base_url = get_base_url(self.url, parsed_url)
            
            # Download segments
            segment_files = []
            downloaded_segments = set()
            total_segments = len(playlist.segments)
            
            self.progress_updated.emit(
                self.url,
                0,
                f"Starting download of {total_segments} segments" + 
                (f" ({total_size/1024/1024:.1f} MB)" if total_size > 0 else "")
            )
            
            for i, segment in enumerate(playlist.segments):
                if not self.is_running:
                    raise Exception("Download cancelled by user")

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
                    time.sleep(min(1 * (attempt + 1), 5))  # Exponential backoff with max delay
                
                if not success:
                    raise Exception(f"Failed to download segment {i + 1} after {self.retry_count} attempts")

            if len(downloaded_segments) != total_segments:
                raise Exception(f"Missing segments. Downloaded {len(downloaded_segments)}/{total_segments}")

            # Combine segments
            self.progress_updated.emit(self.url, 90, "Processing video...")
            
            # Create output filename with quality info
            quality_info = f"_{self.settings['quality']}" if 'quality' in self.settings else ""
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(
                self.save_path,
                f"video_{timestamp}{quality_info}"
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
                try:
                    shutil.rmtree(self.temp_dir, ignore_errors=True)
                except:
                    pass

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
        
        # Quality selection
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(['best', 'medium', 'worst'])
        self.quality_combo.setToolTip("Select the video quality for multi-quality streams")
        video_layout.addWidget(QLabel("Quality:"), 0, 0)
        video_layout.addWidget(self.quality_combo, 0, 1)
        
        # Format selection with tooltips
        self.format_combo = QComboBox()
        self.format_combo.addItems(['mp4', 'mkv', 'ts'])
        self.format_combo.setItemData(0, "Best for compatibility and streaming (recommended)", Qt.ToolTipRole)
        self.format_combo.setItemData(1, "Good for high quality and multiple audio tracks", Qt.ToolTipRole)
        self.format_combo.setItemData(2, "Raw stream without re-encoding (faster but larger)", Qt.ToolTipRole)
        video_layout.addWidget(QLabel("Output Format:"), 1, 0)
        video_layout.addWidget(self.format_combo, 1, 1)
        
        # Quality presets
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
        """Apply predefined quality settings."""
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
        self.setWindowTitle("M3U8 Stream Downloader")
        self.setMinimumSize(900, 700)
        self.active_downloads = {}
        self.save_path = None
        self.init_ui()
        self.load_settings()
        self.check_ffmpeg()

    def check_ffmpeg(self):
        """Verify FFmpeg installation and capabilities."""
        if not shutil.which('ffmpeg'):
            QMessageBox.critical(
                self,
                "FFmpeg Not Found",
                "FFmpeg is required but not found on your system. Please install FFmpeg and make sure it's in your system PATH.",
                QMessageBox.Ok
            )
            sys.exit(1)
        
        try:
            # Check FFmpeg version and capabilities
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True
            )
            if 'ffmpeg version' not in result.stdout:
                raise Exception("Invalid FFmpeg installation")
                
            # Get first line of version info without using backslash
            version_line = result.stdout.split('\n')[0]
            logger.info(f"FFmpeg found: {version_line}")
        except Exception as e:
            QMessageBox.warning(
                self,
                "FFmpeg Check Failed",
                f"Error verifying FFmpeg installation: {str(e)}\nSome features may not work correctly.",
                QMessageBox.Ok
            )

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Add header with version
        header_layout = QHBoxLayout()
        header_label = QLabel("M3U8 Stream Downloader")
        header_label.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #2979ff;
            padding: 10px;
        """)
        header_label.setAlignment(Qt.AlignCenter)
        
        version_label = QLabel("v2.0")
        version_label.setStyleSheet("color: #666666; padding: 10px;")
        version_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        header_layout.addWidget(header_label, stretch=1)
        header_layout.addWidget(version_label)
        layout.addLayout(header_layout)

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
        self.url_input.returnPressed.connect(self.add_url_from_input)
        url_layout.addWidget(self.url_input)

        # Add URL button with icon and tooltip
        self.add_url_btn = QPushButton("Add URL")
        self.add_url_btn.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        self.add_url_btn.setToolTip("Add a single URL to the download queue")
        self.add_url_btn.clicked.connect(self.add_url_from_input)
        url_layout.addWidget(self.add_url_btn)

        # Bulk upload button with icon and tooltip
        self.bulk_upload_btn = QPushButton("Bulk Upload")
        self.bulk_upload_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        self.bulk_upload_btn.setToolTip("Upload multiple URLs from a file")
        self.bulk_upload_btn.clicked.connect(self.bulk_upload)
        url_layout.addWidget(self.bulk_upload_btn)
        
        url_group.setLayout(url_layout)
        layout.addWidget(url_group)

        # Downloads area with improved scrolling
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

        # Control buttons with icons and tooltips
        control_group = QGroupBox()
        button_layout = QHBoxLayout()
        
        self.start_all_btn = QPushButton("Start All")
        self.start_all_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.start_all_btn.setToolTip("Start all pending downloads")
        self.start_all_btn.clicked.connect(self.start_all_downloads)
        self.start_all_btn.setEnabled(False)
        button_layout.addWidget(self.start_all_btn)
        
        self.stop_all_btn = QPushButton("Stop All")
        self.stop_all_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
        self.stop_all_btn.setToolTip("Stop all active downloads")
        self.stop_all_btn.clicked.connect(self.stop_all_downloads)
        self.stop_all_btn.setEnabled(False)
        button_layout.addWidget(self.stop_all_btn)
        
        self.clear_completed_btn = QPushButton("Clear Completed")
        self.clear_completed_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        self.clear_completed_btn.setToolTip("Remove completed downloads from the list")
        self.clear_completed_btn.clicked.connect(self.clear_completed_downloads)
        button_layout.addWidget(self.clear_completed_btn)
        
        control_group.setLayout(button_layout)
        layout.addWidget(control_group)

    def setup_status_bar(self):
        """Set up an enhanced status bar with more information."""
        self.statusBar().showMessage("Ready")
        
        # Create status widgets with tooltips
        self.status_downloads = QLabel("Downloads: 0")
        self.status_downloads.setToolTip("Total number of downloads")
        
        self.status_active = QLabel("Active: 0")
        self.status_active.setToolTip("Currently downloading")
        
        self.status_completed = QLabel("Completed: 0")
        self.status_completed.setToolTip("Successfully completed downloads")
        
        # Add a separator between status elements
        separator = QLabel(" | ")
        separator.setStyleSheet("color: #666666;")
        
        # Add widgets to status bar
        self.statusBar().addPermanentWidget(self.status_downloads)
        self.statusBar().addPermanentWidget(separator)
        self.statusBar().addPermanentWidget(self.status_active)
        self.statusBar().addPermanentWidget(QLabel(" | "))
        self.statusBar().addPermanentWidget(self.status_completed)

    def add_url_from_input(self):
        """Add URL from input field with validation."""
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

    def add_download(self, url):
        """Add a new download with duplicate checking."""
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
        """Remove a download with confirmation if active."""
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

    def bulk_upload(self):
        """Enhanced bulk upload with better file handling."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select M3U8 Files or URL List",
            "",
            "M3U8 Files (*.m3u8);;Text Files (*.txt);;All Files (*.*)"
        )
        
        if not file_paths:
            return
            
        # Get save directory once for all files
        if not self.save_path:
            self.save_path = QFileDialog.getExistingDirectory(
                self,
                "Select Save Directory",
                options=QFileDialog.ShowDirsOnly
            )
            
            if not self.save_path:
                return

        # Track statistics for user feedback
        added = 0
        skipped = 0
        errors = 0
        
        for file_path in file_paths:
            try:
                if file_path.endswith('.txt'):
                    # Handle text files with URLs
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
                    # Handle M3U8 files
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

        # Show summary message
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

    def start_download(self, url):
        """Start a single download with improved error handling."""
        if url not in self.active_downloads:
            return

        # Use existing save path or ask for one
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
        
        # Create and configure worker
        worker = StreamDownloader(url, save_path, settings)
        worker.progress_updated.connect(self.update_progress)
        worker.download_complete.connect(self.download_finished)
        worker.download_error.connect(self.download_error)
        
        # Update download status
        self.active_downloads[url].update({
            'worker': worker,
            'status': 'downloading'
        })
        
        self.active_downloads[url]['widget'].update_status(
            "Initializing download...",
            "#2979ff"
        )
        
        # Start the download
        worker.start()
        self.stop_all_btn.setEnabled(True)
        self.update_status_bar()

    def start_all_downloads(self):
        """Start all pending downloads with concurrent option."""
        if not self.active_downloads:
            return

        # Get save directory if not already set
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
            # Start all pending downloads simultaneously
            for url in list(self.active_downloads.keys()):
                if self.active_downloads[url]['status'] == 'waiting':
                    self.start_download(url)
        else:
            # Start only the first pending download
            self.start_next_download()

    def start_next_download(self):
        """Start the next pending download in the queue."""
        for url in self.active_downloads:
            if self.active_downloads[url]['status'] == 'waiting':
                self.start_download(url)
                break

    def stop_all_downloads(self):
        """Stop all active downloads with status updates."""
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
        """Clear completed downloads with confirmation."""
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

    def update_progress(self, url, progress, status):
        """Update download progress with enhanced visual feedback."""
        if url not in self.active_downloads:
            return

        download = self.active_downloads[url]
        download['widget'].progress_bar.setValue(progress)
        download['widget'].update_status(status)
        
        # Update progress bar color based on progress
        if progress < 30:
            color = "#ff5252"  # Red
        elif progress < 70:
            color = "#ffd740"  # Yellow
        else:
            color = "#69f0ae"  # Green
            
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
        """Handle successful download completion."""
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
                    "Downloads Complete",
                    f"All downloads completed successfully! ({total_completed} files)",
                    QMessageBox.Ok
                )
            
        self.update_status_bar()

    def download_error(self, url, error):
        """Handle download errors with detailed feedback."""
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
        """Update status bar with detailed download statistics."""
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

    def load_settings(self):
        """Load application settings."""
        self.settings_tab.load_settings()

    def save_settings(self):
        """Save application settings."""
        self.settings_tab.save_settings()

    def closeEvent(self, event):
        """Handle application closure with active download check."""
        active_downloads = any(
            download['status'] == 'downloading' 
            for download in self.active_downloads.values()
        )
        
        if active_downloads:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "There are active downloads. Are you sure you want to exit?\nActive downloads will be cancelled.",
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
    """Main application entry point with enhanced error handling."""
    # Enable high DPI support
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    try:
        CustomStyle.apply_dark_theme(app)
        window = M3U8StreamDownloader()
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
