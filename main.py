# main.py - Consolidated Version

import json
import time
import os
import platform # For countdown timer OS detection
from datetime import datetime # For filename timestamp

# Attempt to import pynput, but don't fail catastrophically if not found yet
try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    print("WARNING: pynput library not found. Hotkey functionality will be disabled. Falling back to manual console input.")

try:
    import pyperclip # For clipboard operations
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False
    print("WARNING: pyperclip library not found. Clipboard functionality will be disabled.")


# Local module imports
from audio_recorder import AudioRecorder
from asr_client import ASRClient
from llm_client import LLMClient
from countdown_timer import CountdownTimer

# --- Global Variables ---
CONFIG_FILE = "config.json"
app_config = None # Holds the loaded configuration
recorder_instance = None
asr_client_instance = None
llm_client_instance = None
countdown_timer_instance = None
final_transcribed_text = None # Stores the text after ASR and LLM processing

# --- Configuration Loading ---
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        print("INFO: Configuration loaded successfully.")
        return config_data
    except FileNotFoundError:
        print(f"CRITICAL_ERROR: Configuration file '{CONFIG_FILE}' not found. Application cannot start.")
        return None
    except json.JSONDecodeError:
        print(f"CRITICAL_ERROR: Could not decode JSON from '{CONFIG_FILE}'. Check its format. Application cannot start.")
        return None

# --- Core Functions / Event Handlers ---
def on_start_recording_triggered():
    global app_config, recorder_instance, countdown_timer_instance

    if not app_config:
        print("ERROR: Application configuration not loaded. Cannot start recording.")
        return
    if not recorder_instance:
        print("ERROR: AudioRecorder not initialized. Cannot start recording.")
        return

    if recorder_instance.is_recording:
        print("INFO: Recording is already in progress. Ignoring new start trigger.")
        return

    print("INFO: Event - Start recording triggered!")
    print("  STEP: Attempting to start audio recording...")
    recorder_instance.start_recording()

    if recorder_instance.is_recording:
        print("  SUCCESS: Audio recording started.")
        countdown_duration = app_config.get('recording', {}).get('countdown_seconds', 0)
        if countdown_duration > 0:
            print(f"  STEP: Starting countdown for {countdown_duration} seconds.")
            if countdown_timer_instance and countdown_timer_instance.timer_thread and countdown_timer_instance.timer_thread.is_alive():
                print("    INFO: Stopping existing countdown timer.")
                countdown_timer_instance.stop()

            countdown_timer_instance = CountdownTimer(countdown_duration, on_stop_recording_triggered, config=app_config)
            countdown_timer_instance.start() # This prints its own start message
        else:
            print("  INFO: No countdown configured. Recording will continue until manually stopped.")
    else:
        print("ERROR: Audio recording failed to start. Countdown not initiated.")

def on_stop_recording_triggered():
    global recorder_instance, asr_client_instance, llm_client_instance, countdown_timer_instance, final_transcribed_text

    print("INFO: Event - Stop recording triggered!")
    final_transcribed_text = None

    if countdown_timer_instance:
        print("  STEP: Handling countdown timer...")
        # countdown_timer.stop() is called within its own thread if timer completes.
        # If this stop is triggered externally (e.g. hotkey), then we call stop().
        # The CountdownTimer.stop() method itself sets an event and joins the thread.
        # It also calls _hide_display().
        if countdown_timer_instance.timer_thread and countdown_timer_instance.timer_thread.is_alive():
             print("    INFO: Countdown timer is active. Telling it to stop.")
             countdown_timer_instance.stop()
        else:
            print("    INFO: Countdown timer was not active or already finished.")
        countdown_timer_instance = None # Clear the instance

    if not recorder_instance:
        print("  ERROR: AudioRecorder not initialized. Cannot stop recording.")
        return

    if not recorder_instance.is_recording:
        print("  INFO: AudioRecorder indicates recording was not active. No audio to process.")
        return

    print("  STEP: Stopping audio recording...")
    output_file = recorder_instance.stop_recording() # This also prints messages

    if not output_file:
        print("  WARNING: AudioRecorder did not return an output file path. Processing cannot continue.")
        return
    if not os.path.exists(output_file):
        print(f"  ERROR: Audio file path '{output_file}' returned by recorder, but file not found. Processing cannot continue.")
        return

    print(f"  SUCCESS: Audio recording stopped. Output file at: {output_file}")

    # ASR Processing
    print("  STEP: Starting ASR processing...")
    raw_transcription = None
    if asr_client_instance:
        raw_transcription = asr_client_instance.transcribe_audio_file(output_file)
        if raw_transcription:
            print(f"    SUCCESS: ASR Transcription completed (first 100 chars): '{str(raw_transcription)[:100]}...'")
        else:
            print("    WARNING: ASR transcription failed or returned empty.")
    else:
        print("    SKIPPING: ASRClient not initialized.")

    # LLM Processing
    if raw_transcription:
        print("  STEP: Starting LLM processing...")
        if llm_client_instance:
            corrected_text_from_llm = llm_client_instance.correct_text(raw_transcription)
            if corrected_text_from_llm and corrected_text_from_llm.strip() and corrected_text_from_llm.lower() != raw_transcription.lower():
                print(f"    SUCCESS: LLM correction completed (first 100 chars): '{str(corrected_text_from_llm)[:100]}...'")
                final_transcribed_text = corrected_text_from_llm
            else:
                print("    INFO: LLM returned no significant changes or empty. Using raw ASR text.")
                final_transcribed_text = raw_transcription
        else:
            print("    SKIPPING: LLMClient not initialized. Using raw ASR text.")
            final_transcribed_text = raw_transcription
    else:
         print("  INFO: No text from ASR. Skipping LLM processing.")
         final_transcribed_text = None

    # Output and Cleanup
    if final_transcribed_text:
        print(f"  STEP: Finalizing output for text (length {len(final_transcribed_text)}): '{final_transcribed_text[:100]}...'")
        print("    ACTION: Copying to clipboard...")
        copy_text_to_clipboard(final_transcribed_text)
        print("    ACTION: Saving to file...")
        saved_filepath = save_text_to_file(final_transcribed_text, directory=".")
        if saved_filepath:
            print(f"    SUCCESS: Text saved to {saved_filepath}")
        else:
            print("    WARNING: File saving failed for the final text.")
    else:
        print("  INFO: No final text was generated. Skipping clipboard and file output.")

    # Optional: Audio file cleanup (currently commented out in provided final script)
    try:
        if os.path.exists(output_file):
            print(f"  INFO: Temporary audio file {output_file} was processed. Consider manual cleanup if needed.")
    except OSError as e:
        print(f"  WARNING: Error during check/cleanup of temporary audio file {output_file}: {e}")

def format_hotkey_for_pynput(hotkey_str):
    parts = hotkey_str.lower().split('+')
    formatted_parts = []
    for part in parts:
        part = part.strip()
        if len(part) > 1:
            formatted_parts.append(f'<{part}>')
        else:
            formatted_parts.append(part)
    return '+'.join(formatted_parts)

def copy_text_to_clipboard(text_to_copy):
    if not PYPERCLIP_AVAILABLE:
        print("CLIPBOARD_ERROR: pyperclip library not available. Cannot copy to clipboard.")
        return
    if not text_to_copy:
        print("CLIPBOARD: No text to copy.")
        return
    try:
        pyperclip.copy(text_to_copy)
        print(f"CLIPBOARD: Text copied to clipboard (length: {len(text_to_copy)}).")
    except pyperclip.PyperclipException as e:
        print(f"CLIPBOARD_ERROR: Failed to copy text to clipboard: {e}")
    except Exception as e:
        print(f"CLIPBOARD_ERROR: An unexpected error occurred: {e}")

def save_text_to_file(text_to_save, directory=".", prefix="speech_recognized"):
    if not text_to_save:
        print("FILE_SAVE: No text to save.")
        return None
    try:
        current_date = datetime.now().strftime("%Y-%m-%d")
        filename = f"{current_date}_{prefix}.txt"
        filepath = os.path.join(directory, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(text_to_save)
        print(f"FILE_SAVE: Text saved to {filepath}")
        return filepath
    except IOError as e:
        print(f"FILE_SAVE_ERROR: Could not write to file {filepath}: {e}")
        return None
    except Exception as e:
        print(f"FILE_SAVE_ERROR: An unexpected error occurred: {e}")
        return None

def main():
    global app_config, recorder_instance, asr_client_instance, llm_client_instance, PYNPUT_AVAILABLE

    print("INFO: Starting Voice Input Tool...")
    app_config = load_config()
    if not app_config:
        # load_config() already prints critical error
        return

    # Print some loaded config details for user verification (excluding sensitive info)
    print("INFO: Loaded configuration summary:")
    print(f"  Hotkeys: Start={app_config.get('hotkeys',{}).get('start_recording')}, Stop={app_config.get('hotkeys',{}).get('stop_recording')}")
    print(f"  Recording: Countdown={app_config.get('recording',{}).get('countdown_seconds')}s, Format={app_config.get('recording',{}).get('audio_format')}")
    print(f"  ASR Provider: Name={app_config.get('asr_provider',{}).get('name')}, Endpoint={app_config.get('asr_provider',{}).get('endpoint')}")
    print(f"  LLM Provider: Name={app_config.get('llm_provider',{}).get('name')}, Endpoint={app_config.get('llm_provider',{}).get('endpoint')}")
    proxy_conf = app_config.get('proxy',{})
    print(f"  Proxy: HTTP={proxy_conf.get('http')}, HTTPS={proxy_conf.get('https')}")


    print("\nINFO: Initializing components...")
    try:
        recorder_instance = AudioRecorder(config=app_config.get("recording", {}))
        print("  INFO: AudioRecorder initialized successfully.")
    except Exception as e:
        print(f"  CRITICAL_ERROR: Failed to initialize AudioRecorder: {e}. Application cannot proceed with recording.")
        return

    try:
        asr_client_instance = ASRClient(config=app_config)
        print("  INFO: ASRClient initialized successfully.")
    except ValueError as ve:
        print(f"  WARNING: Error initializing ASRClient: {ve}. ASR functionality will be disabled.")
    except Exception as e:
        print(f"  WARNING: Unexpected error initializing ASRClient: {e}. ASR functionality will be disabled.")

    try:
        llm_client_instance = LLMClient(config=app_config)
        print("  INFO: LLMClient initialized successfully.")
    except ValueError as ve:
        print(f"  WARNING: Error initializing LLMClient: {ve}. LLM correction will be disabled.")
    except Exception as e:
        print(f"  WARNING: Unexpected error initializing LLMClient: {e}. LLM correction will be disabled.")

    print("INFO: Component initialization complete.\n")
    hotkey_listener_active = False
    listener_instance_for_main = None # To keep a reference for stopping

    if PYNPUT_AVAILABLE:
        hotkey_cfg = app_config.get("hotkeys", {})
        start_hotkeys_str = hotkey_cfg.get("start_recording", [])
        stop_hotkeys_str = hotkey_cfg.get("stop_recording", [])

        if start_hotkeys_str and stop_hotkeys_str:
            hotkey_map = {}
            for hk_str in start_hotkeys_str:
                hotkey_map[format_hotkey_for_pynput(hk_str)] = on_start_recording_triggered
            for hk_str in stop_hotkeys_str:
                hotkey_map[format_hotkey_for_pynput(hk_str)] = on_stop_recording_triggered

            if hotkey_map:
                try:
                    print("INFO: Attempting to start global hotkey listener...")
                    listener_instance_for_main = keyboard.GlobalHotKeys(hotkey_map)
                    listener_instance_for_main.start()
                    print("SUCCESS: pynput GlobalHotKeys listener started.")
                    hotkey_listener_active = True
                except Exception as e:
                    print(f"WARNING: Failed to start pynput.keyboard.GlobalHotKeys: {e}")
                    PYNPUT_AVAILABLE = False # Explicitly disable if runtime error
                    print("INFO: Falling back to manual console input.")
            else:
                print("WARNING: No valid hotkeys configured. Falling back to manual input.")
        else:
            print("WARNING: Start/stop hotkeys not fully defined in config. Falling back to manual input.")

    if hotkey_listener_active and PYNPUT_AVAILABLE: # PYNPUT_AVAILABLE re-check
        print("INFO: Application is running with hotkey listener. Press Ctrl+C in this terminal to exit.")
        try:
            if listener_instance_for_main:
                 listener_instance_for_main.join() # Block main thread to keep listener alive
            else: # Should not happen if hotkey_listener_active is True
                 while True: time.sleep(1)
        except KeyboardInterrupt:
            print("\nINFO: KeyboardInterrupt detected. Shutting down...")
        except Exception as e: # Catch other exceptions that might kill the listener join
            print(f"\nERROR: Hotkey listener main loop encountered an error: {e}. Shutting down...")
        finally:
            if listener_instance_for_main and listener_instance_for_main.is_alive():
                print("INFO: Stopping hotkey listener...")
                listener_instance_for_main.stop()
            print("INFO: Application terminated (hotkey mode).")
    else:
        print("\nMANUAL MODE: Type 'start' to trigger recording, 'stop' to end recording.")
        print("Type 'exit' to quit.")
        try:
            while True:
                command = input("> ").strip().lower()
                if command == "start":
                    on_start_recording_triggered()
                elif command == "stop":
                    on_stop_recording_triggered()
                elif command == "exit":
                    print("INFO: Exiting manual mode...")
                    break
                else:
                    print(f"Unknown command: {command}")
        except KeyboardInterrupt:
            print("\nINFO: Exiting manual mode via KeyboardInterrupt...")
        finally:
            print("INFO: Application terminated (manual mode).")

if __name__ == "__main__":
    main()
