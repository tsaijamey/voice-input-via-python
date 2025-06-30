import webrtcvad
import numpy as np

def is_speech(audio_chunk: np.ndarray, sample_rate: int, vad_aggressiveness: int = 1) -> bool:
    """
    使用 webrtcvad 判断音频块中是否包含语音。
    """
    if audio_chunk.dtype != np.int16:
        # VAD 库要求 int16
        return False

    vad = webrtcvad.Vad(vad_aggressiveness)
    
    # VAD 库要求帧长度为 10, 20, 或 30 ms
    frame_duration_ms = 30 
    frame_samples = int(sample_rate * frame_duration_ms / 1000)
    
    num_frames = len(audio_chunk) // frame_samples
    if num_frames == 0:
        return False

    num_speech_frames = 0
    for i in range(num_frames):
        start = i * frame_samples
        end = start + frame_samples
        frame = audio_chunk[start:end].tobytes()
        if vad.is_speech(frame, sample_rate):
            num_speech_frames += 1
    
    # 如果超过一定比例的帧是语音，则认为整个块是语音 (例如 50%)
    speech_ratio = num_speech_frames / num_frames
    return speech_ratio > 0.5 
