import requests
import json # For error handling if response is JSON
import os

class ASRClient:
    def __init__(self, config):
        self.asr_config = config.get('asr_provider', {})
        self.proxy_config = config.get('proxy', {})

        if not self.asr_config.get('endpoint') or not self.asr_config.get('api_key'):
            raise ValueError("ASR endpoint or API key is missing in the configuration.")

    def transcribe_audio_file(self, audio_file_path):
        if not os.path.exists(audio_file_path):
            print(f"Error: Audio file not found at {audio_file_path}")
            return None

        endpoint = self.asr_config['endpoint']
        api_key = self.asr_config['api_key']

        headers = {
            "Authorization": f"Bearer {api_key}",
            # "Content-Type": "audio/wav" # The requests library's files multipart upload normally sets this.
                                          # Add explicitly if API requires it for specific non-multipart uploads.
        }

        proxies = {}
        if self.proxy_config.get('http'):
            proxies['http'] = self.proxy_config['http']
        if self.proxy_config.get('https'):
            proxies['https'] = self.proxy_config['https']

        if not proxies:
            print("Warning: No proxy configuration found. Making a direct request.")


        print(f"Sending {audio_file_path} to ASR endpoint: {endpoint}")
        if proxies:
            print(f"Using proxy: {proxies}")

        try:
            with open(audio_file_path, 'rb') as f_audio:
                files = {'file': (os.path.basename(audio_file_path), f_audio, 'audio/wav')}
                # Depending on the API, it might expect the audio data directly in the body
                # or as a multipart form data. 'files' argument implies multipart.
                # If API expects raw bytes: data=f_audio, and set Content-Type header.
                # Groq's Whisper API likely uses multipart/form-data for file uploads.

                response = requests.post(endpoint, headers=headers, files=files, proxies=proxies, timeout=60) # 60s timeout

            response.raise_for_status() # Raises an HTTPError for bad responses (4XX or 5XX)

            # Assuming the response is JSON and contains the transcription in a 'text' field
            # This might need adjustment based on Groq Whisper API's actual response structure
            # Example: {"text": "transcribed words..."} or {"results": [{"transcript": "..."}]}
            response_json = response.json()
            transcribed_text = response_json.get("text") # Adjust based on actual API

            if transcribed_text is None: # Try another common structure
                results = response_json.get("results")
                if results and isinstance(results, list) and len(results) > 0:
                     if isinstance(results[0], dict) and "transcript" in results[0]:
                        transcribed_text = results[0].get("transcript")


            if transcribed_text is not None:
                print("ASR Transcription successful.")
                return transcribed_text
            else:
                print("Error: 'text' or 'results[0].transcript' field not found in ASR response.")
                print(f"Full ASR response: {response_json}")
                return None

        except requests.exceptions.Timeout:
            print(f"Error: Request to ASR endpoint timed out.")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Error during ASR request: {e}")
            # Try to print response body if available, for more debug info
            if e.response is not None:
                try:
                    error_details = e.response.json()
                    print(f"Error details from server: {error_details}")
                except json.JSONDecodeError:
                    print(f"Error details from server (non-JSON): {e.response.text}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred in ASRClient: {e}")
            return None

# Example usage (optional, for testing module directly)
if __name__ == '__main__':
    # This example won't run in the sandbox due to missing config/network/files
    print("ASRClient module direct test (conceptual):")
    mock_config_data = {
        "asr_provider": {
            "name": "groq_whisper",
            "endpoint": "YOUR_GROQ_WHISPER_ENDPOINT_HERE", # Replace with a mock server if testing
            "api_key": "YOUR_GROQ_API_KEY_HERE"
        },
        "proxy": {
            "http": "http://localhost:7890", # Replace if needed
            "https": "http://localhost:7890"
        }
    }

    # Create a dummy config and audio file for local testing if needed
    # with open("dummy_config.json", "w") as f: json.dump(mock_config_data, f)
    # with open("dummy_audio.wav", "wb") as f: f.write(b"dummydata") # Real wav needed

    # try:
    #     client = ASRClient(config=mock_config_data)
    #     # Replace "dummy_audio.wav" with an actual wav file path for testing
    #     # transcription = client.transcribe_audio_file("dummy_audio.wav")
    #     # if transcription:
    #     #    print(f"Test Transcription: {transcription}")
    #     # else:
    #     #    print("Test Transcription failed.")
    # except ValueError as ve:
    #    print(ve)
    # finally:
    #    if os.path.exists("dummy_config.json"): os.remove("dummy_config.json")
    #    if os.path.exists("dummy_audio.wav"): os.remove("dummy_audio.wav")
    print("ASRClient conceptual test finished.")
