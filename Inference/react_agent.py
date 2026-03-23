from tools import *
from prompt import TRAVEL_SYSTEM_PROMPT
from openai import OpenAI  
import json 
from transformers import AutoTokenizer
from utils import format_planning
import time 


TOOL_MAP = {
    "SearchFlight": SearchFlight(),
    "SearchAccommodation": SearchAccommodation(),
    "SearchRestaurant": SearchRestaurant(),
    "SearchAttraction": SearchAttraction(),
    "SearchCity": SearchCity(),
    "GoogleDistanceMatrix": GoogleDistanceMatrix(),
}


def extract_answer(response: str) -> str: 
    if "<answer>" in response and "</answer>" in response: 
        lpos = response.find("<answer>")
        rpos = response.rfind("</answer>")
        return response[lpos+len("<answer>"):rpos].strip()
    return ""


class TravelReActAgent: 
    def __init__(self, 
                 system_prompt: str = TRAVEL_SYSTEM_PROMPT, 
                 generation_cfg: dict = {}, 
                 server_cfg: dict = {},
                 max_turns: int = 50, 
                 max_context: int = 64 * 1024,
                 model: str = "Qwen/Qwen3-4B-Instruct-2507"):
        self.system_prompt = system_prompt 
        self.tools = TOOL_MAP 
        
        self.server_cfg = server_cfg
        self.generation_cfg = generation_cfg
        self.max_turns = max_turns
        self.max_context = max_context
        self.model = model

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model)
        except Exception as e:
            self.tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-4B-Instruct-2507")
    
    def call_server(self, messages: list[dict], max_retries: int = 10) -> str: 
        for attempt in range(max_retries): 
            client = OpenAI(
                # TODO: [important⚠️] Please change the base_url to the actual server url
                base_url=self.server_cfg.get("url", f"http://localhost:8001/v1"), 
                api_key=self.server_cfg.get("api_key", "EMPTY"),
            )
    
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.generation_cfg.get("temperature", 0.6),
                    top_p=self.generation_cfg.get("top_p", 0.95),
                    max_tokens=8192,
                    reasoning_effort="high",
                    # TODO: for Qwen3.5-397B-A17B / DeepSeek-V3.2-Exp-671B-Thinking 
                    # Must uncomment the following line
                    # extra_body={"enable_thinking": True}, 
                )
                content = response.choices[0].message.content
                if content: 
                    return content
            except Exception as e:
                time.sleep(0.1)
                if attempt == max_retries - 1:
                    print(e)
                    print(f"[Server] Failed to call server after {max_retries} attempts") 
        
        return "Server error with empty response"
    
    def count_tokens(self, messages: list[dict]) -> int: 
        token_length = 0 
        
        for msg in messages: 
            token_length += len(self.tokenizer.encode(msg["content"])) 
        return token_length

    def run(self, query: str, format_result: bool = False): 
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": query},
        ]

        num_llms_available = self.max_turns 
        num_round = 0 
        termination, prediction, format_prediction = None, None, None

        while num_llms_available:
            num_round += 1 
            num_llms_available -= 1 

            llm_response = self.call_server(messages) 
            messages.append({"role": "assistant", "content": llm_response}) 
            print(f"[Round {num_round}] {llm_response}")

            if ("<tool_call>" in llm_response and "</tool_call>" in llm_response):
                try:
                    tool_call = llm_response.split("<tool_call>")[1].split("</tool_call>")[0].strip() 
                    tool_call = json.loads(tool_call)
                    tool_name = tool_call["name"]
                    tool_params = tool_call["arguments"]
                    if tool_name in self.tools:
                        tool_response = self.tools[tool_name].call(tool_params)
                        tool_response = f"<tool_response>\n{tool_response}</tool_response>"
                        print(f"[Round {num_round}] Tool call {tool_name} invocation success with response length {len(tool_response)}")
                    else:
                        tool_response = f"<tool_response>\nTool {tool_name} not found, please rethink your tool call and try again.</tool_response>"
                        print(f"[Round {num_round}] Invalid tool name: {tool_name}")
                    messages.append({"role": "user", "content": tool_response})
                except Exception as e:
                    tool_response = f"<tool_response>\nError calling tool: {e}</tool_response>"
                    print(f"[Round {num_round}] Error calling tool: {e}")
                    messages.append({"role": "user", "content": tool_response})
            
            elif "<answer>" in llm_response and "</answer>" in llm_response: 
                termination = "answer"
                prediction = extract_answer(llm_response) 
                break 
            # TODO: GPT-OSS-120B has a bug, the answer is not wrapped in <answer> tags, so we need to add it manually
            elif "<answer>" in llm_response: 
                termination = "answer" 
                messages[-1]["content"] += "</answer>"
                prediction = llm_response.split("<answer>")[1].strip()
                break 

            cur_tokens = self.count_tokens(messages)  
            print(f"[Round {num_round}] Count tokens: {cur_tokens}")
            if cur_tokens > self.max_context: 
                print(f"Token limit exceeded: {cur_tokens} > {self.max_context}, terminating ...")
                messages[-1]["content"] = "The conversation has reached the token limit. Please summarize the conversation to generate a travel plan."  

                prediction = self.call_server(messages) 
                if "</answer>" not in prediction:
                    prediction += "</answer>"
                messages.append({"role": "assistant", "content": prediction}) 
                termination = "token limits"
                break 

        if not ("<answer>" in messages[-1]["content"] and "</answer>" in messages[-1]["content"]):
            if not prediction:
                prediction = "answer not found" 
            if not num_llms_available:
                termination = "turn limits"

        if format_result: 
            if prediction != "answer not found":
                try:
                   format_prediction = format_planning(prediction, query)
                except Exception as e:
                    format_prediction = None

        return {
            "query": query,
            "plan": prediction,
            "format_plan": format_prediction,
            "termination": termination,
            "messages": messages,
        }


if __name__ == "__main__":
    agent = TravelReActAgent(model="Qwen/Qwen3-30B-A3B-Thinking-2507")

    questions = [
        "Please create a travel plan departing from Minneapolis and heading to Seattle for 3 days, from March 29th to March 31st, 2022, with a budget of $1,800.",
    ]

    for question in questions:
        result = agent.run(question)
        print(result)
        print("-" * 40)
