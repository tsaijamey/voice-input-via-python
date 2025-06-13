# -*- coding: utf-8 -*-
"""
This module handles the output of the recognized text, including copying to
the clipboard and saving to a file.
"""

import pyperclip
from datetime import datetime
import os
import json


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


def save_to_file(
    raw_text: str,
    corrected_text: str,
    enhanced_text: str | None,
    vision_analysis: dict | None,
    output_dir: str = "recordings",
):
    """
    Saves all versions of recognized text and vision analysis to a timestamped JSON file.

    Args:
        raw_text (str): The raw text from ASR.
        corrected_text (str): The text after basic correction.
        enhanced_text (str | None): The final text after content enhancement.
        vision_analysis (dict | None): A dictionary with vision analysis results.
        output_dir (str): The directory where the file will be saved.
    """
    try:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{timestamp}_recognition_result.json"
        filepath = os.path.join(output_dir, filename)

        # 准备要保存的完整数据
        output_data = {
            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            "text_versions": {
                "raw_asr": raw_text,
                "corrected_asr": corrected_text,
                "enhanced_final": enhanced_text,
            },
            "vision_analysis": vision_analysis,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)

        print(f"✅ Full recognition result saved to file: {filepath}")
    except IOError as e:
        print(f"❌ Error saving to file: {e}")