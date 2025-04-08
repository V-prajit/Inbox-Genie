import openai
from dotenv import load_dotenv
import os

load_dotenv()

client = openai.OpenAI(
    base_url=os.getenv('BASE_URL'),
    api_key='ollama',
)

try:
    model_name = "llama3.1:8b-instruct-q4_K_M"

    response = client.chat.completions.create(
        model= model_name,
        messages=[{
            "role": "user",
            "content": "Explain what an email assistant does in one paragraph."
        }],
        max_tokens=200
    )

    print("\nModel response:")
    print(response.choices[0].message.content)
    print("\nTest completed successfully!")

except Exception as e:
    print(f"Error connecting to Ollama API: {e}")
