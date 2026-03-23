from react_agent import TravelReActAgent 
import argparse 
import os 
from datasets import load_dataset
from datetime import datetime 
from concurrent.futures import ThreadPoolExecutor, as_completed 
import json 
from tqdm import tqdm 
import threading 


if __name__ == "__main__": 
    parser = argparse.ArgumentParser() 
    parser.add_argument("--model", type=str, default="Qwen/Qwen3-30B-A3B-Thinking-2507") 
    parser.add_argument("--split", type=str, default="validation")
    parser.add_argument("--use_custom_query", action="store_true")
    parser.add_argument("--input_file", type=str, default="")
    parser.add_argument("--save_suffix", type=str, default="")
    parser.add_argument("--max_workers", type=int, default=20)
    
    # server config 
    parser.add_argument("--use_custom_server", action="store_true")
    parser.add_argument("--server_url", type=str, default="http://localhost:8001/v1")
    parser.add_argument("--server_api_key", type=str, default="EMPTY")
    
    # generation config
    parser.add_argument("--temperature", type=float, default=0.6)
    parser.add_argument("--top_p", type=float, default=0.95)
    parser.add_argument("--max_turns", type=int, default=60)
    parser.add_argument("--max_context", type=int, default=64*1024)

    args = parser.parse_args() 

    # Load custom server configs for commercial LLMs
    if args.use_custom_server: 
        configs = json.load(open("config.json", "r")) 
        assert args.model in configs, f"Model {args.model} not found in config.json" 
        args.server_url = configs[args.model]["url"]
        args.server_api_key = configs[args.model]["api_key"]
        print(f"Loaded server config: {args.server_url} for {args.model}")
    server_cfg = {
        "url": args.server_url,
        "api_key": args.server_api_key,
    }

    # Load dataset 
    if args.use_custom_query:
        data = [json.loads(line) for line in open(args.input_file, "r")]
        print(f"Loaded {len(data)} custom queries from {args.input_file}")
    else:
        data = load_dataset('osunlp/TravelPlanner', args.split, download_mode="force_redownload")[args.split] 
        print(f"Loaded {len(data)} samples from TravelPlanner[{args.split}]")
        
    # Create output directory  
    basemodel = args.model.split("/")[-1] 
    save_suffix = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}" if not args.save_suffix else args.save_suffix
    output_dir = f"output/{basemodel}{ '_' + args.split if args.split else ''}_{save_suffix}" 
    os.makedirs(output_dir, exist_ok=True)  
    print(f"Created output directory: {output_dir}") 
    
    # Initialize agent  
    generation_cfg = {
        "temperature": args.temperature,
        "top_p": args.top_p,
    }

    agent = TravelReActAgent(
        model=args.model, 
        server_cfg=server_cfg,
        generation_cfg=generation_cfg, 
        max_turns=args.max_turns, 
        max_context=args.max_context
    )

    processed_queries = []
    if os.path.exists(f"{output_dir}/predictions.jsonl"):
        with open(f"{output_dir}/predictions.jsonl", "r") as f:
            for line in f:
                prediction = json.loads(line)
                if "error" not in prediction:
                    print(f"Skip processed query: {prediction['query']}")
                    processed_queries.append(prediction["query"]) 
    
    tasks_to_run = []
    for sample in data:
        if sample["query"] not in processed_queries:
            tasks_to_run.append({"item": sample.copy(), "query": sample["query"]})
    if not tasks_to_run:
        print("No queries to process")
        exit(0) 

    print(f"Found {len(tasks_to_run)} queries to process \n") 
    
    write_lock = threading.Lock() 
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_task = {executor.submit(agent.run, task["query"]): task for task in tasks_to_run}
        for future in tqdm(as_completed(future_to_task), total=len(future_to_task), desc="Processing queries"):
            task_info = future_to_task[future]["item"]
            origin_query = task_info["query"]
            try:
                result = future.result()
                result["item"] = task_info
                with write_lock:
                    with open(f"{output_dir}/predictions.jsonl", "a", encoding="utf-8") as f:
                        f.write(json.dumps(result, ensure_ascii=False) + "\n")
            except Exception as e:
                print(f"Task for query {origin_query} failed: {e}")
                error_result = {
                    "query": origin_query,
                    "error": str(e),
                    "messages": [],
                    "plan": None,
                    "format_plan": None,
                    "item": task_info,
                }
                
                print("=" * 20)
                print(error_result)
                print("=" * 20)
                with write_lock:
                    with open(f"{output_dir}/predictions.jsonl", "a", encoding="utf-8") as f:
                        f.write(json.dumps(result, ensure_ascii=False) + "\n") 

    print(f"\nAll tasks completed!")
