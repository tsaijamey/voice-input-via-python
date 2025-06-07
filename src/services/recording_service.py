import sounddevice as sd
import numpy as np
from typing import Optional, Callable
import threading
import logging
import soundfile as sf
from pathlib import Path
import queue

class RecordingService:
    """音频录制服务，处理录音、分块和状态管理"""

    def __init__(self, sample_rate: int = 16000, channels: int = 1, dtype: str = 'int16'):
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        
        self.is_recording = False
        self.recording_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.stream: Optional[sd.InputStream] = None
        self.logger = logging.getLogger(__name__)
        
        # --- 用于实时分块的内部状态 ---
        self._chunk_queue: Optional[queue.Queue] = None
        self._chunk_size: Optional[int] = None
        self._chunk_buffer: list[np.ndarray] = []
        self._total_samples_in_buffer = 0
        self._full_audio_data: list[np.ndarray] = []

    def start_recording(self, chunk_queue: queue.Queue, chunk_size: int) -> None:
        """开始录音，并将音频块放入指定的队列"""
        if self.is_recording:
            self.logger.warning("Recording already in progress")
            return

        self.is_recording = True
        self._chunk_queue = chunk_queue
        self._chunk_size = chunk_size
        self._chunk_buffer = []
        self._total_samples_in_buffer = 0
        self._full_audio_data = []
        self.stop_event.clear()

        self.recording_thread = threading.Thread(target=self._run_recording)
        self.recording_thread.start()
        self.logger.info("Recording started")

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """音频数据回调，处理分块逻辑"""
        if status:
            self.logger.warning(f"Audio stream status: {status}")
        
        # 存储完整录音
        self._full_audio_data.append(indata.copy())
        
        # --- 核心分块逻辑 ---
        if self._chunk_queue and self._chunk_size:
            self._chunk_buffer.append(indata.copy())
            self._total_samples_in_buffer += len(indata)
            
            if self._total_samples_in_buffer >= self._chunk_size:
                # 拼接并发送音频块
                full_chunk = np.concatenate(self._chunk_buffer)
                self._chunk_queue.put(full_chunk)
                
                # 重置缓冲区
                self._chunk_buffer = []
                self._total_samples_in_buffer = 0

    def _run_recording(self) -> None:
        """运行录音线程，管理音频流的生命周期"""
        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=self.dtype,
                callback=self._audio_callback,
                blocksize=0, # 使用0让sounddevice自动选择最佳块大小
                latency='low'
            ) as self.stream:
                self.stop_event.wait()
        except Exception as e:
            self.logger.error(f"Recording stream error: {e}", exc_info=True)
        finally:
            self.is_recording = False
            self.logger.info("Recording stream closed.")

    def stop_recording(self) -> Optional[np.ndarray]:
        """停止录音并处理剩余的音频数据"""
        if not self.is_recording:
            self.logger.warning("No active recording to stop")
            return None

        self.stop_event.set()
        if self.recording_thread:
            self.recording_thread.join(timeout=2.0)
            if self.recording_thread.is_alive():
                self.logger.error("Recording thread did not terminate in time.")

        self.is_recording = False

        # --- 处理缓冲区中剩余的音频 ---
        if self._chunk_queue and self._chunk_buffer:
            remaining_chunk = np.concatenate(self._chunk_buffer)
            if remaining_chunk.size > 0:
                self.logger.info(f"Putting remaining {len(remaining_chunk)} samples into queue.")
                self._chunk_queue.put(remaining_chunk)
            self._chunk_buffer = []
            self._total_samples_in_buffer = 0

        if not self._full_audio_data:
            self.logger.warning("Recording stopped, but no audio data was captured.")
            return None

        try:
            # 合并完整的音频数据
            full_audio = np.concatenate(self._full_audio_data)
            self.logger.info(f"Recording stopped. Captured {len(full_audio)} samples in total.")
            return full_audio
        except ValueError:
            self.logger.error("Failed to concatenate full audio data. It might be empty.")
            return None

    def save_to_file(self, filename: str, audio_data: np.ndarray) -> Optional[str]:
        """保存音频数据到WAV文件"""
        if audio_data is None or audio_data.size == 0:
            self.logger.error("Cannot save empty audio data.")
            return None
            
        try:
            output_dir = Path("recordings")
            output_dir.mkdir(exist_ok=True)
            
            filepath = output_dir / Path(filename).name
            
            # 检查音频数据是否为静音
            max_abs_val = np.max(np.abs(audio_data))
            if max_abs_val == 0:
                self.logger.warning("Audio data is completely silent. Saving as is.")
                # 创建一个符合格式的静音数组
                normalized_audio = np.zeros_like(audio_data, dtype=np.int16)
            else:
                # 标准化并转换为16位PCM格式
                normalized_audio = np.int16(audio_data / max_abs_val * 32767)

            sf.write(
                filepath,
                normalized_audio,
                samplerate=self.sample_rate,
                subtype='PCM_16'
            )
            self.logger.info(f"Audio saved to {filepath}")
            return str(filepath)
        except Exception as e:
            self.logger.error(f"Failed to save audio to {filename}: {e}", exc_info=True)
            return None