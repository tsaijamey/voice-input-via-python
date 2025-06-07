# -*- coding: utf-8 -*-
"""
This module handles the output of the recognized text, including copying to
the clipboard and saving to a file.
"""

import pyperclip
from datetime import datetime
import os


def copy_to_clipboard(text: str):
    """
    Copies the given text to the system clipboard.

    Args:
        text (str): The text to be copied.
    """
    try:
        pyperclip.copy(text)
        print("✅ Text copied to clipboard.")
    except pyperclip.PyperclipException as e:
        print(f"❌ Error copying to clipboard: {e}")


def save_to_file(text: str, output_dir: str = "recordings"):
    """
    Saves the given text to a file with a timestamped name.

    Args:
        text (str): The text to be saved.
        output_dir (str): The directory where the file will be saved.
                          Defaults to "recordings".
    """
    try:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{timestamp}_speech_recognized.txt"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"✅ Text saved to file: {filepath}")
    except IOError as e:
        print(f"❌ Error saving to file: {e}")