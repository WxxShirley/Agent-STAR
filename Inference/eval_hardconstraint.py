import re 
from tools import * 
from eval_commonsense import get_valid_name_city, extract_from_to, detect_transportation_type
import math 


flight_tool = SearchFlight()
accommodation_tool = SearchAccommodation()
restaurant_tool = SearchRestaurant()
attraction_tool = SearchAttraction()
city_tool = SearchCity()
distance_tool = GoogleDistanceMatrix()
city_state = open("../database/background/citySet_with_states.txt", "r").read().split("\n") 
city_state_map = {x:y for x,y in [unit.split('\t') for unit in city_state]}


def check_cuisine_preferences(question, tested_data):
    """Check if required cuisines are included in the trip."""
    if not question.get("local_constraint", {}).get("cuisine"):
        return None, None
    
    required_cuisines = set(question["local_constraint"]["cuisine"])
    found_cuisines = set()
    
    for i in range(min(question["days"], len(tested_data))):
        unit = tested_data[i]
        
        for meal in ['breakfast', 'lunch', 'dinner']:
            if unit.get(meal) and unit[meal] != '-':
                name, city = get_valid_name_city(unit[meal])
                if city == question["org"]:  # Skip origin city
                    continue
                
                restaurant_data = restaurant_tool.data[
                    (restaurant_tool.data["Name"].astype(str).str.contains(re.escape(name))) & 
                    (restaurant_tool.data["City"] == city)
                ]
                if len(restaurant_data) > 0:
                    cuisines = restaurant_data.iloc[0]["Cuisines"]
                    # print(name, city, cuisines)
                    for cuisine in required_cuisines:
                        if cuisine in cuisines:
                            found_cuisines.add(cuisine)
    
    missing_cuisines = required_cuisines - found_cuisines
    if missing_cuisines:
        return False, f"Missing required cuisines: {', '.join(missing_cuisines)}."
    
    return True, None


def check_room_type(question, tested_data):
    """Check if accommodation matches room type preferences."""
    expected_room = question.get("local_constraint", {}).get("room type") 
    if not expected_room:
        return None, None
    
    for i in range(min(question["days"], len(tested_data))):
        unit = tested_data[i]
        if unit.get("accommodation") and unit["accommodation"] != '-':
            name, city = get_valid_name_city(unit["accommodation"])
            accommodation_data = accommodation_tool.data[
                (accommodation_tool.data["NAME"].astype(str).str.contains(re.escape(name))) & 
                (accommodation_tool.data["city"] == city)
            ]
            
            if len(accommodation_data) > 0:
                hotel = accommodation_data.iloc[0]
                # print(name, city, hotel["room type"])
                # Check room type
                if expected_room == "not shared room" and hotel["room type"] == "Shared room":
                    return False, f"Room type should not be shared room."
                elif expected_room == "shared room" and hotel["room type"] != "Shared room":
                    return False, f"Room type should be shared room."
                elif expected_room == "private room" and hotel["room type"] != "Private room":
                    return False, f"Room type should be private room."
                elif expected_room == "entire room" and hotel["room type"] != "Entire home/apt":
                    return False, f"Room type should be entire room."
                
    return True, None


def check_room_rule(question, tested_data):
    """Check if accommodation matches room rule preferences."""
    expected_rule = question.get("local_constraint", {}).get("house rule")
    if not expected_rule:
        return None, None
    
    for i in range(min(question["days"], len(tested_data))):
        unit = tested_data[i]
        if unit.get("accommodation") and unit["accommodation"] != '-':
            name, city = get_valid_name_city(unit["accommodation"])
            accommodation_data = accommodation_tool.data[
                (accommodation_tool.data["NAME"].astype(str).str.contains(re.escape(name))) & 
                (accommodation_tool.data["city"] == city)
            ]
            if len(accommodation_data) > 0:
                hotel = accommodation_data.iloc[0]
                house_rules = str(hotel["house_rules"])
                # print(name, city, house_rules)
                if expected_rule == "smoking" and "No smoking" in house_rules:
                    return False, f"House rule should allow smoking."
                elif expected_rule == "parties" and "No parties" in house_rules:
                    return False, f"House rule should allow parties."
                elif expected_rule == "children under 10" and "No children under 10" in house_rules:
                    return False, f"House rule should allow children under 10."
                elif expected_rule == "visitors" and "No visitors" in house_rules:
                    return False, f"House rule should allow visitors."
                elif expected_rule == "pets" and "No pets" in house_rules:
                    return False, f"House rule should allow pets."

    return True, None


def check_valid_transportation(question, tested_data): 
    expected_trans = question.get("local_constraint", {}).get("transportation")
    if not expected_trans:
        return None, None
    
    for i in range(min(question["days"], len(tested_data))):
        unit = tested_data[i]
        if unit.get("transportation") and unit["transportation"] != '-':
            transport_type = detect_transportation_type(unit["transportation"])
            
            if expected_trans == "no flight" and transport_type == "flight":
                return False, f"Transportation should not include flights."  
            if expected_trans == "no self-driving" and transport_type == "driving":
                return False, f"Transportation should not include self-driving."
            
    return True, None


def calculate_total_cost(question, tested_data):
    """Calculate the total cost of the trip."""
    total_cost = 0
    
    for i in range(min(question["days"], len(tested_data))):
        unit = tested_data[i]
        
        # Transportation cost
        if unit.get("transportation") and unit["transportation"] != '-':
            org_city, dest_city = extract_from_to(unit["transportation"]) 
            if not org_city or not dest_city: 
                org_city, dest_city = extract_from_to(unit["current_city"])
            
            if not org_city or not dest_city: 
                pass 
            else:
                transport_type = detect_transportation_type(unit["transportation"])
                
                if transport_type == 'flight':
                    flight_num = unit["transportation"].split('Flight Number: ')[1].split(',')[0]
                    flight_data = flight_tool.data[flight_tool.data["Flight Number"] == flight_num]
                    if len(flight_data) > 0:
                        total_cost += flight_data.iloc[0]["Price"] * question["people_number"]
                elif transport_type == 'driving':
                    cost = distance_tool.run_for_evaluation(org_city, dest_city, 'driving').get("cost")
                    total_cost += cost * math.ceil(question['people_number'] * 1.0 / 5)
                elif transport_type == 'taxi':
                    cost = distance_tool.run_for_evaluation(org_city, dest_city, 'taxi').get("cost")
                    total_cost += cost * math.ceil(question['people_number'] * 1.0 / 4)
        # print(f"Added transportation cost for day {i+1}: {total_cost}")

        # Restaurant costs
        for meal in ['breakfast', 'lunch', 'dinner']:
            if unit.get(meal) and unit[meal] != '-':
                name, city = get_valid_name_city(unit[meal])
                restaurant_data = restaurant_tool.data[
                    (restaurant_tool.data["Name"].astype(str).str.contains(re.escape(name))) & 
                    (restaurant_tool.data["City"] == city)
                ]
                if len(restaurant_data) > 0:
                    total_cost += restaurant_data.iloc[0]["Average Cost"] * question["people_number"]
        # print(f"Added meal cost for day {i+1}: {total_cost}")
        
        # Accommodation cost
        if unit["accommodation"] and unit["accommodation"] != '-':
            name, city = get_valid_name_city(unit["accommodation"])
            accommodation_data = accommodation_tool.data[
                (accommodation_tool.data["NAME"].astype(str).str.contains(re.escape(name))) & 
                (accommodation_tool.data["city"] == city)
            ]
            if len(accommodation_data) > 0:
                price = accommodation_data.iloc[0]["price"]
                max_occupancy = accommodation_data.iloc[0]["maximum occupancy"]
                total_cost += price * math.ceil(question["people_number"] / max_occupancy)
        # print(f"Added accommodation cost for day {i+1}: {total_cost}")
    # print(f"Total cost: {total_cost}")
    return total_cost


def check_budget_constraint(question, tested_data):
    """Check if the total cost is within budget."""
    total_cost = calculate_total_cost(question, tested_data)
    
    if total_cost > question["budget"]:
        return False, f"Total cost ${total_cost:.2f} exceeds budget ${question['budget']:.2f}."
    
    return True, None


def check_hardconstraint(question, tested_data): 
    # Rules 
    #  - Valid cuisine preferences
    #  - Valid room rule 
    #  - Valid transportation restrictions 
    #  - Valid budget  
    #  - Valid room type

    result_info = {} 
    
    result_info["valid_cuisine"] = check_cuisine_preferences(question, tested_data)

    result_info["valid_room_type"] = check_room_type(question, tested_data) 

    result_info["valid_room_rule"] = check_room_rule(question, tested_data) 

    result_info["valid_transportation"] = check_valid_transportation(question, tested_data)  

    result_info["valid_cost"] = check_budget_constraint(question, tested_data)
  
    return result_info


if __name__ == "__main__":
    question = {
        "query": "Please plan a trip for me starting from Sarasota to Chicago for 3 days, from March 22nd to March 24th, 2022. The budget for this trip is set at $1,900.", 
        "days": 3, 
        "org": "Sarasota", 
        "dest": "Chicago", 
        "visiting_city_number": 1, 
        "budget": 1900,
        "local_constraint": {
            "house rule": None, 
            "cuisine": ["Indian", "Cafe", "Seafood"],
            "room type": None, 
            "transportation": "no self-driving"
        },
        "people_number": 1
    }

    tested_data = [
        {'day': 1, 'current_city': 'from Sarasota to Chicago', 'transportation': 'Flight Number: F3984576, from Sarasota to Chicago, Departure Time: 05:14, Arrival Time: 06:50', 'breakfast': '-', 'attraction': 'Millennium Park, Chicago;', 'lunch': '-', 'dinner': 'The Black Pearl, Chicago', 'accommodation': 'Amazing new private bedroom 5 min to subway, Chicago'}, 
        {'day': 2, 'current_city': 'Chicago', 'transportation': '-', 'breakfast': '-', 'attraction': 'Willis Tower, Chicago;Grant Park, Chicago;Buckingham Fountain, Chicago;Museum of Science and Industry, Chicago;', 'lunch': "Pantry d'or, Chicago", 'dinner': 'FIO Cookhouse and Bar, Chicago', 'accommodation': 'Amazing new private bedroom 5 min to subway, Chicago'}, 
        {'day': 3, 'current_city': 'from Chicago to Sarasota', 'transportation': 'Flight Number: F3600004, from Chicago to Sarasota, Departure Time: 10:14, Arrival Time: 14:01', 'breakfast': 'Starbucks, Chicago;Gyan Vaishnav, Chicago', 'attraction': 'Riverwalk, Chicago;', 'lunch': '-', 'dinner': '-', 'accommodation': '-'}
    ]

    result_info = check_hardconstraint(question, tested_data) 
    print(result_info)
