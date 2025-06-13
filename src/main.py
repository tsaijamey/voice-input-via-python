import logging
import numpy as np
import sys
import time
import threading
import queue
import signal
import os
import soundfile as sf

from dotenv import load_dotenv
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, QTimer

from core.config_loader import ConfigLoader
from core.hotkey_manager import HotkeyManager
from services.recording_service import RecordingService
from services.asr_service import ASRService
from services.timer_overlay import ControlWidget
from services.vision_service import VisionService
from services.content_enhancement_service import ContentEnhancementService
from utils.screenshot_util import take_screenshot, resize_image, save_screenshot
from output_handler import copy_to_clipboard, save_to_file

class Communicate(QObject):
    """用于跨线程通信的信号类"""
    toggle_signal = Signal(bool)

def setup_logging():
    """配置日志记录"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

def main():
    """主应用入口"""
    # 在所有操作之前加载环境变量
    load_dotenv()
    
    setup_logging()
    logger = logging.getLogger(__name__)

    app = QApplication(sys.argv)
    
    try:
        config = ConfigLoader().load()
        logger.info("Configuration loaded successfully")
        
        # --- 初始化服务和状态 ---
        hotkey_manager = HotkeyManager()
        recording_service = RecordingService()
        asr_service = ASRService(
            asr_config=config['services']['asr'],
            correction_config=config['services']['text_correction']
        )
        control_widget = ControlWidget()
        vision_service = VisionService(config['services']['vision'])
        enhancement_service = ContentEnhancementService(config['services']['content_enhancement'])
        max_screenshot_width = config['services']['vision'].get('max_width', 1200)
        
        is_recording = False
        audio_queue = queue.Queue()
        transcription_worker_thread = None
        vision_worker_thread = None
        full_transcript = []
        screen_context_result = None
        
        chunk_seconds = config['recording'].get('realtime_chunk_seconds', 10)
        chunk_size = int(chunk_seconds * recording_service.sample_rate)

        def transcription_worker():
            min_chunk_samples = int(0.5 * recording_service.sample_rate)

            while True:
                audio_chunk = audio_queue.get()
                if audio_chunk is None:
                    audio_queue.task_done()
                    break

                # 如果音频块太短，则忽略，以避免ASR产生幻觉
                if len(audio_chunk) < min_chunk_samples:
                    logger.info(f"Skipping a short audio chunk with {len(audio_chunk)} samples.")
                    audio_queue.task_done()
                    continue
                
                # --- 增加诊断日志 ---
                duration_seconds = len(audio_chunk) / recording_service.sample_rate
                logger.info(
                    f"Sending chunk to ASR: "
                    f"Duration={duration_seconds:.2f}s, "
                    f"Samples={len(audio_chunk)}, "
                    f"Dtype={audio_chunk.dtype}, "
                    f"Min={np.min(audio_chunk):.0f}, "
                    f"Max={np.max(audio_chunk):.0f}"
                )
                
                transcript = asr_service.transcribe_audio_data(
                    audio_chunk,
                    sample_rate=recording_service.sample_rate
                )
                
                if transcript:
                    # 1. 显示原始转录结果
                    logger.info(f"实时转录 (原始): {transcript}")
                    
                    # 2. 对实时转录的片段进行修正
                    corrected_chunk = asr_service.correct_text(transcript)
                    logger.info(f"实时转录 (修正): {corrected_chunk}")
                    
                    # 3. 拼接最终结果
                    full_transcript.append(corrected_chunk)
                    logger.info(f"当前完整文本: {' '.join(full_transcript)}")
                
                audio_queue.task_done()
            logger.info("Transcription worker finished.")
        
        communicator = Communicate()
        
        def handle_toggle_recording(start: bool):
            nonlocal is_recording, transcription_worker_thread, vision_worker_thread, full_transcript, screen_context_result
            
            if start and not is_recording:
                is_recording = True
                logger.info("Recording started...")
                
                # --- 并行任务启动 ---
                # 1. 启动视觉分析线程
                def vision_worker():
                    nonlocal screen_context_result
                    logger.info("Capturing and analyzing screen...")
                    screenshot = take_screenshot()
                    resized_screenshot = resize_image(screenshot, max_screenshot_width)
                    save_screenshot(resized_screenshot) # 保存调整尺寸后的截图
                    screen_context_result = vision_service.analyze_screenshot(resized_screenshot)
                    logger.info("Screen analysis complete.")

                vision_worker_thread = threading.Thread(target=vision_worker, daemon=True)
                vision_worker_thread.start()

                # 2. 启动录音和ASR转录线程
                full_transcript = []
                while not audio_queue.empty():
                    audio_queue.get_nowait()

                transcription_worker_thread = threading.Thread(target=transcription_worker, daemon=True)
                transcription_worker_thread.start()
                
                countdown = config['recording'].get('countdown_seconds', 60)
                control_widget.set_recording_state(countdown)
                
                recording_service.start_recording(audio_queue, chunk_size)

            elif not start and is_recording:
                is_recording = False
                logger.info("Recording stopped...")
                
                # 停止录音
                recording_service.stop_recording()
                
                # 发送结束信号给ASR转录工作线程
                audio_queue.put(None)
                
                # --- 等待并行任务完成 ---
                logger.info("Waiting for transcription and vision analysis to complete...")
                if transcription_worker_thread:
                    transcription_worker_thread.join(timeout=10.0) # 增加超时
                if vision_worker_thread:
                    vision_worker_thread.join(timeout=20.0) # 视觉分析可能更耗时

                final_text = ' '.join(full_transcript)
                logger.info(f"最终识别文本: {final_text}")
                logger.info(f"最终屏幕上下文: {screen_context_result}")

                if final_text and screen_context_result:
                    # --- 内容增强 ---
                    enhanced_text = enhancement_service.enhance_text(final_text, screen_context_result)
                    logger.info(f"增强后文本: {enhanced_text}")
                    copy_to_clipboard(enhanced_text)
                    save_to_file(enhanced_text)
                elif final_text:
                    # 如果视觉分析失败，则回退到只输出原始文本
                    logger.warning("Vision analysis failed or returned no result. Falling back to original transcript.")
                    copy_to_clipboard(final_text)
                    save_to_file(final_text)
                else:
                    logger.warning("没有识别到任何文本，跳过输出。")

                control_widget.set_idle_state()

        # --- 连接所有信号到统一的处理器 ---
        communicator.toggle_signal.connect(lambda start: handle_toggle_recording(start))
        control_widget.start_requested.connect(lambda: handle_toggle_recording(True))
        control_widget.stop_requested.connect(lambda: handle_toggle_recording(False))
        
        # --- 优雅退出逻辑 ---
        def shutdown_application():
            logger.info("Application shutting down...")
            hotkey_manager.stop()
            
            # 确保录音停止
            if is_recording:
                handle_toggle_recording(False)

            # 等待转录线程结束
            if transcription_worker_thread and transcription_worker_thread.is_alive():
                audio_queue.put(None) # 发送停止信号
                transcription_worker_thread.join(timeout=5.0)

            logger.info("Shutdown complete.")
            QApplication.quit()

        # 连接GUI退出按钮
        control_widget.exit_requested.connect(shutdown_application)
        
        # 捕获 Ctrl+C 信号
        signal.signal(signal.SIGINT, lambda sig, frame: shutdown_application())
        
        # PySide6 需要一个定时器来确保 Python 的信号处理器能被主事件循环调用
        timer = QTimer()
        timer.start(500)
        timer.timeout.connect(lambda: None)

        def on_toggle_recording_emitter(is_start: bool):
            communicator.toggle_signal.emit(is_start)

        hotkey_manager.register_toggle(
            config['hotkeys']['toggle_recording'],
            on_toggle_recording_emitter
        )
        
        hotkey_manager.start()
        control_widget.show() # 启动时显示控制面板
        logger.info("Application started. Use the 'Exit' button or press Ctrl+C to quit.")
        
        sys.exit(app.exec())
            
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()