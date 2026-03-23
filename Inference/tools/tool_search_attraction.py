import pandas as pd


class SearchAttraction:
    def __init__(self, path="../database/attractions.csv"):
        self.path = path
        self.data = pd.read_csv(self.path).dropna()[['Name','Latitude','Longitude','Address','Phone','Website',"City"]]
        print("Tool SearchAttraction loaded.")

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
                return f"There is no attraction in {city}. Please rethink your attraction search and try again."
            
            results = []  
            for i, row in enumerate(filtered_data.itertuples(index=False)):  
                cur_result = f"{i+1}. [{row[0]}]({row[5]}) Address: {row[3]}. Contact: {row[4]}\n"
                results.append(cur_result) 
            return f"A SearchAttraction for city {city} found the following {len(results)} attractions:\n" + "\n".join(results)
        except Exception as e:
            return f"Tool calling error: {e}" 


if __name__ == "__main__":
    search_attraction = SearchAttraction(path="../../database/attractions.csv")

    test_params = [
        {"city": "New York"},
        {"city": "Champaign"},
        {"city": "Los Angeles"},
        {"city": "Chicago"},
    ]

    for param in test_params:
        print(search_attraction.call(param))
        print("-"*40)
