import pandas as pd
import numpy as np


def check_value(val):
    return val is not None and val != "" and not val is np.nan


class GoogleDistanceMatrix:
    def __init__(self) -> None:
        # origin, destination, cost, duration, distance
        try:
            self.data =  pd.read_csv('../../database/distance.csv')
        except: 
            self.data =  pd.read_csv('../database/distance.csv')
        print("Tool GoogleDistanceMatrix loaded.")
    
    def call(self, parameters: dict) -> str:
        try:
            # 0 - Parameters validation 
            if "departure" not in parameters or "destination" not in parameters:
                return "Invalid parameters. Please provide departure, destination and mode." 
            
            origin = parameters["departure"]
            destination = parameters["destination"]
            mode = parameters.get("mode", "driving")

            # 1 - Data filtering 
            filtered_data = self.data[(self.data["origin"] == origin) & (self.data["destination"] == destination)] 
            
            # 2 - Format results
            if len(filtered_data):
                if not check_value(filtered_data['duration'].values[0]) or not check_value(filtered_data['distance'].values[0]):
                    result = f"Sorry, we cannot find the distance between {origin} and {destination}." 
                else:
                    duration = filtered_data['duration'].values[0] 
                    distance = filtered_data['distance'].values[0]
                    if "driving" in mode: 
                        cost = int(eval(distance.replace("km","").replace(",","").strip()) * 0.05)
                    else: # taxi
                        cost = int(eval(distance.replace("km","").replace(",","").strip()))
                    
                    if "day" in duration:
                        return "The required time exceeds a single day, we cannot provide the cost. Please consider an alternative transportation instead."

                    result = f"A GoogleDistanceMatrix found the following information:\n{mode}, from {origin} to {destination}, duration: {duration}, distance: {distance}, cost: ${cost}"
            else:
                result = "No valid information found. Please rethink your distance search and try again." 

            return result
        except Exception as e:
            return f"Tool calling error: {e}" 

    def run_for_evaluation(self, origin, destination, mode='driving'): 
        info = {
            "origin": origin,
            "destination": destination,
            "cost": None, 
            "duration": None,  
            "distance": None, 
        }
        response = self.data[(self.data["origin"] == origin) & (self.data["destination"] == destination)]
        if len(response): 
            if not check_value(response['duration'].values[0]) or not check_value(response['distance'].values[0]):
                return info 
            
            info["duration"] = response['duration'].values[0]
            info["distance"] = response['distance'].values[0]
            
            if 'day' not in info["duration"]: 
                if 'driving' in mode: 
                    info["cost"] = int(eval(info["distance"].replace("km","").replace(",","").strip()) * 0.05)
                else: # taxi
                    info["cost"] = int(eval(info["distance"].replace("km","").replace(",","").strip()))

            return info 
        
        return info


if __name__ == "__main__": 
    google_distance = GoogleDistanceMatrix() 

    test_params = [
        {"departure": "Boston", "destination": "Washington", "mode": "driving"},
        {"departure": "Dallas", "destination": "San Antonio", "mode": "driving"},
        {"departure": "New York", "destination": "London", "mode": "driving"}, 
        {"departure": "Detroit", "destination": "Norfolk", "mode": "taxi"},
        {"departure": "Hartford", "destination": "Denver", "mode": "driving"},
    ]

    for param in test_params:
        print(google_distance.call(param))
        # print(google_distance.run_for_evaluation(param["departure"], param["destination"], param["mode"]))
        print("-"*40)
