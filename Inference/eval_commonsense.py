import re 
from tools import * 
import os 

RELAX_BREAKFAST = os.getenv("RELAX_BREAKFAST", "False").lower() == "true"


flight_tool = SearchFlight()
accommodation_tool = SearchAccommodation()
restaurant_tool = SearchRestaurant()
attraction_tool = SearchAttraction()
city_tool = SearchCity()
distance_tool = GoogleDistanceMatrix()
city_state = open("../database/background/citySet_with_states.txt", "r").read().split("\n") 
city_state_map = {x:y for x,y in [unit.split('\t') for unit in city_state]}


def extract_from_to(text: str):
    pattern = r"from\s+(.+?)\s+to\s+([^,]+)(?=[,\s]|$)"
    matches = re.search(pattern, text)
    return matches.groups() if matches else (None, None)


def get_valid_name_city(info):
    pattern = r'(.*?),\s*([^,]+)(\(\w[\w\s]*\))?$'
    match = re.search(pattern, info)
    if match:
        return match.group(1).strip(), match.group(2).strip().strip()
    else:
        print(f"{info} can not be parsed, '-' will be used instead.")
        return "-","-"


def detect_transportation_type(transport_text):
    """
    Detect transportation type from text.
    Returns: 'flight', 'taxi', or 'driving' (default)
    
    Logic:
    - If contains 'flight' or 'flight number' -> 'flight'
    - Else if contains 'taxi' -> 'taxi'
    - Else if contains driving-related keywords -> 'driving'
    - Otherwise, default to 'driving' (as per requirement: if no Flight/Taxi, assume Driving)
    """
    if not transport_text or transport_text == '-':
        return None
    
    transport_lower = transport_text.lower()
    
    # Check for flight (highest priority)
    if 'flight' in transport_lower or 'flight number' in transport_lower:
        return 'flight'
    
    # Check for taxi
    if 'taxi' in transport_lower:
        return 'taxi'
    
    # Check for driving-related keywords
    driving_keywords = ['driving', 'drive', 'self-driving', 'self driving', 'car', 'vehicle', 'automobile', 'auto']
    if any(keyword in transport_lower for keyword in driving_keywords):
        return 'driving'
    
    # Default to driving if no Flight/Taxi detected
    return 'driving'


################################################################################
######################### Commonsense 1 - Valid Keys ###########################
################################################################################

def check_visiting_city_number(question, tested_data):
    """Check if the number of visiting cities matches the requirement."""
    if 'visiting_city_number' not in question:
        return True
    
    visited_cities = set()
    
    for i in range(min(question["days"], len(tested_data))):
        city_value = tested_data[i]['current_city']
        
        if 'from' in city_value:
            source, destination = extract_from_to(city_value)
            if i == 0 and source != question["org"]:
                return False 

            visited_cities.add(source)
            visited_cities.add(destination)
        else:
            visited_cities.add(city_value)
    
    # Remove origin city from count
    visited_cities.discard(question["org"])
    # print(len(visited_cities), question["visiting_city_number"])
    
    if len(visited_cities) != question["visiting_city_number"]:
        return False

    return True


def check_day_count(question, tested_data):
    """Check if the number of days matches the requirement."""
    valid_days = 0
    
    for i in range(min(question["days"], len(tested_data))):
        unit = tested_data[i]
        if unit and unit.get('current_city') and unit['current_city'] != "You don't need to fill in the information for this or later days.":
            valid_days += 1
    
    if valid_days != question["days"]:
        return False
    
    return True


def check_completeness(question, tested_data):
    """Check if all required fields are present for each day."""
    needed_number = 6 * question["days"] 
    total_valid_info = 0

    if not check_day_count(question, tested_data):
        return False, "The number of days is not correct."
    
    if not check_visiting_city_number(question, tested_data):
        return False, "The number of visiting cities is not correct."

    required_fields = ['transportation', 'breakfast', 'lunch', 'dinner', 'attraction', 'accommodation']
    
    for i in range(min(question["days"], len(tested_data))):
        unit = tested_data[i]
        
        for field in required_fields:
            if field not in unit:
                return False, f"No {field} information is provided for day {i+1}."
            if unit[field] in ['', '-']:
                # Special cases for different days
                set_fields = ['breakfast', 'lunch', 'dinner', 'attraction'] if not RELAX_BREAKFAST else ['lunch', 'dinner', 'attraction']
                if field == 'transportation':
                    if 'from ' in unit.get('current_city', '') or 'to ' in unit.get('current_city', ''): 
                        return False, f"Transportation is required on day {i+1}."
                elif field == 'accommodation' and i < question["days"] - 1:
                    return False, f"Accommodation is required on day {i+1}."
                # TODO: Relaxed the constraint for breakfast
                elif field in set_fields and 'from ' not in unit.get('current_city', ''):
                    return False, f"{field.capitalize()} is required on day {i+1}."
        
        for key in unit: 
            if unit[key] and unit[key] != '-':
                total_valid_info += 1 
    
    if total_valid_info * 1.0 / needed_number < 0.5:
        return False, f"The completeness rate is less than 50%."
    
    return True, None


################################################################################
######################### Commonsense 2 - Hallucination ########################
################################################################################

def check_hallucination(question, tested_data):
    """Check if all venues and transportation exist in the database."""
    for i in range(min(question["days"], len(tested_data))):
        unit = tested_data[i]
        
        # Check transportation
        if unit.get("transportation") and unit["transportation"] != '-':
            org_city, dest_city = extract_from_to(unit["transportation"])
            if not org_city or not dest_city:
                org_city, dest_city = extract_from_to(unit["current_city"])
            
            transport_type = detect_transportation_type(unit["transportation"])
            
            if transport_type == 'flight':
                try:
                    flight_num = unit["transportation"].split('Flight Number: ')[1].split(',')[0]
                except Exception as e:
                    return False, f"Flight number is invalid"
                
                if len(flight_tool.data[
                    (flight_tool.data["Flight Number"] == flight_num) & 
                    (flight_tool.data["OriginCityName"] == org_city) & 
                    (flight_tool.data["DestCityName"] == dest_city)
                ]) == 0:
                    return False, f"Flight {flight_num} from {org_city} to {dest_city} does not exist."

            elif transport_type in ['driving', 'taxi']: 
                try:
                    result = distance_tool.run_for_evaluation(org_city, dest_city, 'driving') 
                    if result.get('cost') is None:
                        return False, f"Self-driving from {org_city} to {dest_city} is not available." 
                except Exception as e: 
                    return False, f"Self-driving from {org_city} to {dest_city} is not available."

        # Check restaurants
        # TODO: relax the constraint for breakfast
        meals = ['lunch', 'dinner', 'breakfast'] if not RELAX_BREAKFAST else ['lunch', 'dinner']
        for meal in meals:
            if unit.get(meal) and unit[meal] != '-':
                name, city = get_valid_name_city(unit[meal])
                # print(meal, name, city)
                if len(restaurant_tool.data[
                    (restaurant_tool.data["Name"].astype(str).str.contains(re.escape(name))) & 
                    (restaurant_tool.data["City"] == city)
                ]) == 0:
                    return False, f"Restaurant {name} in {city} does not exist."
                
        # Check attractions
        if unit.get("attraction") and unit["attraction"] != '-':
            attractions = unit["attraction"].split(';')[:-1]
            for attraction in attractions:
                name, city = get_valid_name_city(attraction)
                if len(attraction_tool.data[
                    (attraction_tool.data["Name"].astype(str).str.contains(re.escape(name))) & 
                    (attraction_tool.data["City"] == city)
                ]) == 0:
                    return False, f"Attraction {name} in {city} does not exist."
        
        # Check accommodation
        if unit.get("accommodation") and unit["accommodation"] != '-':
            name, city = get_valid_name_city(unit["accommodation"])
            if len(accommodation_tool.data[
                (accommodation_tool.data["NAME"].astype(str).str.contains(re.escape(name))) & 
                (accommodation_tool.data["city"] == city)
            ]) == 0:
                return False, f"Accommodation {name} in {city} does not exist."
    
    return True, None


################################################################################
###################### Commonsense 3 - No repeated meals #######################
################################################################################

def check_restaurant_diversity(question, tested_data): 
    restaurants = []
    
    for i in range(min(question["days"], len(tested_data))):
        unit = tested_data[i]
        # TODO: relax the constraint for breakfast 
        meals = ['lunch', 'dinner', 'breakfast'] if not RELAX_BREAKFAST else ['lunch', 'dinner']
        for meal in meals:
            if unit.get(meal) and unit[meal] != '-':
                if unit[meal] in restaurants:
                    return False, f"Restaurant '{unit[meal]}' is repeated on day {i+1}."
                restaurants.append(unit[meal])
    
    return True, None


################################################################################
###################### Commonsense 4 - No repeated attractions #################
################################################################################

def check_attraction_diversity(question, tested_data):
    """Check if attractions are diverse (no repeated attractions)."""
    attractions = []
    
    for i in range(min(question["days"], len(tested_data))):
        unit = tested_data[i]
        if unit.get("attraction") and unit["attraction"] != '-':
            day_attractions = unit["attraction"].split(';')[:-1]  # Remove empty last element
            for attraction in day_attractions:
                # attraction = attraction.strip()
                if attraction in attractions:
                    return False, f"Attraction '{attraction}' is repeated on day {i+1}."
                attractions.append(attraction)
    
    return True, None


################################################################################
######################## Commonsense 5 - Minimum nights ########################
################################################################################

def count_consecutive_values(lst):
    if not lst:
        return []

    result = []
    current_string = lst[0]
    count = 1 

    for i in range(1, len(lst)):
        if lst[i] == current_string:
            count += 1
        else:
            result.append((current_string, count))
            current_string = lst[i]
            count = 1

    result.append((current_string, count))  # Add the last group of values
    return result


def check_accommodation_minimum_nights(question, tested_data):
    """Check if accommodation bookings meet minimum night requirements."""
    accommodation_data = []
    
    for i in range(min(question["days"], len(tested_data))):
        unit = tested_data[i]
        if "accommodation" not in unit: 
            return False, f"No accommodation information is provided for day {i+1}." 

        accommodation_data.append(unit["accommodation"])
    
    consecutive_accommodations = count_consecutive_values(accommodation_data)
    
    for accommodation, nights in consecutive_accommodations:
        if accommodation and accommodation not in ['', '-']:
            name, city = get_valid_name_city(accommodation)
            filtered_hotel = accommodation_tool.data[
                (accommodation_tool.data["NAME"].astype(str).str.contains(re.escape(name))) & 
                (accommodation_tool.data["city"] == city)
            ]
            # print(filtered_hotel.to_string())
            if len(filtered_hotel) == 1:
                min_nights = filtered_hotel.iloc[0]["minimum nights"]
                if nights < min_nights:
                    return False, f"Accommodation {name} requires minimum {min_nights} nights, but only {nights} nights booked."
    
    return True, None


################################################################################
################### Commonsense 6 - Reasonable visiting cities #################
################################################################################

def check_city_route_logic(city_list):
    """
    Checks if the city sequence is valid. A valid sequence has every city (except the first and last) 
    appearing consecutively, and no city should appear again once its sequence is over.
    """ 

    if len(city_list) < 3:
        return False 

    visited_cities = set()
    
    i = 0 
    while i < len(city_list):
        city = city_list[i]
        
        if city in visited_cities and (i not in [0, len(city_list) - 1]):
            # print(f"City {city} is repeated, which is not allowed.")
            return False 
        
        count = 0 
        while i < len(city_list) and city_list[i] == city:
            count += 1
            i += 1
        
        if count == 1 and 0 < i-1 < len(city_list)-1:
            print(f'City {city} only appears once, which is not allowed.')
            return False 
        
        visited_cities.add(city)
    
    return True 


def check_reasonable_visiting_cities(question, tested_data): 
    """Check if the visiting cities are reasonable."""
    cities = []

    for i in range(min(question["days"], len(tested_data))):
        city_value = tested_data[i]['current_city']
        if 'from' in city_value:
            source, destination = extract_from_to(city_value)
            if i == 0 and source != question["org"]: 
                return False, f"The first city should be {question['org']}."

            cities.extend([source, destination])
        else:
            cities.append(city_value)
    if len(cities) and cities[0] != cities[-1]: 
        return False, "The visiting cities should form a closed loop." 
    
    if not check_city_route_logic(cities):
        return False, "The visiting cities should form a valid route." 

    for idx, city in enumerate(cities): 
        if city not in city_state_map:  
            return False, f"City {city} is not valid." 
        
        # TODO: check the logic for multi-day trips
        if idx not in [0, len(cities) - 1] and city_state_map[city] != question["dest"] and question["days"] > 3:
            return False, f"City {city} is not in destination state {question['dest']}." 
    return True, None


################################################################################
##################### Commonsense 7 - Valid transportation #####################
################################################################################

def check_transportation_consistency(question, tested_data):
    """Check if transportation types are consistent (no conflicting types)."""
    transportation_types = []
    if tested_data[0]["transportation"] and tested_data[0]["transportation"] != '-': 
        transport_type = detect_transportation_type(tested_data[0]["transportation"])
        if transport_type:
            transportation_types.append(transport_type)
    else:
        return False, "The transporation in day 1 should not be empty."
    
    for i in range(min(question["days"], len(tested_data))):
        unit = tested_data[i]
        if unit.get("transportation") and unit["transportation"] != '-':
            transport_type = detect_transportation_type(unit["transportation"])
            if transport_type:
                transportation_types.append(transport_type)
    
    # Check for conflicting transportation types
    if 'flight' in transportation_types and 'driving' in transportation_types:
        return False, "Cannot mix flight and self-driving transportation."
    
    if 'taxi' in transportation_types and 'driving' in transportation_types:
        return False, "Cannot mix taxi and self-driving transportation."
    
    return True, None


################################################################################
##################### Commonsense 8 - Valid day arrangement ####################
################################################################################

def check_valid_day_arrangement(question, tested_data):
    """Check if the day arrangement is valid."""
    for i in range(min(question["days"], len(tested_data))):
        unit = tested_data[i]
        current_city = unit.get('current_city', '')
        
        # Determine which cities we're in
        cities_in = []
        if 'from' in current_city:
            source, destination = extract_from_to(current_city)
            cities_in = [source, destination]
        else:
            cities_in = [current_city]

        # Check transportation 
        if "transportation" in unit and unit["transportation"] != "-":
            for city in cities_in: 
                if city not in unit["transportation"]:
                    return False, f"Transportation in day {i+1} is invalid city choice"
        
        # Check if meals are in the right cities
        for meal in ['breakfast', 'lunch', 'dinner']:
            if unit.get(meal) and unit[meal] != '-':
                flg = False 
                for city in cities_in:  
                    if city in unit[meal]:
                        flg = True 
                if not flg:
                    return False, f"{meal.capitalize()} '{unit[meal]}' is not in {cities_in} on day {i+1}."
        
        # Check if attractions are in the right cities
        if unit.get("attraction") and unit["attraction"] != '-':
            attractions = unit["attraction"].split(';')[:-1]
            for attraction in attractions:
                flg = False 
                for city in cities_in: 
                    if city in attraction: 
                        flg = True 
                if not flg:
                    return False, f"Attraction '{attraction}' is not in {cities_in} on day {i+1}."

        # Check if accommodation is in the right city
        if unit.get("accommodation") and unit["accommodation"] != '-':
            if cities_in[-1] not in unit["accommodation"]:
                return False, f"Accommodation '{unit['accommodation']}' should be in {cities_in[-1]}."
    
    return True, None


def check_commonsense(question, tested_data): 
    # Rules 
    #  - Reasonable visiting city number
    #  - Valid restaurants 
    #  - Valid attractions 
    #  - Valid accommodations  
    #  - Valid transportation   
    #  - Valid information in current city 
    #  - Valid information in sandbox 
    #  - No missing keys in the plan  
    
    result_info = {}

    result_info["is_not_absent"] = check_completeness(question, tested_data) 

    result_info["is_valid_information_in_sandbox"] = check_hallucination(question, tested_data)

    result_info["is_valid_restaurants"] = check_restaurant_diversity(question, tested_data) 

    result_info["is_valid_attractions"] = check_attraction_diversity(question, tested_data)

    result_info["is_valid_accommodation"] = check_accommodation_minimum_nights(question, tested_data)

    result_info["is_reasonable_visiting_city"] = check_reasonable_visiting_cities(question, tested_data)

    result_info["is_valid_transportation"] = check_transportation_consistency(question, tested_data)

    result_info["is_valid_information_in_current_city"] = check_valid_day_arrangement(question, tested_data)

    return result_info


if __name__ == "__main__": 
    question = {
        "query": "Please plan a trip for me starting from Sarasota to Chicago for 3 days, from March 22nd to March 24th, 2022. The budget for this trip is set at $1,900.", 
        "days": 3, 
        "org": "Sarasota", 
        "dest": "Chicago", 
        "visiting_city_number": 1, 
        "budget": 1900
    }

    tested_data = [
        {'day': 1, 'current_city': 'from Sarasota to Chicago', 'transportation': 'Flight Number: F3984576, from Sarasota to Chicago, Departure Time: 05:14, Arrival Time: 06:50', 'breakfast': '-', 'attraction': 'Millennium Park, Chicago;', 'lunch': '-', 'dinner': 'The Black Pearl, Chicago', 'accommodation': 'Amazing new private bedroom 5 min to subway, Chicago'}, 
        {'day': 2, 'current_city': 'Chicago', 'transportation': '-', 'breakfast': '-', 'attraction': 'Willis Tower, Chicago;Grant Park, Chicago;Buckingham Fountain, Chicago;Museum of Science and Industry, Chicago;', 'lunch': "Pantry d'or, Chicago", 'dinner': 'FIO Cookhouse and Bar, Chicago', 'accommodation': 'Amazing new private bedroom 5 min to subway, Chicago'}, 
        {'day': 3, 'current_city': 'from Chicago to Sarasota', 'transportation': 'Flight Number: F3600004, from Chicago to Sarasota, Departure Time: 10:14, Arrival Time: 14:01', 'breakfast': 'Starbucks, Chicago;Gyan Vaishnav, Chicago', 'attraction': 'Riverwalk, Chicago;', 'lunch': '-', 'dinner': '-', 'accommodation': '-'}
    ]

    result_info = check_commonsense(question, tested_data) 
    print(result_info)

    # test_cities = ['Chicago', 'Sarasota', 'Sarasota', 'Washtington', "New York", "New York", "Chicago"]
    # print(check_city_route_logic(test_cities))
