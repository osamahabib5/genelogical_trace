from openai import OpenAI

endpoint = "https://sofafea-foundry-dom.services.ai.azure.com/openai/v1/"
model_name = "gpt-oss-120b"
deployment_name = "gpt-oss-workhorse"

api_key = "3UDqHiEQLaoGznTgXbgjXsZIS06VhLzdSBnymFYkntPCNB2IXRepJQQJ99CCACHYHv6XJ3w3AAAAACOG9Xjo"

client = OpenAI(
    base_url=f"{endpoint}",
    api_key=api_key
)

completion = client.chat.completions.create(
    model=deployment_name,
    messages=[
        {
            "role": "user",
            "content": "What is the capital of France?",
        }
    ],
)

print(completion.choices[0].message)