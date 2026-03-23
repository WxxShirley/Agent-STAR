from eval_commonsense import check_commonsense 
from eval_hardconstraint import check_hardconstraint 
import os 
import json 
import argparse 
from tqdm import tqdm 


global_hard_micro_score = 0 

def eval_one_sample(question, tested_data, verbose=False): 
    global global_hard_micro_score 
    if not tested_data or len(tested_data) == 0:
        return {
            "commonsense_macro_score": 0,
            "commonsense_micro_score": 0,
            "hard_macro_score": 0,
            "hard_micro_score": 0,
            "success_pass": 0,
        }

    commonsense_results = check_commonsense(question, tested_data) 
    
    hard_results = None
    try:
        # for TravelPlanner data
        question["local_constraint"] = eval(question["local_constraint"])
    except Exception as e:
        pass 

    if commonsense_results and commonsense_results["is_not_absent"][0] and commonsense_results["is_valid_information_in_sandbox"][0]:
        hard_results = check_hardconstraint(question, tested_data)
    
    if verbose: 
        for constraint, (is_valid, message) in commonsense_results.items(): 
            if is_valid is not None and not is_valid:
                print(f"Commonsense constraint '{constraint}' failed: {message}")
        
        if hard_results:
            for constraint, (is_valid, message) in hard_results.items(): 
                if is_valid is not None and not is_valid:
                    print(f"Hard constraint '{constraint}' failed: {message}")

    commonsense_all_pass, micro_pass = True, 0
    for constraint, (is_valid, message) in commonsense_results.items():  
        if is_valid is not None:
            if not is_valid: 
                commonsense_all_pass = False 
            else: # Pass the commonsense constraint
                micro_pass += 1 

    commonsense_macro_score, commonsense_micro_score = int(commonsense_all_pass), micro_pass * 1.0 / 8
    
    hard_macro_score, hard_micro_score = None, None
    if hard_results:
        # Check if all hard constraints are None (not applicable)
        all_none = all(is_valid is None for is_valid, _ in hard_results.values())
        
        if not all_none:
            hard_all_pass, micro_pass, micro_total = True, 0, 0
            for constraint, (is_valid, message) in hard_results.items():  
                if is_valid is not None and not is_valid:
                    hard_all_pass = False
                if is_valid is not None:
                    micro_pass += 1 if is_valid else 0
                    micro_total += 1
                    global_hard_micro_score += 1 if is_valid else 0
            hard_macro_score, hard_micro_score = int(hard_all_pass), micro_pass * 1.0 / micro_total if micro_total > 0 else 0

    # Final pass rate: commonsense must pass, and if hard constraints exist and are applicable, they must also pass
    if hard_macro_score is None:
        # All hard constraints are not applicable, only consider commonsense
        success_pass = int(commonsense_all_pass)
    else:
        success_pass = int(commonsense_all_pass and hard_macro_score)

    return {
        "commonsense_macro_score": commonsense_macro_score,
        "commonsense_micro_score": commonsense_micro_score,
        "hard_macro_score": hard_macro_score,
        "hard_micro_score": hard_micro_score,
        "success_pass": success_pass,
        "details": {
            "commonsense_results": commonsense_results,
            "hard_results": hard_results
        }
    }
    

def eval_one_file(file_path, verbose=False, save_score=False): 
    global global_hard_micro_score 
    assert os.path.exists(file_path), f"File {file_path} does not exist" 
    items = [json.loads(line) for line in open(file_path, "r")]  
    # base hard constraint numbers: 420 for validation set, 105 for train set
    base_num = 420 if "validation" in file_path else 105

    metrics = {
        "commonsense_macro_score": [],
        "commonsense_micro_score": [],
        "hard_macro_score": [],
        "hard_micro_score": [],
        "success_pass": [],
    }
    
    scored_items = []
    for item in tqdm(items, desc="Evaluating samples"):
        result = eval_one_sample(item["item"], item["plan"], verbose=verbose) 
        
        for metric in metrics.keys():
            metrics[metric].append(result[metric]) 
        
        item["success"] = result["success_pass"]
        item["commonsense_macro_score"] = result["commonsense_macro_score"]
        item["commonsense_micro_score"] = result["commonsense_micro_score"]
        item["hard_macro_score"] = result["hard_macro_score"]
        item["hard_micro_score"] = result["hard_micro_score"]
        item["scored_details"] = result.get("details", {})
        scored_items.append(item)
    
    for metric in metrics.keys():
        valid_values = [v for v in metrics[metric] if v is not None]
        if valid_values:
            metrics[metric] = str(round(sum(valid_values) / len(items) * 100, 2)) + "%"
        else:
            metrics[metric] = None  
    
    print(f"Global hard micro score: {global_hard_micro_score / base_num * 100:.2f}%")
    metrics["hard_micro_score_case_avg"] = metrics["hard_micro_score"]
    metrics["hard_micro_score"] = str(round(global_hard_micro_score / base_num * 100, 2)) + "%"
    print(f"Metrics: {metrics}")

    if save_score:
        with open(file_path.replace(".jsonl", "_scored.jsonl"), "w", encoding="utf-8") as f:
            for item in scored_items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"Saved {len(scored_items)} scored items to {file_path.replace('.jsonl', '_scored.jsonl')}")


if __name__ == "__main__": 
    # question = {
    #     "query": "Please plan a trip for me starting from Sarasota to Chicago for 3 days, from March 22nd to March 24th, 2022. The budget for this trip is set at $1,900.", 
    #     "days": 3, 
    #     "org": "Sarasota", 
    #     "dest": "Chicago", 
    #     "visiting_city_number": 1, 
    #     "budget": 1900,
    #     "local_constraint": {
    #         "house rule": "private room", 
    #         "cuisine": ["Cafe"],
    #         "room type": None, 
    #         "transportation": None
    #     },
    #     "people_number": 1
    # }

    # tested_data = [
    #     {'day': 1, 'current_city': 'from Sarasota to Chicago', 'transportation': 'Flight Number: F3984576, from Sarasota to Chicago, Departure Time: 05:14, Arrival Time: 06:50', 'breakfast': '-', 'attraction': 'Millennium Park, Chicago;', 'lunch': '-', 'dinner': 'The Black Pearl, Chicago', 'accommodation': 'Amazing new private bedroom 5 min to subway, Chicago'}, 
    #     {'day': 2, 'current_city': 'Chicago', 'transportation': '-', 'breakfast': '-', 'attraction': 'Willis Tower, Chicago;Grant Park, Chicago;Buckingham Fountain, Chicago;Museum of Science and Industry, Chicago;', 'lunch': "Pantry d'or, Chicago", 'dinner': 'FIO Cookhouse and Bar, Chicago', 'accommodation': 'Amazing new private bedroom 5 min to subway, Chicago'}, 
    #     {'day': 3, 'current_city': 'from Chicago to Sarasota', 'transportation': 'Flight Number: F3600004, from Chicago to Sarasota, Departure Time: 10:14, Arrival Time: 14:01', 'breakfast': 'Starbucks, Chicago;Gyan Vaishnav, Chicago', 'attraction': 'Riverwalk, Chicago;', 'lunch': '-', 'dinner': '-', 'accommodation': '-'}
    # ]

    # print(eval_one_sample(question, tested_data))
    
    parser = argparse.ArgumentParser() 
    parser.add_argument("--path", type=str, required=True) 
    parser.add_argument("--verbose", action="store_true") 
    parser.add_argument("--save_score", action="store_true")
    args = parser.parse_args() 

    eval_one_file(args.path, verbose=args.verbose, save_score=args.save_score) 
