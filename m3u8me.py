import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                           QProgressBar, QFileDialog, QMessageBox,
                           QComboBox, QSpinBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import m3u8
import requests
import subprocess
from urllib.parse import urljoin, urlparse
import concurrent.futures
import tempfile
import shutil
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StreamDownloader(QThread):
    progress_updated = pyqtSignal(int, str)
    download_complete = pyqtSignal(str)
    download_error = pyqtSignal(str, str)

    def __init__(self, url, save_path, quality='best', max_workers=4, segment_timeout=30):
        super().__init__()
        self.url = url
        self.save_path = save_path
        self.quality = quality
        self.max_workers = max_workers
        self.segment_timeout = segment_timeout
        self.is_running = True
        self.session = requests.Session()
        self.temp_dir = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }

    def get_base_url(self, url):
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{os.path.dirname(parsed.path)}/"

    def select_playlist(self, master_playlist, base_url):
        playlists = master_playlist.playlists
        if not playlists:
            return None, None

        playlists.sort(key=lambda p: p.stream_info.bandwidth if p.stream_info else 0)
        
        if self.quality == 'best':
            selected = playlists[-1]
        elif self.quality == 'worst':
            selected = playlists[0]
        else:  # medium
            selected = playlists[len(playlists)//2]

        # Ensure we have a complete URL for the playlist
        playlist_url = selected.uri
        if not playlist_url.startswith('http'):
            playlist_url = urljoin(base_url, playlist_url)

        return selected, playlist_url

    def download_segment(self, segment_url, base_url, output_path, index, total):
        retries = 3
        
        # Ensure we have a complete URL for the segment
        if not segment_url.startswith('http'):
            segment_url = urljoin(base_url, segment_url)

        for attempt in range(retries):
            try:
                response = self.session.get(
                    segment_url, 
                    headers=self.headers,
                    timeout=self.segment_timeout
                )
                response.raise_for_status()
                
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                
                progress = int((index + 1) / total * 100)
                self.progress_updated.emit(
                    progress, 
                    f"Downloading segment {index + 1}/{total}"
                )
                return True
            except Exception as e:
                logger.error(f"Error downloading segment {index + 1}: {str(e)}")
                if attempt == retries - 1:
                    self.download_error.emit(self.url, f"Failed to download segment {index + 1}: {str(e)}")
                    return False
                continue

    def combine_segments(self, segment_files, output_file):
        try:
            if shutil.which('ffmpeg'):
                concat_file = os.path.join(self.temp_dir, 'concat.txt')
                with open(concat_file, 'w') as f:
                    for segment in segment_files:
                        f.write(f"file '{segment}'\n")

                cmd = [
                    'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                    '-i', concat_file, '-c', 'copy', output_file
                ]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            else:
                with open(output_file, 'wb') as outfile:
                    for i, segment_file in enumerate(segment_files):
                        if os.path.exists(segment_file):
                            with open(segment_file, 'rb') as infile:
                                outfile.write(infile.read())
                        
                        progress = int((i + 1) / len(segment_files) * 100)
                        self.progress_updated.emit(
                            progress,
                            f"Combining segments {i + 1}/{len(segment_files)}"
                        )
            return True
        except Exception as e:
            self.download_error.emit(self.url, f"Error combining segments: {str(e)}")
            return False

    def run(self):
        try:
            self.temp_dir = tempfile.mkdtemp()
            
            # Get initial playlist
            response = self.session.get(self.url, headers=self.headers)
            response.raise_for_status()
            
            base_url = self.get_base_url(self.url)
            m3u8_content = m3u8.loads(response.text)

            # Handle master playlist
            if m3u8_content.is_endlist == False and m3u8_content.playlists:
                playlist, playlist_url = self.select_playlist(m3u8_content, base_url)
                if not playlist:
                    raise Exception("No suitable playlist found")
                
                logger.info(f"Selected playlist: {playlist_url}")
                response = self.session.get(playlist_url, headers=self.headers)
                response.raise_for_status()
                base_url = self.get_base_url(playlist_url)
                m3u8_content = m3u8.loads(response.text)

            # Check for segments
            if not m3u8_content.segments:
                logger.error(f"Playlist content: {response.text}")
                raise Exception("No segments found in playlist. Content may be DRM-protected or requires authentication.")

            # Download segments
            segment_files = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                
                for i, segment in enumerate(m3u8_content.segments):
                    if not self.is_running:
                        executor.shutdown(wait=False)
                        return

                    output_path = os.path.join(
                        self.temp_dir,
                        f"segment_{i:05d}.ts"
                    )
                    segment_files.append(output_path)
                    
                    future = executor.submit(
                        self.download_segment,
                        segment.uri,
                        base_url,
                        output_path,
                        i,
                        len(m3u8_content.segments)
                    )
                    futures.append(future)

                results = [f.result() for f in futures]
                if not all(results):
                    raise Exception("Some segments failed to download")

            # Combine segments
            output_file = os.path.join(
                self.save_path,
                f"{os.path.splitext(os.path.basename(self.url))[0]}.mp4"
            )
            
            self.progress_updated.emit(0, "Combining segments...")
            if self.combine_segments(segment_files, output_file):
                self.download_complete.emit(self.url)

        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            self.download_error.emit(self.url, str(e))
        finally:
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)

    def stop(self):
        self.is_running = False

class M3U8StreamDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("M3U8 Stream Downloader")
        self.setMinimumSize(600, 400)
        self.active_downloads = {}
        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # URL input section
        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter M3U8 stream URL")
        url_layout.addWidget(self.url_input)

        # Bulk upload button
        self.bulk_upload_btn = QPushButton("Bulk Upload M3U8 Files")
        self.bulk_upload_btn.clicked.connect(self.bulk_upload)
        url_layout.addWidget(self.bulk_upload_btn)

        layout.addLayout(url_layout)

        # Settings section
        settings_layout = QHBoxLayout()
        
        # Quality selection
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(['best', 'medium', 'worst'])
        settings_layout.addWidget(QLabel("Quality:"))
        settings_layout.addWidget(self.quality_combo)
        
        # Thread count
        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, 16)
        self.thread_spin.setValue(4)
        settings_layout.addWidget(QLabel("Threads:"))
        settings_layout.addWidget(self.thread_spin)
        
        settings_layout.addStretch()
        layout.addLayout(settings_layout)

        # Progress section
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        # Control buttons
        button_layout = QHBoxLayout()
        
        self.download_btn = QPushButton("Download")
        self.download_btn.clicked.connect(self.start_download)
        button_layout.addWidget(self.download_btn)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_download)
        self.stop_btn.setEnabled(False)
        button_layout.addWidget(self.stop_btn)
        
        layout.addLayout(button_layout)

    def bulk_upload(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select M3U8 Files", "", "M3U8 Files (*.m3u8)")
        if file_paths:
            save_path = QFileDialog.getExistingDirectory(self, "Select Save Directory")
            if not save_path:
                return

            for file_path in file_paths:
                self.start_download(file_path, save_path)

    def start_download(self, url=None, save_path=None):
        if not url:
            url = self.url_input.text().strip()

        if not url:
            QMessageBox.warning(self, "Error", "Please enter a valid URL")
            return

        if not save_path:
            save_path = QFileDialog.getExistingDirectory(self, "Select Save Directory")
            if not save_path:
                return

        self.download_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting download...")

        worker = StreamDownloader(
            url=url,
            save_path=save_path,
            quality=self.quality_combo.currentText(),
            max_workers=self.thread_spin.value()
        )
        
        worker.progress_updated.connect(self.update_progress)
        worker.download_complete.connect(self.download_finished)
        worker.download_error.connect(self.download_error)
        
        self.active_downloads[url] = worker
        worker.start()

    def stop_download(self):
        for worker in self.active_downloads.values():
            worker.stop()
        
        self.status_label.setText("Stopping downloads...")
        self.stop_btn.setEnabled(False)

    def update_progress(self, progress, status):
        self.progress_bar.setValue(progress)
        self.status_label.setText(status)

    def download_finished(self, url):
        if url in self.active_downloads:
            self.active_downloads[url].deleteLater()
            del self.active_downloads[url]

        if not self.active_downloads:
            self.download_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.status_label.setText("Download completed!")
            QMessageBox.information(
                self, "Success", "Download completed successfully!"
            )

    def download_error(self, url, error):
        QMessageBox.critical(self, "Error", f"Error downloading {url}: {error}")
        if url in self.active_downloads:
            self.active_downloads[url].deleteLater()
            del self.active_downloads[url]

        if not self.active_downloads:
            self.download_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def closeEvent(self, event):
        for worker in self.active_downloads.values():
            worker.stop()
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = M3U8StreamDownloader()
    window.show()
    sys.exit(app.exec_())
