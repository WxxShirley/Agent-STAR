import pandas as pd


class SearchRestaurant:
    def __init__(self, path="../database/clean_restaurant_2022.csv"):
        self.path = path
        self.data = pd.read_csv(self.path).dropna()[['Name','Average Cost','Cuisines','Aggregate Rating','City']]
        print("Tool SearchRestaurant loaded.")

    def call(self, parameters: dict) -> str:
        try:
            # 0 - Parameters validation 
            if "city" not in parameters:
                return "Invalid parameters. Please provide city." 
            city = parameters["city"]

            # 1 - Data filtering 
            filtered_data = self.data[self.data["City"] == city]

            # 2 - Format results 
            if len(filtered_data) == 0:
                return f"There is no restaurant in {city}. Please rethink your restaurant search and try again."
            results = [] 
            for i, row in enumerate(filtered_data.itertuples(index=False)):  
                cur_result = f"{i+1}. [{row[0]}] Avg. Cost ${row[1]}. Cuisines: {row[2]}. Rating: {row[3]}\n" 
                results.append(cur_result) 

            return f"A SearchRestaurant for city {city} found the following {len(results)} restaurants:\n" + "\n".join(results)
        except Exception as e:
            return f"Tool calling error: {e}" 


if __name__ == "__main__":
    search_restaurant = SearchRestaurant(path="../../database/clean_restaurant_2022.csv")

    test_params = [
        {"city": "New York"},
        {"city": "Los Angeles"},
        {"city": "Vancouver"},
    ]

    for param in test_params:
        print(search_restaurant.call(param))
        print("-"*40)
    