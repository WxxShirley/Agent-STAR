import json 
from datasets import load_dataset
import argparse  
import os 
from concurrent.futures import ThreadPoolExecutor, as_completed 
from utils import format_planning, format_planning_for_official_test
from tqdm import tqdm  


if __name__ == "__main__": 
    parser = argparse.ArgumentParser() 
    parser.add_argument("--path", type=str, required=True) 
    parser.add_argument("--split", type=str, default="validation")
    parser.add_argument("--use_custom_query", action="store_true")
    parser.add_argument("--format_model", type=str, default="deepseek-chat")
 
    args = parser.parse_args()  

    # Load dataset 
    if args.use_custom_query:
        data = [json.loads(line) for line in open(args.path, "r")]
        print(f"Loaded {len(data)} custom queries from {args.path}")
    else:
        data = load_dataset('osunlp/TravelPlanner', args.split, download_mode="force_redownload")[args.split] 
        print(f"Loaded {len(data)} samples from TravelPlanner[{args.split}]")
    
    # Load input file 
    assert os.path.exists(args.path), f"Input file {args.path} does not exist" 
    items = [json.loads(line) for line in open(args.path, "r")] 
    
    formatted_items = []
    with ThreadPoolExecutor(max_workers=50) as executor:
        if args.split == "test":
            future_to_task = {executor.submit(format_planning_for_official_test, item["plan"], item["query"], args.format_model): item for item in items}
        else:
            future_to_task = {executor.submit(format_planning, item["plan"], item["query"], args.format_model): item for item in items}
        for future in tqdm(as_completed(future_to_task), total=len(future_to_task), desc="Formatting plans"):
            item = future_to_task[future]
            
            try:
                item["raw_plan"] = item["plan"]
                item["plan"] = future.result()
            
            except Exception as e: 
                print(f"Failed to format plan for item {item['query']}: {e}")
                item["raw_plan"] = item["plan"]
                item["plan"] = [{}]
                item["format_plan_error"] = "Failed to format plan"
            
            formatted_items.append(item)
    
    output_file = args.path.replace(".jsonl", f"_{args.format_model}_formatted.jsonl") 
    
    query_to_item = {item["query"]: item for item in formatted_items}
    with open(output_file, "w", encoding="utf-8") as f: 
        for idx, sample in enumerate(data):
            cur_query = sample["query"] 

            if args.split == "test":
                write_content = {"idx": idx, "query": cur_query, "plan": []}
                if cur_query in query_to_item:
                    write_content["plan"] = query_to_item[cur_query]["plan"]
                    # f.write(json.dumps(query_to_item[cur_query], ensure_ascii=False) + "\n")
                else:
                    print(f"Warning: No formatted item found for query: {cur_query}")
                f.write(json.dumps(write_content, ensure_ascii=False) + "\n")
            else:
                if cur_query in query_to_item:
                    f.write(json.dumps(query_to_item[cur_query], ensure_ascii=False) + "\n")
                else:
                    print(f"Warning: No formatted item found for query: {cur_query}")
           
    print(f"Saved {len(formatted_items)} formatted items to {output_file}") 
