from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI 
import os 
import json 
import argparse  
import random 
from tqdm import tqdm 
import threading 


SYNTHESIS_PROMPT = """Given a JSON, please help me generate a natural language query. In the JSON, 'org' denotes the departure city. When 'days' exceeds 3, 'visiting_city_number' specifies the number of cities to be covered in the destination state. Here are three examples.

-----EXAMPLE 1----
JSON:
{"org": "Gulfport", "dest": "Charlotte", "days": 3, "visiting_city_number": 1, "date": ["2022-03-05", "2022-03-06", "2022-03-07"], "people_number": 1, "constraint": {"room rule": null, "cuisine": null, "room type": null}, "budget": 1800}
QUERY: Please design a travel plan departing Gulfport and heading to Charlotte for 3 days, spanning March 5th to March 7th, 2022, with a budget of $1800.

-----EXAMPLE 2----
JSON:
{"org": "Omaha", "dest": "Colorado", "days": 5, "visiting_city_number": 2, "date": ["2022-03-14", "2022-03-15", "2022-03-16", "2022-03-17", "2022-03-18"], "people_number": 7, "constraint": {"room rule": "pets", "cuisine": null, "room type": null}, "budget": 35300}
QUERY: Could you provide a 5-day travel itinerary for a group of 7, starting in Omaha and exploring 2 cities in Colorado between March 14th and March 18th, 2022? Our budget is set at $35,300, and it's essential that our accommodations be pet-friendly since we're bringing our pets.

-----EXAMPLE 3----
JSON:
{"org": "Indianapolis", "dest": "Georgia", "days": 7, "visiting_city_number": 3, "date": ["2022-03-01", "2022-03-02", "2022-03-03", "2022-03-04", "2022-03-05", "2022-03-06", "2022-03-07"], "people_number": 2, "constraint": {"room rule": null, "cuisine": ["Bakery", "Indian"], "room type": "entire room", "transportation": "self driving"}, "budget": 6200}
QUERY: I'm looking for a week-long travel itinerary for 2 individuals. Our journey starts in Indianapolis, and we intend to explore 3 distinct cities in Georgia from March 1st to March 7th, 2022. Our budget is capped at $6,200. For our accommodations, we'd prefer an entire room. We plan to navigate our journey via self-driving. In terms of food, we're enthusiasts of bakery items, and we'd also appreciate indulging in genuine Indian cuisine.

-----EXAMPLES END----

JSON: {{{json}}}
Query:

"""


MODEL_CFG = {
    "deepseek-chat": {
        "endpoint": ["https://api.deepseek.com"],
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    },
    "openai/gpt-oss-120b": {
        "endpoint": ["http://localhost:8001/v1", "http://localhost:8002/v1"],
        "api_key": "EMPTY",
    },
}


def invoke_openai(query, model="deepseek-chat", max_retries=10):
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": query},
    ]

    cfg = MODEL_CFG[model]
    # print(cfg)
    client = OpenAI(
        base_url=random.choice(cfg["endpoint"]),
        api_key=cfg["api_key"],
    )

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7, 
                max_tokens=512, 
                top_p=0.95, 
            )
            content = response.choices[0].message.content 
            # print(f"Response: {response}")
            if content:
                return content 
           
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"Failed to generate query after {max_retries} attempts: {e}")
                return None
            print(e)
            import time 
            time.sleep(0.1)
    return None 


def generate_query(query_obj: dict):
    model = random.choice(["deepseek-chat", "openai/gpt-oss-120b"])

    query_content = SYNTHESIS_PROMPT.replace("{{{json}}}", json.dumps(query_obj, ensure_ascii=False))
    query = invoke_openai(query_content, model=model)
    if query:
        query_obj["query"] = query
        query_obj["generated_model"] = model
        return True, query_obj

    return False, None 


if __name__ == "__main__":
    parser = argparse.ArgumentParser() 
    parser.add_argument("--input_file", type=str, required=True)
    parser.add_argument("--output_file", type=str, required=True)
    args = parser.parse_args() 
    
    total_items = []
    for input_file in args.input_file.split(","): 
        items = [json.loads(line) for line in open(input_file, "r")] 
        total_items.extend(items) 
    print(f"Total items: {len(total_items)}") 
    
    random.shuffle(total_items) 
    
    failed_ids = []

    writing_lock = threading.Lock() 

    with ThreadPoolExecutor(max_workers=30) as executor:
        future_to_task = {executor.submit(generate_query, item): item for item in total_items}
        for future in tqdm(as_completed(future_to_task), total=len(future_to_task), desc="Generating queries"):
            item = future_to_task[future]
            success, query_obj = future.result()
            if success:
                print(f"{item['generated_model']}: {query_obj['query']}")
                with writing_lock:
                    with open(args.output_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(query_obj, ensure_ascii=False) + "\n")
            else:
                failed_ids.append(item["query"])
            print("-" * 40)
    
    if len(failed_ids) > 0: 
        failed_file = args.output_file.replace(".jsonl", "_failed.jsonl")
        with open(failed_file, "w", encoding="utf-8") as f:
            for query in failed_ids:
                f.write(json.dumps({"query": query}, ensure_ascii=False) + "\n")
        print(f"Saved {len(failed_ids)} failed items to {failed_file}")
