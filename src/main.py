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
from services.input_automation_service import InputAutomationService

class Communicate(QObject):
    """用于跨线程通信的信号类"""
    toggle_signal = Signal(bool, object)
    transcription_update_signal = Signal(str, bool)  # 信号：(文本, 是否追加)

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
        config_loader = ConfigLoader()
        config = config_loader.load()
        logger.info("Configuration loaded successfully")
        
        # --- 初始化服务和状态 ---
        hotkey_manager = HotkeyManager()
        recording_service = RecordingService(config['recording'])
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
        raw_transcript_list = [] # 新增：用于存储原始未修正的文本
        screen_context_result = None
        focused_window_at_start = None # 新增：用于保存录音开始时的窗口
        

        def transcription_worker():
            min_chunk_samples = int(0.5 * recording_service.sample_rate)

            while True:
                audio_chunk = audio_queue.get()
                if audio_chunk is None:
                    audio_queue.task_done()
                    break

                if len(audio_chunk) < min_chunk_samples:
                    logger.info(f"Skipping a short audio chunk with {len(audio_chunk)} samples.")
                    audio_queue.task_done()
                    continue
                
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
                    logger.info(f"实时转录 (原始): {transcript}")
                    raw_transcript_list.append(transcript)
                    
                    corrected_chunk = asr_service.correct_text(transcript)
                    logger.info(f"实时转录 (修正): {corrected_chunk}")
                    
                    full_transcript.append(corrected_chunk)
                    current_full_text = ' '.join(full_transcript)
                    logger.info(f"当前完整文本: {current_full_text}")
                    communicator.transcription_update_signal.emit(current_full_text, False) # False表示覆盖
                
                audio_queue.task_done()
            logger.info("Transcription worker finished.")
        
        communicator = Communicate()
        
        # 连接转写更新信号到UI控件
        communicator.transcription_update_signal.connect(control_widget.update_transcription) # 连接信号到槽
        
        def handle_toggle_recording(start: bool, window=None):
            nonlocal is_recording, transcription_worker_thread, vision_worker_thread, full_transcript, screen_context_result, raw_transcript_list, focused_window_at_start
            
            enhancement_enabled = config['services']['content_enhancement'].get('enabled', False)

            if start and not is_recording:
                is_recording = True
                focused_window_at_start = window
                logger.info("Recording started...")
                
                if enhancement_enabled:
                    def vision_worker():
                        nonlocal screen_context_result
                        logger.info("Capturing and analyzing screen...")
                        screenshot = take_screenshot()
                        resized_screenshot = resize_image(screenshot, max_screenshot_width)
                        save_screenshot(resized_screenshot)
                        screen_context_result = vision_service.analyze_screenshot(resized_screenshot)
                        logger.info("Screen analysis complete.")
                    vision_worker_thread = threading.Thread(target=vision_worker, daemon=True)
                    vision_worker_thread.start()
                else:
                    screen_context_result = None
                    vision_worker_thread = None

                full_transcript = []
                raw_transcript_list = []
                while not audio_queue.empty():
                    audio_queue.get_nowait()

                transcription_worker_thread = threading.Thread(target=transcription_worker, daemon=True)
                transcription_worker_thread.start()
                
                countdown = config['recording'].get('countdown_seconds', 60)
                control_widget.set_idle_state()  # 确保清空上一次的结果
                control_widget.transcription_label.clear()
                control_widget.set_recording_state(countdown)
                
                recording_service.start_recording(audio_queue)

            elif not start and is_recording:
                is_recording = False
                logger.info("Recording stopped...")
                
                recording_service.stop_recording()
                audio_queue.put(None)
                
                logger.info("Waiting for transcription and vision analysis to complete...")
                if transcription_worker_thread:
                    transcription_worker_thread.join(timeout=10.0)
                if vision_worker_thread:
                    vision_worker_thread.join(timeout=20.0)

                raw_text = ' '.join(raw_transcript_list)
                corrected_text = ' '.join(full_transcript)
                logger.info(f"最终识别文本 (原始): {raw_text}")
                logger.info(f"最终识别文本 (修正): {corrected_text}")
                logger.info(f"最终屏幕上下文: {screen_context_result}")

                final_text_for_processing = corrected_text if corrected_text else raw_text
                output_text = final_text_for_processing
                enhanced_text_result = None

                if enhancement_enabled and final_text_for_processing and screen_context_result:
                    logger.info("Enhancing text with screen context...")
                    enhanced_text_result = enhancement_service.enhance_text(final_text_for_processing, screen_context_result)
                    logger.info(f"增强后文本: {enhanced_text_result}")
                    output_text = enhanced_text_result
                elif not enhancement_enabled:
                    logger.info("Content enhancement is disabled. Skipping.")
                elif not screen_context_result:
                     logger.warning("Vision analysis failed or returned no result. Falling back to transcript.")

                if output_text:
                    if config['output'].get('mode', 'clipboard') == 'paste' and focused_window_at_start:
                        InputAutomationService.paste_to_window(focused_window_at_start, output_text)
                    else:
                        copy_to_clipboard(output_text)
                else:
                    logger.warning("没有识别到任何文本，跳过输出。")

                save_to_file(
                    raw_text=raw_text,
                    corrected_text=corrected_text,
                    enhanced_text=enhanced_text_result,
                    vision_analysis=screen_context_result
                )

                # set_finished_state 内部会调用 update_transcription(text, append=False)
                # 这会用最终文本覆盖掉实时追加的内容
                control_widget.set_finished_state(output_text or "")
                focused_window_at_start = None

        communicator.toggle_signal.connect(handle_toggle_recording)
        control_widget.start_requested.connect(lambda: handle_toggle_recording(True))
        control_widget.stop_requested.connect(lambda: handle_toggle_recording(False))
        
        def shutdown_application():
            logger.info("Application shutting down...")
            hotkey_manager.stop()
            
            if is_recording:
                handle_toggle_recording(False)

            if transcription_worker_thread and transcription_worker_thread.is_alive():
                audio_queue.put(None)
                transcription_worker_thread.join(timeout=5.0)

            logger.info("Shutdown complete.")
            QApplication.quit()

        control_widget.exit_requested.connect(shutdown_application)
        signal.signal(signal.SIGINT, lambda sig, frame: shutdown_application())
        
        timer = QTimer()
        timer.start(500)
        timer.timeout.connect(lambda: None)

        def on_toggle_recording_emitter(is_start: bool, window=None):
            communicator.toggle_signal.emit(is_start, window)

        hotkey_manager.register_toggle(
            config['hotkeys']['toggle_recording'],
            on_toggle_recording_emitter
        )
        
        hotkey_manager.start()
        
        # --- UI 与配置双向绑定 ---
        # 1. 应用启动时，根据配置设置UI
        enhancement_enabled = config['services']['content_enhancement'].get('enabled', False)
        control_widget.set_enhancement_state(enhancement_enabled)

        # 2. 当UI开关变化时，更新配置并保存
        def on_enhancement_toggled(enabled):
            config['services']['content_enhancement']['enabled'] = enabled
            # 更新原始配置以备保存
            if 'original_services' in config and 'content_enhancement' in config['original_services']:
                config['original_services']['content_enhancement']['enabled'] = enabled
            config_loader.save(config)
            logger.info(f"Content enhancement set to: {enabled}")

        control_widget.enhancement_toggled.connect(on_enhancement_toggled)
        
        control_widget.show()
        logger.info("Application started. Use the 'Exit' button or press Ctrl+C to quit.")
        
        sys.exit(app.exec())
            
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()