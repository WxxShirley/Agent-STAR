class SearchCity:
    def __init__(self, path="../database/background/citySet_with_states.txt") -> None:
        self.path = path
        self.load_data()
        print("Tool SearchCity loaded.")

    def load_data(self):
        cityStateMapping = open(self.path, "r").read().strip().split("\n")
        self.data = {}
        for unit in cityStateMapping:
            city, state = unit.split("\t")
            if state not in self.data:
                self.data[state] = [city]
            else:
                self.data[state].append(city)
    
    def call(self, parameters: dict) -> str:
        try:
            # 0 - Parameters validation 
            if "state" not in parameters:
                return "Invalid parameters. Please provide state." 
            state = parameters["state"]
            # 1 - Data filtering 
            results = self.data.get(state, [])
            
            # 2 - Format results 
            if len(results) == 0:
                return f"There is no city in {state}. Please rethink your city search and try again."
            return f"A SearchCity for state {state} found the following {len(results)} cities:\n" + ", ".join(results)
        except Exception as e:
            return f"Tool calling error: {e}" 


if __name__ == "__main__":
    search_city = SearchCity(path="../../database/background/citySet_with_states.txt")

    test_params = [
        {"state": "Banana"},
        {"state": "California"},
        {"state": "Texas"},
    ]

    for param in test_params:
        print(search_city.call(param))
        print("-"*40)
