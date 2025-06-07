import time
import threading
import subprocess
import tkinter as tk
import platform

class CountdownTimer:
    def __init__(self, duration_seconds, stop_callback_func, config=None):
        self.duration_seconds = duration_seconds
        self.stop_callback = stop_callback_func
        self.timer_thread = None
        self.stop_event = threading.Event()
        self.current_os = platform.system().lower()
        self.config = config or {} # General app config if needed

        # For Tkinter window on Windows
        self.tk_root = None
        self.tk_label = None

    def _update_display(self, seconds_left):
        message = f"Recording... {seconds_left}s left"
        print(f"DISPLAY_STUB: {message}") # Always print for sandbox

        if self.current_os == "darwin": # macOS
            try:
                # Simple notification. A borderless window is much more complex.
                # This will create a new notification each second, which is not ideal.
                # A better way would be to manage one AppleScript process or use pyobjc.
                # For this exercise, a simple notification is a placeholder.
                script = f'display notification "{message}" with title "Voice Recorder"'
                subprocess.run(["osascript", "-e", script], timeout=0.5)
            except Exception as e:
                print(f"macOS display notification error: {e}")

        elif self.current_os == "windows":
            try:
                if not self.tk_root: # Create window on first update
                    self.tk_root = tk.Tk()
                    self.tk_root.title("Countdown")
                    self.tk_root.attributes("-topmost", True) # Keep on top
                    # Make it somewhat like an overlay: remove decorations, set geometry
                    self.tk_root.overrideredirect(True)
                    # Position it (e.g., top right, needs screen dimensions for accuracy)
                    # For simplicity, let's put it near screen center initially
                    screen_width = self.tk_root.winfo_screenwidth()
                    screen_height = self.tk_root.winfo_screenheight()
                    win_width = 200
                    win_height = 50
                    x = (screen_width // 2) - (win_width // 2)
                    y = (screen_height // 5) # Near top
                    self.tk_root.geometry(f"{win_width}x{win_height}+{x}+{y}")

                    self.tk_label = tk.Label(self.tk_root, text=message, font=("Arial", 16))
                    self.tk_label.pack(expand=True, fill=tk.BOTH)
                    self.tk_root.protocol("WM_DELETE_WINDOW", self._on_tk_close) # Handle explicit close

                if self.tk_label:
                    self.tk_label.config(text=message)
                if self.tk_root:
                    self.tk_root.update_idletasks()
                    self.tk_root.update()
            except Exception as e:
                print(f"Windows Tkinter display error: {e}")
                # If Tkinter fails, we rely on console print.
                if self.tk_root:
                    try:
                        self.tk_root.destroy()
                    except: pass # Best effort
                    self.tk_root = None
                    self.tk_label = None


    def _hide_display(self):
        print("DISPLAY_STUB: Hiding countdown display")
        if self.current_os == "darwin":
            # Notifications hide automatically. If it were a persistent dialog, it would need closing.
            pass
        elif self.current_os == "windows":
            if self.tk_root:
                try:
                    self.tk_root.destroy()
                except Exception as e:
                    print(f"Error destroying Tkinter window: {e}")
                finally:
                    self.tk_root = None
                    self.tk_label = None

    def _on_tk_close(self):
        # If user closes the Tk window, stop the timer and recording
        print("Tkinter countdown window closed by user.")
        self.stop_event.set() # Signal the timer loop to stop
        # self.stop_callback() # This might be called too early if timer loop also calls it
        # It's safer to let the timer loop finish its current iteration and call stop_callback.
        # Or, explicitly call the stop_recording logic if the countdown window is closed.
        # For now, setting the event is sufficient for the timer loop to exit.
        # The main recording stop should also handle stopping this timer.


    def _timer_loop(self):
        try:
            for i in range(self.duration_seconds, -1, -1):
                if self.stop_event.is_set():
                    print("Countdown timer loop: Stop event received.")
                    break

                self._update_display(i)

                if i == 0: # Countdown finished
                    print("Countdown finished.")
                    if self.stop_callback:
                        # Schedule the callback to run in the main thread if it interacts with GUI/shared state
                        # For now, direct call. If stop_callback modifies Tkinter things, it might need `tk_root.after`.
                        self.stop_callback()
                    break # Exit loop

                time.sleep(1) # Wait for 1 second
        except Exception as e:
            print(f"Error in timer loop: {e}")
        finally:
            self._hide_display()
            print("Countdown timer thread finished.")


    def start(self):
        if self.timer_thread and self.timer_thread.is_alive():
            print("Timer is already running.")
            return

        self.stop_event.clear()
        self.timer_thread = threading.Thread(target=self._timer_loop)
        self.timer_thread.daemon = True # Allow main program to exit even if thread is running
        self.timer_thread.start()
        print(f"Countdown timer started for {self.duration_seconds} seconds.")

    def stop(self):
        print("Stopping countdown timer...")
        self.stop_event.set()
        self._hide_display() # Attempt to hide display immediately
        if self.timer_thread and self.timer_thread.is_alive():
            print("Waiting for timer thread to join...")
            self.timer_thread.join(timeout=2) # Wait for thread to finish
            if self.timer_thread.is_alive():
                print("Timer thread did not join in time.")
        self.timer_thread = None
        print("Countdown timer stopped.")

# Example Usage (conceptual)
if __name__ == '__main__':
    print("CountdownTimer module direct test (conceptual):")
    def my_callback():
        print("TEST CALLBACK: Countdown finished or stopped!")

    # Test for macOS (will likely fail in sandbox)
    # timer_mac = CountdownTimer(5, my_callback)
    # timer_mac.start()
    # time.sleep(2); timer_mac.stop()

    # Test for Windows (will likely fail in sandbox)
    # timer_win = CountdownTimer(5, my_callback)
    # timer_win.start()
    # time.sleep(6) # Let it finish

    print("Conceptual test finished. Actual display requires a suitable environment.")
