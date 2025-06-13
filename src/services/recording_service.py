import sounddevice as sd
import numpy as np
from typing import Optional, Callable
import threading
import logging
import soundfile as sf
from pathlib import Path
import queue
import audioop

class RecordingService:
    """音频录制服务，处理录音、分块和状态管理"""

    def __init__(self, recording_config: dict, sample_rate: int = 16000, channels: int = 1, dtype: str = 'int16'):
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        
        self.is_recording = False
        self.recording_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.stream: Optional[sd.InputStream] = None
        self.logger = logging.getLogger(__name__)
        
        # --- 混合切分模式配置 ---
        self.chunk_seconds = recording_config.get('realtime_chunk_seconds', 3)
        self.floor_threshold = recording_config.get('realtime_split_silence_threshold', 100)
        self.split_ratio = recording_config.get('realtime_split_ratio', 0.6)
        self.min_chunk_duration_ms = recording_config.get('min_chunk_duration_ms', 300)
        self.chunk_size = int(self.chunk_seconds * self.sample_rate) # 每个处理周期的帧数
        
        # --- 状态变量 ---
        self._chunk_queue: Optional[queue.Queue] = None
        self._buffer: list[np.ndarray] = [] # 主缓冲区，持续接收音频数据
        self._carry_over_buffer: Optional[np.ndarray] = None # 上一个块未发送的结转部分
        self._full_audio_data: list[np.ndarray] = []

    def start_recording(self, chunk_queue: queue.Queue) -> None:
        """开始录音，并将音频块放入指定的队列"""
        if self.is_recording:
            self.logger.warning("Recording already in progress")
            return

        self.is_recording = True
        self._chunk_queue = chunk_queue
        self._buffer = []
        self._carry_over_buffer = None
        self._full_audio_data = []
        self.stop_event.clear()

        self.recording_thread = threading.Thread(target=self._run_recording)
        self.recording_thread.start()
        self.logger.info("Recording started")

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """音频数据回调，实现混合切分逻辑"""
        if status:
            self.logger.warning(f"Audio stream status: {status}")
        
        self._full_audio_data.append(indata.copy())
        self._buffer.append(indata.copy())
        
        # 检查缓冲区是否达到一个处理周期的大小
        if self.get_buffer_len_in_frames() < self.chunk_size:
            return

        # 缓冲区已达到处理周期，开始处理
        full_buffer_data = np.concatenate(self._buffer)
        
        # 取出要处理的块
        process_chunk_data = full_buffer_data[:self.chunk_size]
        
        # 更新缓冲区，保留未处理的部分
        remaining_buffer_data = full_buffer_data[self.chunk_size:]
        if remaining_buffer_data.size > 0:
            self._buffer = [remaining_buffer_data]
        else:
            self._buffer = []

        # 寻找切分点
        split_point = self.find_split_point(process_chunk_data)

        if split_point is not None:
            # 找到了切分点
            to_send_data = process_chunk_data[:split_point]
            remaining_data = process_chunk_data[split_point:]

            # 合并上次结转的音频
            if self._carry_over_buffer is not None and self._carry_over_buffer.size > 0:
                to_send_data = np.concatenate([self._carry_over_buffer, to_send_data])
            
            self.send_chunk(to_send_data)
            self._carry_over_buffer = remaining_data
        else:
            # 未找到切分点，将整个块作为结转音频
            if self._carry_over_buffer is not None and self._carry_over_buffer.size > 0:
                self._carry_over_buffer = np.concatenate([self._carry_over_buffer, process_chunk_data])
            else:
                self._carry_over_buffer = process_chunk_data

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

    def get_buffer_len_in_frames(self) -> int:
        """计算主缓冲区中的总帧数"""
        if not self._buffer:
            return 0
        return sum(len(chunk) for chunk in self._buffer)

    def send_chunk(self, audio_data: np.ndarray):
        """对音频块进行预检，如果有效则放入队列"""
        # --- 预检 1: 检查时长 ---
        min_chunk_samples = int((self.min_chunk_duration_ms / 1000) * self.sample_rate)
        if audio_data.size < min_chunk_samples:
            self.logger.info(f"Skipping chunk: too short ({len(audio_data)} samples).")
            return

        # --- 预检 2: 检查音量 ---
        try:
            avg_rms = audioop.rms(audio_data.tobytes(), 2)
            if avg_rms < self.floor_threshold:
                self.logger.info(f"Skipping chunk: too quiet (RMS: {avg_rms:.2f}).")
                return
        except Exception:
            self.logger.warning("Skipping chunk: could not calculate RMS for pre-check.")
            return

        # --- 通过所有预检，发送音频块 ---
        if self._chunk_queue:
            self.logger.info(f"Putting chunk of {len(audio_data)} samples into queue (RMS: {avg_rms:.2f}).")
            self._chunk_queue.put(audio_data)

    def find_split_point(self, data: np.ndarray, search_margin_ms: int = 500) -> Optional[int]:
        """在音频数据块的末尾使用动态阈值向前搜索一个静音点"""
        # --- 1. 计算动态阈值 ---
        try:
            avg_rms = audioop.rms(data.tobytes(), 2)
            dynamic_threshold = avg_rms * self.split_ratio
            effective_threshold = max(dynamic_threshold, self.floor_threshold)
        except Exception as e:
            self.logger.warning(f"Could not calculate average RMS for dynamic threshold, falling back to floor. Error: {e}")
            effective_threshold = self.floor_threshold

        # --- 2. 定义搜索范围 ---
        margin_frames = int((search_margin_ms / 1000) * self.sample_rate)
        if len(data) < margin_frames:
            margin_frames = len(data)
        
        search_area = data[-margin_frames:]
        if len(search_area) == 0:
            return None

        # --- 3. 在该范围内，从后向前遍历，以小步长（如20ms）检查音量 ---
        step_ms = 20
        step_frames = int((step_ms / 1000) * self.sample_rate)
        if step_frames == 0: step_frames = 1
        
        min_rms_in_margin = float('inf')

        for i in range(len(search_area) - step_frames, 0, -step_frames):
            chunk_to_check = search_area[i : i + step_frames]
            try:
                rms = audioop.rms(chunk_to_check.tobytes(), 2)
                min_rms_in_margin = min(min_rms_in_margin, rms)

                if rms < effective_threshold:
                    # 4. 如果音量低于生效阈值，则返回该位置作为切分点
                    split_point_in_data = len(data) - margin_frames + i
                    self.logger.info(
                        f"Found split point at frame {split_point_in_data} with RMS: {rms:.2f} "
                        f"(effective threshold: {effective_threshold:.2f})"
                    )
                    return split_point_in_data
            except Exception:
                pass # 忽略单个小块的计算错误

        # 5. 如果搜索完仍未找到，返回 None并提供更有用的日志
        self.logger.info(
            f"No suitable split point found. "
            f"Min RMS in margin was {min_rms_in_margin:.2f}, "
            f"not below effective threshold of {effective_threshold:.2f} "
            f"(avg_rms: {avg_rms:.2f}, ratio: {self.split_ratio}, floor: {self.floor_threshold})."
        )
        return None

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

        # --- 处理所有剩余的音频 ---
        final_chunk_parts = []
        # 1. 从结转缓冲区开始
        if self._carry_over_buffer is not None and self._carry_over_buffer.size > 0:
            final_chunk_parts.append(self._carry_over_buffer)
        
        # 2. 添加主缓冲区的内容
        if self._buffer:
            main_buffer_data = np.concatenate(self._buffer)
            if main_buffer_data.size > 0:
                final_chunk_parts.append(main_buffer_data)

        # 3. 发送最后的音频块
        if final_chunk_parts:
            final_chunk = np.concatenate(final_chunk_parts)
            self.send_chunk(final_chunk)

        # 重置缓冲区
        self._buffer = []
        self._carry_over_buffer = None

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