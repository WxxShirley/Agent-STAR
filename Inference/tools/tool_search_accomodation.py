import pandas as pd


class SearchAccommodation:
    def __init__(self, path="../database/clean_accommodations_2022.csv"):
        self.path = path
        self.data = pd.read_csv(self.path).dropna()[['NAME','price','room type', 'house_rules', 'minimum nights', 'maximum occupancy', 'review rate number', 'city']]
        print("Tool SearchAccommodation loaded.")
    
    def call(self, parameters: dict) -> str:
        try:
            # 0 - Parameters validation 
            if "city" not in parameters:
                return "Invalid parameters. Please provide city." 
            city = parameters["city"]

            # 1 - Data filtering 
            filtered_data = self.data[self.data["city"] == city]

            # 2 - Format results
            if len(filtered_data) == 0:
                return f"There is no accommodation in {city}. Please rethink your accommodation search and try again."

            results = [] 
            for i, row in enumerate(filtered_data.itertuples(index=False)):  
                cur_result = f"{i+1}. [{row[0]}] ${row[1]}. Room Type: {row[2]}, House Rules: {row[3]}, Minimum Nights: {row[4]}, Maximum Occupancy: {row[5]}, Review Rate Number: {row[6]}\n" 
                results.append(cur_result) 
            return f"A SearchAccommodation for {city} found the following {len(results)} accommodations:\n" + "\n".join(results)
        except Exception as e:
            return f"Tool calling error: {e}" 


if __name__ == "__main__":
    search_accommodation = SearchAccommodation(path="../../database/clean_accommodations_2022.csv")

    test_params = [
        {"city": "New York"},
        {"city": "Champaign"},
        {"city": "Los Angeles"},
        {"city": "Seattle"},
        {"city": "Vancouver"}
    ]

    for param in test_params:
        print(search_accommodation.call(param))
        print("-"*40)
