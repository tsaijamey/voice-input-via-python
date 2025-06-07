import sounddevice as sd
import numpy as np
import wave
import time
import os

class AudioRecorder:
    def __init__(self, config):
        self.config = config
        self.samplerate = 44100  # Standard sample rate
        self.channels = 1        # Mono audio
        self.dtype = 'int16'     # Data type for recording
        self.frames = []
        self.is_recording = False
        self.stream = None
        self.output_filename = "temp_recording.wav" # Default, can be changed

    def _callback(self, indata, frames, time, status):
        if status:
            print(f"Audio callback status: {status}")
        if self.is_recording:
            self.frames.append(indata.copy())

    def start_recording(self):
        if self.is_recording:
            print("Already recording.")
            return

        print(f"Starting recording... Sample rate: {self.samplerate}, Channels: {self.channels}")
        self.frames = []
        try:
            self.stream = sd.InputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                dtype=self.dtype,
                callback=self._callback
            )
            self.stream.start()
            self.is_recording = True
            print("Recording started.")
        except Exception as e:
            print(f"Error starting audio stream: {e}")
            self.is_recording = False # Ensure state is correct
            if self.stream: # Try to clean up if stream object was created
                try:
                    self.stream.close()
                except Exception as e_close:
                    print(f"Error closing stream during start_recording failure: {e_close}")
            self.stream = None


    def stop_recording(self):
        if not self.is_recording:
            print("Not recording.")
            return None # Or raise an error

        print("Stopping recording...")
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                print(f"Error stopping/closing audio stream: {e}")
            finally:
                self.stream = None # Clear the stream object

        self.is_recording = False

        if not self.frames:
            print("No frames recorded.")
            return None

        # Ensure directory exists if path is complex, for now current dir
        # os.makedirs(os.path.dirname(self.output_filename), exist_ok=True)

        try:
            print(f"Saving recording to {self.output_filename}...")
            wf = wave.open(self.output_filename, 'wb')
            wf.setnchannels(self.channels)
            wf.setsampwidth(sd.check_dtype(self.dtype).itemsize) # Get sample width from dtype
            wf.setframerate(self.samplerate)

            # Concatenate all frames
            recording_data = np.concatenate(self.frames, axis=0)
            wf.writeframes(recording_data.tobytes())
            wf.close()
            print(f"Recording saved to {self.output_filename}")
            return self.output_filename
        except Exception as e:
            print(f"Error saving .wav file: {e}")
            return None
        finally:
            self.frames = [] # Clear frames after attempting to save

# Example usage (optional, for testing module directly)
if __name__ == '__main__':
    mock_config = {'recording': {'audio_format': 'wav'}} # Simplified config
    recorder = AudioRecorder(config=mock_config)

    print("Testing AudioRecorder: Starting recording for 3 seconds...")
    recorder.start_recording()
    if recorder.is_recording: # Check if recording actually started
        time.sleep(3)
        output_file = recorder.stop_recording()
        if output_file and os.path.exists(output_file):
            print(f"Test successful. File '{output_file}' created.")
            # os.remove(output_file) # Clean up test file
        elif output_file:
             print(f"Test problematic. File '{output_file}' was named but not found.")
        else:
            print("Test failed. No output file produced or recording did not start.")
    else:
        print("Test failed: Recording did not start.")
