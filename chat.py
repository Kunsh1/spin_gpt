import requests
import json
import re
import sys

def chat_with_api(prompt):
    url = "http://127.0.0.1:8000/api/chat"
    params = {"prompt": prompt}

    print(f"You: {prompt}")
    print("Bot: ", end="", flush=True)

    # stream=True is critical to keep the connection open and read chunks as they arrive
    with requests.get(url, params=params, stream=True) as response:
        # Check if the server threw an error (like a 500)
        response.raise_for_status()
        
        # Iterate over the raw bytes coming from the server
        for line in response.iter_lines():
            if line:
                # Decode the bytes to a string
                decoded_line = line.decode('utf-8')
                
                # We only care about the lines starting with "data: "
                if decoded_line.startswith("data: "):
                    json_str = decoded_line.replace("data: ", "", 1).strip()
                    
                    try:
                        # Parse the JSON payload {"text": "..."}
                        # Parse the JSON payload {"text": "..."}
                        data = json.loads(json_str)
                        if "text" in data:
                            raw_text = data["text"]
                            
                            # Clean out OpenAI's internal hidden markers ( ... )
                            clean_text = re.sub(r'.*?', '', raw_text)
                            
                            # Print the clean chunk to the terminal smoothly
                            print(clean_text, end="", flush=True)
                        elif "error" in data:
                            print(f"\n[Error: {data['error']}]")
                    except json.JSONDecodeError:
                        pass

    print("\n") # Add a final newline when the stream finishes

if __name__ == "__main__":
    while True:
        user_input = input("\nEnter your prompt (or 'exit' to quit): ")
        if user_input.lower() in ['exit', 'quit']:
            break
        chat_with_api(user_input)