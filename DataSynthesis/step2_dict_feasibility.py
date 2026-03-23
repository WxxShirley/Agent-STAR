import sys 
import os
import re
import math
import pandas as pd
from collections import defaultdict
sys.path.append("../")
from Inference.tools import SearchFlight, SearchAccommodation, SearchRestaurant, GoogleDistanceMatrix  
import argparse 
import json
from tqdm import tqdm 
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


FLIGHT_TOOL = SearchFlight()
ACCOMMODATION_TOOL = SearchAccommodation()
RESTAURANT_TOOL = SearchRestaurant()
DISTANCE_TOOL = GoogleDistanceMatrix()
CITY_SET = open("../database/background/citySet_with_states.txt", "r").read().strip().split("\n") 
STATE2CITY, CITY2STATE = defaultdict(list), defaultdict(str)
for unit in CITY_SET:
    city, state = unit.split("\t")
    STATE2CITY[state].append(city) 
    CITY2STATE[city] = state
print(f"Loaded {len(STATE2CITY)} states and {len(CITY2STATE)} cities")


def check_dict_feasibility(query_obj: dict):
    multipliers = {
        3: {"flight": 2, "hotel": 3, "restaurant": 9},
        5: {"flight": 3, "hotel": 5, "restaurant": 15},
        7: {"flight": 4, "hotel": 7, "restaurant": 21}
    }

    # 0. Check city feasibility 
    source, destination = query_obj["org"], query_obj["dest"] 
    if query_obj["days"] in [5, 7]:
        destination_state = destination 
        destination_city = STATE2CITY[destination_state]
    else:
        destination_state = CITY2STATE[destination] 
        destination_city = [destination]

    # 1. Check transportation feasibility 
    flight_fees = 0
    no_flight_flg = query_obj.get("local_constraint", {}).get("transportation", "") == "no flight" 
    no_transporation_constraint = query_obj.get("local_constraint", {}).get("transportation", "") == None 
    only_flight_flg = query_obj.get("local_constraint", {}).get("transportation", "") == "no self-driving" 

    if no_flight_flg or no_transporation_constraint:
        flg = False 
        for possible_city in destination_city:
            result = DISTANCE_TOOL.run_for_evaluation(source, possible_city, "driving") 
            if result.get("cost") is not None:
                flg = True 
                flight_fees = result.get("cost")
                flight_fees = flight_fees * math.ceil(query_obj["people_number"] * 1.0 / 5)
                break 
        if not flg and no_flight_flg:
            return False, "No driving route found for the destination city" 
        
        if not flg and no_transporation_constraint:
            only_flight_flg = True 
    
    if only_flight_flg:
        flg = False  
        for possible_city in destination_city: 
            outbound_flight = FLIGHT_TOOL.data[(FLIGHT_TOOL.data["OriginCityName"] == source) & (FLIGHT_TOOL.data["DestCityName"] == possible_city) & (FLIGHT_TOOL.data["FlightDate"] == query_obj["date"][0])]
            return_flight = FLIGHT_TOOL.data[(FLIGHT_TOOL.data["OriginCityName"] == possible_city) & (FLIGHT_TOOL.data["DestCityName"] == source) & (FLIGHT_TOOL.data["FlightDate"] == query_obj["date"][-1])]
            
            # Strict checking: 
            if len(outbound_flight) > 2 and len(return_flight) > 2:
                flg = True 
                flight_fees = (outbound_flight["Price"].mean() + return_flight["Price"].mean()) / 2 * query_obj["people_number"]
                break 
        if not flg:
            return False, "No flight found for the destination city" 
    flight_budget = flight_fees * multipliers[query_obj["days"]]["flight"] 

    # 2. Check accommodation feasibility  
    all_hotel_data = []
    for possible_city in destination_city:
        current_hotel_data = ACCOMMODATION_TOOL.data[ACCOMMODATION_TOOL.data["city"] == possible_city]
        all_hotel_data.append(current_hotel_data)
    hotel_data = pd.concat(all_hotel_data, axis=0)
    hotel_data = hotel_data[hotel_data["maximum occupancy"] >= query_obj["people_number"]]
    
    if query_obj.get("local_constraint", {}).get("room type"):
        if query_obj["local_constraint"]["room type"] == "shared room":
            hotel_data = hotel_data[hotel_data["room type"] == "Shared room"]
        elif query_obj["local_constraint"]["room type"] == "private room":
            hotel_data = hotel_data[hotel_data["room type"] == "Private room"]
        elif query_obj["local_constraint"]["room type"] == "entire room":
            hotel_data = hotel_data[hotel_data["room type"] == "Entire home/apt"]
        elif query_obj["local_constraint"]["room type"] == "not shared room":
            hotel_data = hotel_data[(hotel_data["room type"] == "Private room") | (hotel_data["room type"] == "Entire home/apt")]
        else:
            raise ValueError(f"Invalid room type: {query_obj['local_constraint']['room type']}")
    if query_obj.get("local_constraint", {}).get("house rule"):
        if query_obj["local_constraint"]["house rule"] == "smoking":
            hotel_data = hotel_data[~hotel_data["house_rules"].str.contains("No smoking", case=False, na=False)]
        elif query_obj["local_constraint"]["house rule"] == "parties":
            hotel_data = hotel_data[~hotel_data["house_rules"].str.contains("No parties", case=False, na=False)]
        elif query_obj["local_constraint"]["house rule"] == "children under 10":
            hotel_data = hotel_data[~hotel_data["house_rules"].str.contains("No children under 10", case=False, na=False)]
        elif query_obj["local_constraint"]["house rule"] == "pets":
            hotel_data = hotel_data[~hotel_data["house_rules"].str.contains("No pets", case=False, na=False)]
        elif query_obj["local_constraint"]["house rule"] == "visitors":
            hotel_data = hotel_data[~hotel_data["house_rules"].str.contains("No visitors", case=False, na=False)]
        else:
            raise ValueError(f"Invalid house rule: {query_obj['local_constraint']['house rule']}")
    
    if len(hotel_data) < multipliers[query_obj["days"]]["hotel"]:
        return False, "Not enough hotel data available for the given constraints"  

    hotel_budget = hotel_data["price"].mean() * multipliers[query_obj["days"]]["hotel"] * math.ceil(query_obj["people_number"] * 1.0 / 2)

    # 3. Check restaurant feasibility  
    all_restaurant_data = []
    for possible_city in destination_city:
        current_restaurant_data = RESTAURANT_TOOL.data[RESTAURANT_TOOL.data["City"] == possible_city]
        all_restaurant_data.append(current_restaurant_data)
    restaurant_data = pd.concat(all_restaurant_data, axis=0)
    if query_obj.get("local_constraint", {}).get("cuisine"):
        target_cuisines = query_obj["local_constraint"]["cuisine"]
        cuisine_pattern = '|'.join([re.escape(c) for c in target_cuisines]) 
        restaurant_data = restaurant_data[restaurant_data["Cuisines"].str.contains(cuisine_pattern, case=False, na=False, regex=True)]
        if len(restaurant_data) < multipliers[query_obj["days"]]["restaurant"]:
            return False, "Not enough restaurant data available for the given constraints"  

    restaurant_budget = restaurant_data["Average Cost"].mean() * multipliers[query_obj["days"]]["restaurant"] * query_obj["people_number"] * 0.6

    # 4. Check total budget feasibility  
    total_budget = flight_budget + hotel_budget + restaurant_budget  
    if query_obj["budget"] < 0.7 * total_budget:
        print(f"The total budget is not feasible: {query_obj['budget']} < {total_budget:.2f} (80%)")
        return False, "The total budget is not feasible"  
    
    return True, "All constraints are feasible"


if __name__ == "__main__": 
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str, default="output/easy_4500.jsonl")
    parser.add_argument("--max_workers", type=int, default=20)
    args = parser.parse_args()
    
    assert os.path.exists(args.path), f"Input file {args.path} does not exist"  

    items = [json.loads(line) for line in open(args.path, "r")] 
    print(f"Loaded {len(items)} items to check")

    write_path = args.path.replace(".jsonl", "_feasible.jsonl")
    failed_path = args.path.replace(".jsonl", "_failed.jsonl")
    
    # 清空输出文件
    if os.path.exists(write_path):
        os.remove(write_path)
    if os.path.exists(failed_path):
        os.remove(failed_path)
    
    write_lock = threading.Lock()
    
    def process_item(item):
        """处理单个item并直接写入文件"""
        try:
            flag, msg = check_dict_feasibility(item)
            with write_lock:
                if flag:
                    with open(write_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
                else:
                    item["error"] = msg
                    with open(failed_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
            return item, flag, msg, None
        except Exception as e:
            with write_lock:
                item["error"] = str(e)
                with open(failed_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            return item, False, None, str(e)
    
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_item = {executor.submit(process_item, item): item for item in items}
        for future in tqdm(as_completed(future_to_item), total=len(future_to_item), desc="Checking feasibility"):
            try:
                item, flag, msg, error = future.result()
                if error:
                    print(f"Error checking feasibility for item {item.get('query', 'unknown')}: {error}")
                elif not flag and msg:
                    print(f"Feasibility check failed for item {item.get('query', 'unknown')}: {msg}")
            except Exception as e:
                print(f"Unexpected error: {e}")

    print(f"\nAll tasks completed!")
