import os
from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types
from app import get_weather, get_mandi_price, tool_functions, SYSTEM_PROMPT_TEMPLATE

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def test_agent_query(query: str, language="Hindi"):
    sys_instructions = SYSTEM_PROMPT_TEMPLATE.format(language=language)
    config = types.GenerateContentConfig(
        system_instruction=sys_instructions,
        temperature=0.8,
        tools=[get_weather, get_mandi_price]
    )

    contents = [types.Content(role="user", parts=[types.Part(text=query)])]
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=config
    )
    
    max_tool_calls = 3
    calls = 0

    while response.function_calls and calls < max_tool_calls:
        print(f"[{calls}] Model requested function call(s): {[c.name for c in response.function_calls]}")
        contents.append(response.candidates[0].content)

        parts = []
        for call in response.function_calls:
            name = call.name
            args = call.args
            
            func_result = {"error": "Not found"}
            if name in tool_functions:
                func_result = tool_functions[name](**args)
                print(f"     => Result: {func_result}")
                
            parts.append(
                types.Part.from_function_response(
                    name=name,
                    response=func_result
                )
            )

        contents.append(types.Content(role="user", parts=parts))

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config
        )
        calls += 1

    print(f"\nFinal Response:\n{response.text}")

if __name__ == "__main__":
    print("-" * 50)
    print("TEST 1: Weather Check")
    test_agent_query("Karnal mein aaj mausam kaisa hai?")
    
    print("-" * 50)
    print("TEST 2: Mandi Price Check")
    test_agent_query("Chawal ka kya daam chal raha hai Bhopal mein?")
