import json 
import os
import time
import argparse
import random  
import re
from datetime import datetime, timedelta
import sys 
import os
sys.path.append("../")
from Inference.tools import SearchFlight, SearchAccommodation, SearchRestaurant, GoogleDistanceMatrix  
import pandas as pd  
import numpy as np 
from collections import defaultdict


FLIGHT_TOOL = SearchFlight()
ACCOMMODATION_TOOL = SearchAccommodation()
RESTAURANT_TOOL = SearchRestaurant()
DISTANCE_TOOL = GoogleDistanceMatrix()
VISITING_CITY_MAP = {3: 1, 5: 2, 7: 3}
CITY_SET = open("../database/background/citySet_with_states.txt", "r").read().strip().split("\n") 
STATE2CITY, CITY2STATE = defaultdict(list), defaultdict(str)
for unit in CITY_SET:
    city, state = unit.split("\t")
    STATE2CITY[state].append(city) 
    CITY2STATE[city] = state
print(f"Loaded {len(STATE2CITY)} states and {len(CITY2STATE)} cities")


FLIGHT_DATA = FLIGHT_TOOL.data.copy()
FLIGHT_DATA["FlightDate"] = pd.to_datetime(FLIGHT_DATA["FlightDate"])

FLIGHT_PAIR_DATES = {} # {(org, dest): [dates]}
FLIGHT_COUNT_BY_DATE = {}  # {(org, dest, date): count}
for (origin, destination), group in FLIGHT_DATA.groupby(["OriginCityName", "DestCityName"]):
    if origin not in CITY2STATE or destination not in CITY2STATE:
        continue
    unique_dates = sorted(group["FlightDate"].dt.normalize().unique())
    FLIGHT_PAIR_DATES[(origin, destination)] = [pd.Timestamp(date) for date in unique_dates]
    
    # Count flights for each date
    for date, date_group in group.groupby(group["FlightDate"].dt.normalize()):
        FLIGHT_COUNT_BY_DATE[(origin, destination, pd.Timestamp(date))] = len(date_group)

dates_list = [len(v) for v in FLIGHT_PAIR_DATES.values()]
flight_counts_list = list(FLIGHT_COUNT_BY_DATE.values())
print(f"Loaded {len(FLIGHT_PAIR_DATES)} (source, destination) flight pairs with avg. {sum(dates_list) / len(dates_list):.2f} dates and avg. {sum(flight_counts_list) / len(flight_counts_list):.2f} flights per date")


def property_budget_calculation(data, mode, property_name=None):
    # print(f"Calculating {property_name} (#{len(data)}) for {mode} mode")
    if mode == "lowest":
        return min(data) 
    elif mode == "highest":
        return max(data) 
    elif mode == "average":
        valid_data = [x for x in data if str(x) != "nan"]
        return sum(valid_data) / len(valid_data) 


def budget_calculation(org: str, dest: str, days: int, date: list, people_number=None, local_constraint=None):
    if days == 3:
        grain = "city"
    elif days in [5, 7]: 
        grain = "state" 
    print(f"Calculating budget for {org} to {dest} for {days} days ({date}) with {people_number} people and {local_constraint}")
    
    assert grain in ["city", "state"], "Granularity must be either city or state" 

    multipliers = {
        3: {"flight": 2, "hotel": 3, "restaurant": 9},
        5: {"flight": 3, "hotel": 5, "restaurant": 15},
        7: {"flight": 4, "hotel": 7, "restaurant": 21}
    }

    if grain == "city":
        hotel_data = ACCOMMODATION_TOOL.data[ACCOMMODATION_TOOL.data["city"] == dest]
        restaurant_data = RESTAURANT_TOOL.data[RESTAURANT_TOOL.data["City"] == dest]
        flight_data = FLIGHT_TOOL.data[(FLIGHT_TOOL.data["OriginCityName"] == org) & (FLIGHT_TOOL.data["DestCityName"] == dest)] 
        print(f"Found {len(hotel_data)} hotels, {len(restaurant_data)} restaurants, and {len(flight_data)} flights")

    elif grain == "state":
        all_hotel_data = []
        all_restaurant_data = [] 
        all_flight_data = []

        for city in STATE2CITY[dest]: 
            current_hotel_data = ACCOMMODATION_TOOL.data[ACCOMMODATION_TOOL.data["city"] == city]
            current_restaurant_data = RESTAURANT_TOOL.data[RESTAURANT_TOOL.data["City"] == city]
            current_flight_data = FLIGHT_TOOL.data[(FLIGHT_TOOL.data["OriginCityName"] == org) & (FLIGHT_TOOL.data["DestCityName"] == city)]
            
            # print(f"For city {city} in {dest}, found {len(current_hotel_data)} hotels, {len(current_restaurant_data)} restaurants, and {len(current_flight_data)} flights")
            all_hotel_data.append(current_hotel_data)
            all_restaurant_data.append(current_restaurant_data)
            all_flight_data.append(current_flight_data)
        
        hotel_data = pd.concat(all_hotel_data, axis=0)
        restaurant_data = pd.concat(all_restaurant_data, axis=0)
        flight_data = pd.concat(all_flight_data, axis=0)
        # flight_data should be in the range of supported dates
        flight_data = flight_data[flight_data["FlightDate"].isin(date)]
        print(f"Total {len(hotel_data)} hotels, {len(restaurant_data)} restaurants, and {len(flight_data)} flights")
    
    if people_number:
        hotel_data = hotel_data[hotel_data["maximum occupancy"] >= people_number] 
        print(f"Filtered hotels to {len(hotel_data)} hotels based on maximum occupancy")
    
    if local_constraint: 
        if local_constraint.get("transportation", "") == "no self-driving":
            if grain == "city":
                if len(flight_data[flight_data["FlightDate"] == date[0]]) < 2:
                    raise ValueError("No flight data available for the given constraints")
            elif grain == "state": 
                if len(flight_data[flight_data["FlightDate"] == date[0]]) < 10:
                    raise ValueError("No flight data available for the given constraints") 

        if local_constraint["room type"]:
            if local_constraint['room type'] == 'shared room':
                hotel_data = hotel_data[hotel_data['room type'] == 'Shared room']
            elif local_constraint['room type'] == 'not shared room':
                hotel_data = hotel_data[(hotel_data['room type'] == 'Private room') | (hotel_data['room type'] == 'Entire home/apt')]
            elif local_constraint['room type'] == 'private room':
                hotel_data = hotel_data[hotel_data['room type'] == 'Private room']
            elif local_constraint['room type'] == 'entire room':
                hotel_data = hotel_data[hotel_data['room type'] == 'Entire home/apt']
            print(f"Filtered hotels to {len(hotel_data)} hotels based on room type")
        
            if len(hotel_data) < multipliers[days]["hotel"]:
                raise ValueError("Not enough hotel data available for the given constraints")
        
        if local_constraint["house rule"]:
            if local_constraint["house rule"] == 'parties':
                hotel_data = hotel_data[~hotel_data['house_rules'].str.contains('No parties', case=False, na=False)]
            elif local_constraint["house rule"] == 'smoking':
                hotel_data = hotel_data[~hotel_data['house_rules'].str.contains('No smoking', case=False, na=False)]
            elif local_constraint["house rule"] == 'children under 10':
                hotel_data = hotel_data[~hotel_data['house_rules'].str.contains('No children under 10', case=False, na=False)]
            elif local_constraint["house rule"] == 'pets':
                hotel_data = hotel_data[~hotel_data['house_rules'].str.contains('No pets', case=False, na=False)]
            elif local_constraint["house rule"] == 'visitors':
                hotel_data = hotel_data[~hotel_data['house_rules'].str.contains('No visitors', case=False, na=False)]
            print(f"Filtered hotels to {len(hotel_data)} hotels based on house rule")
        
            if len(hotel_data) < multipliers[days]["hotel"]:
                raise ValueError("Not enough hotel data available for the given constraints")
        
        if local_constraint.get("cuisine"):
            # Use regex pattern to match any of the cuisines (cuisines are separated by comma and space)
            cuisine_pattern = '|'.join([re.escape(c) for c in local_constraint['cuisine']])
            restaurant_data = restaurant_data[restaurant_data['Cuisines'].str.contains(cuisine_pattern, case=False, na=False, regex=True)]
            print(f"Filtered restaurants to {len(restaurant_data)} restaurants based on cuisine")
            if len(restaurant_data) < multipliers[days]["restaurant"]:
                raise ValueError("No restaurant data available for the given constraints.")
    
    # Estimate the total budgets based on transporation, meals, and accommodation
    budgets = {}
    for mode in ["lowest", "highest", "average"]:
        if local_constraint and local_constraint.get("transportation", "") == "no flight":
            # For state-level trips, use a representative city for distance calculation
            dest_city_for_distance = dest if grain == "city" else STATE2CITY[dest][0]
            distance_info = DISTANCE_TOOL.run_for_evaluation(org, dest_city_for_distance, 'driving')
            cost = distance_info.get("cost")
            if cost is None:
                raise ValueError(f"Unable to calculate driving cost from {org} to {dest_city_for_distance}")
            
            flight_budget = cost * multipliers[days]["flight"] 
        else:
            flight_budget = property_budget_calculation(flight_data["Price"].tolist(), mode, "flight") * multipliers[days]["flight"] 

        hotel_budget = property_budget_calculation(hotel_data["price"].tolist(), mode, "hotel") * multipliers[days]["hotel"] 
        restaurant_budget = property_budget_calculation(restaurant_data["Average Cost"].tolist(), mode, "restaurant") * multipliers[days]["restaurant"] 
        budgets[mode] = flight_budget + hotel_budget + restaurant_budget 
    
    return budgets 


def round_to_hundreds(num):
    return round(num / 100) * 100


def select_consecutive_dates(num_days, start_date=datetime(2022, 1, 1), end_date=datetime(2022, 6, 30)):
    delta = end_date - start_date  
    all_dates = [start_date + timedelta(days=i) for i in range(delta.days)] 

    latest_start = len(all_dates) - num_days 

    start_index = random.randint(0, latest_start) 

    consecutive_dates = all_dates[start_index:start_index+num_days]
    return consecutive_dates 


def sample_trip_from_flights(days: int, verbose=False):
    assert days in [3, 5, 7], "Supported trip lengths are 3, 5, or 7 days"

    candidate_pairs = list(FLIGHT_PAIR_DATES.keys())
    random.shuffle(candidate_pairs)

    for org, dest_city in candidate_pairs:
        # Condition 0 - check both outbound and return flights are available
        if (dest_city, org) not in FLIGHT_PAIR_DATES:
            continue

        org_state = CITY2STATE.get(org)
        dest_state = CITY2STATE.get(dest_city)
        
        # Condition 1 - ensure source and destination are in different states
        if not org_state or not dest_state or org_state == dest_state or len(STATE2CITY.get(dest_state, [])) < 3:
            continue

        outbound_dates = FLIGHT_PAIR_DATES[(org, dest_city)]
        return_date_list = FLIGHT_PAIR_DATES[(dest_city, org)]
        return_date_set = set(return_date_list)

        # Find all possible start dates with their flight counts
        possible_start_dates = []
        weights = []
        
        for start_date in outbound_dates:
            end_date = start_date + timedelta(days=days - 1)
            if end_date in return_date_set:
                # Get flight counts for outbound and return
                outbound_count = FLIGHT_COUNT_BY_DATE.get((org, dest_city, start_date), 0)
                return_count = FLIGHT_COUNT_BY_DATE.get((dest_city, org, end_date), 0)

                # Add 1 to avoid zero weight if count is 0
                weight = (outbound_count + 1) * (return_count + 1)
                
                possible_start_dates.append(start_date)
                weights.append(weight)

        # Condition 2 - ensure at least one possible start date is found
        if not possible_start_dates:
            continue

        # Weighted random selection based on flight counts
        start_date = random.choices(possible_start_dates, weights=weights, k=1)[0]
        date_list = [
            (start_date + timedelta(days=offset)).strftime("%Y-%m-%d")
            for offset in range(days)
        ]

        if days == 3:
            final_dest = dest_city
        else:
            final_dest = dest_state
        
        outbound_count = FLIGHT_COUNT_BY_DATE.get((org, dest_city, start_date), 0)
        return_count = FLIGHT_COUNT_BY_DATE.get((dest_city, org, start_date + timedelta(days=days-1)), 0)
        if outbound_count < 3 or return_count < 3:
            continue
       
        if verbose:
            print(f"Sampled trip from {org} to {final_dest} for {days} days with dates {date_list} (outbound: {outbound_count} flights, return: {return_count} flights)")
        return org, final_dest, date_list

    raise ValueError("Unable to sample a trip that satisfies flight availability")


def sample_trip_for_driving(days: int, max_distance_miles=600, verbose=False):
    assert days in [3, 5, 7], "Supported trip lengths are 3, 5, or 7 days"

    def _clean_distance(distance_str: str) -> float:
        if not distance_str:
            return float("inf")
        try:
            return float(distance_str.replace("km", "").replace(",", "").strip())
        except (ValueError, AttributeError):
            return float("inf")

    def _valid_driving_info(origin_city: str, target_city: str):
        info = DISTANCE_TOOL.run_for_evaluation(origin_city, target_city, "driving")
        if not info or info.get("cost") is None:
            return None
        if _clean_distance(info.get("distance")) > max_distance_miles:
            return None
        return info

    max_attempts = 1000
    for _ in range(max_attempts):
        org_city_record = random.choice(CITY_SET)
        org_city, org_state = org_city_record.split("\t")

        if days == 3:
            dest_candidates = [city for city in CITY2STATE.keys() if CITY2STATE[city] != org_state and city != org_city]
            if not dest_candidates:
                continue
            dest_city = random.choice(dest_candidates)
            distance_info = _valid_driving_info(org_city, dest_city)
            if not distance_info:
                continue
            final_dest = dest_city
        else:
            valid_states = [state for state, cities in STATE2CITY.items() if len(cities) > 3 and state != org_state]
            if not valid_states:
                continue
            dest_state = random.choice(valid_states)
            dest_city = random.choice(STATE2CITY[dest_state])
            distance_info = _valid_driving_info(org_city, dest_city)
            if not distance_info:
                continue
            final_dest = dest_state

        dates = select_consecutive_dates(days, start_date=datetime(2022, 1, 1), end_date=datetime(2022, 6, 30))
        date_list = [date.strftime("%Y-%m-%d") for date in dates]

        if verbose:
            print(
                f"Sampled driving trip from {org_city} to {final_dest} for {days} days "
                f"with dates {date_list} (distance: {distance_info.get('distance', 'N/A')}, "
                f"duration: {distance_info.get('duration', 'N/A')})"
            )
        return org_city, final_dest, date_list

    raise ValueError(f"Unable to sample a driving trip for {days} days after {max_attempts} attempts")


def easy_level_element_selection(day_list): 
    days = random.choice(day_list)
    
    # For easy level, we mainly consider trips from flights
    probability = random.random()
    if probability < 0.1:
        source, destination, dates = sample_trip_for_driving(days)
    else:
        source, destination, dates = sample_trip_from_flights(days)
    
    budgets = budget_calculation(source, destination, days, dates)

    if days == 3:
        rounded_budget = round_to_hundreds((budgets["average"] + budgets["lowest"]) / 2) 
    elif days == 5:
        rounded_budget = round_to_hundreds(budgets["average"]) 
    elif days == 7: 
        rounded_budget = round_to_hundreds((budgets["average"] + budgets["highest"]) / 2) 

    return {
        "org": source,
        "dest": destination,
        "days": days,
        "date": dates,
        "visiting_city_number": VISITING_CITY_MAP[days],
        "people_number": 1,
        "local_constraint": {"house rule": None, "cuisine": None, "room type": None, "transportation": None},
        "budget": rounded_budget,
        "query": None, 
        "level": "easy"
    }
    

def medium_level_element_selection(day_list): 
    days = random.choice(day_list)

    probability = random.random()
    if probability < 0.1:
        source, destination, date = sample_trip_for_driving(days)
    else:   
        source, destination, date = sample_trip_from_flights(days)

    people_number = random.choice(random.choice([[2],[3,4,5,6,7,8]])) 

    local_constraint = {"house rule": None, "cuisine": None, "room type": None, "transportation": None}
    local_constraint_type = random.choice(["house rule", "cuisine", "room type"]) 

    if local_constraint_type == "room type": 
        if people_number <= 2:
            cur_room_type = random.choice(["shared room", "not shared room", "private room", "entire room"])
        else:
            cur_room_type = random.choice(["private room", "entire room"])
        local_constraint["room type"] = cur_room_type
    
    elif local_constraint_type == "house rule":
        cur_house_rule = random.choice(["smoking", "parties", "children under 10", "pets", "visitors"])
        local_constraint["house rule"] = cur_house_rule

    elif local_constraint_type == "cuisine":
        cur_cuisine = random.sample(["Chinese", "American", "Italian", "Mexican", "Indian", "Mediterranean", "French", "BBQ"], 2) 
        local_constraint["cuisine"] = cur_cuisine

    budgets = budget_calculation(source, destination, days, date, people_number, local_constraint)

    if days == 3:
        rounded_budget = round_to_hundreds((budgets["average"] + budgets["lowest"]) / 2 * people_number * 0.75) 
    elif days == 5:
        rounded_budget = round_to_hundreds(budgets["average"] * people_number * 0.75) 
    elif days == 7: 
        rounded_budget = round_to_hundreds((budgets["average"] + budgets["highest"]) / 2 * people_number * 0.75) 

    return {
        "org": source,
        "dest": destination,
        "days": days,
        "date": date,
        "visiting_city_number": VISITING_CITY_MAP[days],
        "people_number": people_number,
        "local_constraint": local_constraint,
        "budget": rounded_budget,
        "query": None, 
        "level": "medium"
    }


def hard_level_element_selection(day_list): 
    days = random.choice(day_list)
    people_number = random.choice(random.choice([[2],[3,4,5,6,7,8]])) 

    transportation_constraint = random.choice(["no self-driving", "no flight"])
    if transportation_constraint == "no flight":
        source, destination, date = sample_trip_for_driving(days, verbose=True)
    else:
        source, destination, date = sample_trip_from_flights(days, verbose=True)

    local_constraint = {"house rule": None, "cuisine": None, "room type": None, "transportation": transportation_constraint}

    constraints = np.random.choice(["house rule", "cuisine", "room type"], size=2, replace=False, p=[0.35, 0.3, 0.35]).tolist()

    for constraint in constraints: 
        if constraint == "room type":  
            if people_number <= 2:
                cur_room_type = random.choice(["shared room", "not shared room", "private room", "entire room"])
            else:
                cur_room_type = random.choice(["private room", "entire room"])
            local_constraint["room type"] = cur_room_type
        
        elif constraint == "house rule": 
            cur_house_rule = random.choice(["smoking", "parties", "children under 10", "pets", "visitors"])
            local_constraint["house rule"] = cur_house_rule
        
        elif constraint == "cuisine": 
            if random.random() < 0.6:
                cur_cuisine = random.sample(["Chinese", "American", "Italian", "Mexican", "Indian", "Mediterranean", "French", "BBQ", "Fast Food"], 2) 
            else:
                cur_cuisine = random.sample(["Chinese", "American", "Italian", "Mexican", "Indian", "Mediterranean", "French", "BBQ", "Fast Food"], 3) 
            local_constraint["cuisine"] = cur_cuisine

    budgets = budget_calculation(source, destination, days, date, people_number, local_constraint)

    if days == 3:
        rounded_budget = round_to_hundreds((budgets["average"] + budgets["lowest"]) / 2 * people_number * 0.5) 
    elif days == 5:
        rounded_budget = round_to_hundreds(budgets["average"] * people_number * 0.5) 
    elif days == 7: 
        rounded_budget = round_to_hundreds((budgets["average"] + budgets["highest"]) / 2 * people_number * 0.5) 

    return {
        "org": source,
        "dest": destination,
        "days": days,
        "date": date,
        "visiting_city_number": VISITING_CITY_MAP[days],
        "people_number": people_number,
        "local_constraint": local_constraint,
        "budget": rounded_budget,
        "query": None, 
        "level": "hard"
    }


if __name__ == "__main__": 
    parser = argparse.ArgumentParser() 
    parser.add_argument("--generate_dict", action="store_true")
    parser.add_argument("--easy_num", type=int, default=4500)
    parser.add_argument("--medium_num", type=int, default=3500)
    parser.add_argument("--hard_num", type=int, default=2000)
    parser.add_argument("--output_dir", type=str, default="output")

    args = parser.parse_args()  
    
    init_start_time = time.time() 
    if args.generate_dict:
        num_samples = [args.easy_num, args.medium_num, args.hard_num]
        function_list = [easy_level_element_selection, medium_level_element_selection, hard_level_element_selection] 

        for _ in range(3):
            target_samples = num_samples[_] 
            target_function = function_list[_] 
            cnt = 0 

            if not target_samples:
                continue
             
            st_time = time.time() 
            while True:
                try:
                    sample = target_function([3, 5, 7]) 

                    cur_mode = sample.get("level") 
                    output_file = os.path.join(args.output_dir, f"{cur_mode}_{target_samples}.jsonl")
                    with open(output_file, "a") as f:
                        f.write(json.dumps(sample, ensure_ascii=False) + "\n") 
                    cnt += 1  

                except Exception as e:
                    print(f"Error generating sample: {e}")
                    pass 
                
                if cnt >= target_samples:
                    break 

            print(f"Generated {cnt} samples for {cur_mode} level in {(time.time() - st_time)/60:.2f} minutes!")
    
    print(f"Total time taken: {(time.time() - init_start_time)/3600:.2f} hours!") 
