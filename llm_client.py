import requests
import json # For error handling and request payload
import os

class LLMClient:
    def __init__(self, config):
        self.llm_config = config.get('llm_provider', {})
        self.proxy_config = config.get('proxy', {})

        if not self.llm_config.get('endpoint') or not self.llm_config.get('api_key'):
            raise ValueError("LLM endpoint or API key is missing in the configuration.")

    def correct_text(self, text_to_correct):
        if not text_to_correct or not text_to_correct.strip():
            print("LLMClient: No text provided for correction.")
            return text_to_correct # Return original if empty or whitespace

        endpoint = self.llm_config['endpoint']
        api_key = self.llm_config['api_key']
        model_name = self.llm_config.get('name', 'llama-3.3-70b-versatile') # Default or from config

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        proxies = {}
        if self.proxy_config.get('http'):
            proxies['http'] = self.proxy_config['http']
        if self.proxy_config.get('https'):
            proxies['https'] = self.proxy_config['https']

        # Craft the prompt for correction based on semantics
        # The prompt is crucial for how the LLM behaves.
        prompt_instruction = (
            "You are an expert assistant specialized in correcting Automatic Speech Recognition (ASR) errors. "
            "The following text is a transcription from an ASR system. It may contain errors due to segmentation "
            "or misinterpretation of spoken language. Your task is to analyze the text, understand its semantics, "
            "and correct any errors to produce a fluent, grammatically correct, and semantically sound version. "
            "Focus on making the text natural and accurate based on likely spoken intent. "
            "Only return the corrected text, without any preamble or explanation."
        )

        # Payload structure depends on Groq API for Llama models.
        # Common structure involves a 'messages' array with 'role' and 'content'.
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": prompt_instruction},
                {"role": "user", "content": text_to_correct}
            ],
            "temperature": 0.3, # Adjust for more deterministic output
            # "max_tokens": len(text_to_correct.split()) + 50 # Optional: limit output length
        }

        print(f"Sending text to LLM endpoint: {endpoint} for correction.")
        if proxies:
            print(f"Using proxy for LLM: {proxies}")

        try:
            response = requests.post(endpoint, headers=headers, json=payload, proxies=proxies, timeout=120) # 120s timeout for LLM
            response.raise_for_status()

            response_json = response.json()

            # Extract corrected text. This depends heavily on Groq's Llama API response structure.
            # Example 1: {"choices": [{"message": {"content": "corrected text"}}]}
            # Example 2: {"output": "corrected text"}
            corrected_text = None
            if "choices" in response_json and response_json["choices"]:
                choice = response_json["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    corrected_text = choice["message"]["content"].strip()
                elif "text" in choice: # Some APIs might use 'text' directly in choice
                    corrected_text = choice["text"].strip()
            elif "output" in response_json: # Simpler structure
                corrected_text = response_json["output"].strip()
            elif "text" in response_json: # Some APIs might return text directly
                 corrected_text = response_json["text"].strip()


            if corrected_text:
                print("LLM correction successful.")
                return corrected_text
            else:
                print("Error: Could not extract corrected text from LLM response.")
                print(f"Full LLM response: {response_json}")
                return text_to_correct # Return original text as fallback

        except requests.exceptions.Timeout:
            print(f"Error: Request to LLM endpoint timed out.")
            return text_to_correct
        except requests.exceptions.RequestException as e:
            print(f"Error during LLM request: {e}")
            if e.response is not None:
                try:
                    error_details = e.response.json()
                    print(f"Error details from LLM server: {error_details}")
                except json.JSONDecodeError:
                    print(f"Error details from LLM server (non-JSON): {e.response.text}")
            return text_to_correct
        except Exception as e:
            print(f"An unexpected error occurred in LLMClient: {e}")
            return text_to_correct # Fallback to original text

# Example usage (conceptual)
if __name__ == '__main__':
    print("LLMClient module direct test (conceptual):")
    mock_config_data = {
        "llm_provider": {
            "name": "groq_llama3_70b",
            "endpoint": "YOUR_GROQ_LLAMA3_ENDPOINT_HERE", # Replace
            "api_key": "YOUR_GROQ_API_KEY_HERE"  # Replace
        },
        "proxy": {
            "http": "http://localhost:7890",
            "https": "http://localhost:7890"
        }
    }
    # try:
    #     client = LLMClient(config=mock_config_data)
    #     test_text = "This is a testt of the emrgency broadcast systemm."
    #     corrected = client.correct_text(test_text)
    #     print(f"Original: {test_text}")
    #     print(f"Corrected: {corrected}")
    # except ValueError as ve:
    #     print(ve)
    print("LLMClient conceptual test finished.")
