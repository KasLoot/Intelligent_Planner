import json

from tools import call_tool


MODEL = "gpt-5.4-nano"
MAX_TOOL_ROUNDS = 8


def load_json(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def load_text(path):
    with open(path, encoding="utf-8") as file:
        return file.read()


def write_output(path, content):
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)
        if content and not content.endswith("\n"):
            file.write("\n")


def run_agent(user_message):
    from openai import OpenAI

    client = OpenAI()
    available_tools = load_json("configs/tools.json")
    instructions = load_text("configs/instructions.md")

    input_list = [{"role": "user", "content": user_message}]

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.responses.create(
            model=MODEL,
            instructions=instructions,
            tools=available_tools,
            input=input_list,
        )
        input_list += response.output

        function_calls = [
            item for item in response.output if item.type == "function_call"
        ]
        if not function_calls:
            return response

        for item in function_calls:
            arguments = json.loads(item.arguments or "{}")
            result = call_tool(item.name, arguments)
            input_list.append(
                {
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": json.dumps(result),
                }
            )

    raise RuntimeError("The agent reached the maximum number of tool-call rounds.")


if __name__ == "__main__":
    response = run_agent("Plan a trip for me to Paris this weekend.")
    write_output("output.json", response.output_text)
    write_output("full_api_response.json", response.model_dump_json(indent=2))
    print("Full API Response:")
    print(response.model_dump_json(indent=2))
    
    print("\n\n\n\nOutput Text:")
    print("-" * 50)
    print(response.output_text)
    print("\nSaved model output to output.md")
