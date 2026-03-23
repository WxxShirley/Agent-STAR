import pandas as pd


class SearchFlight:
    def __init__(self, path="../database/clean_Flights_2022.csv"):
        self.path = path
        self.data = pd.read_csv(self.path).dropna()[['Flight Number', 'Price', 'DepTime', 'ArrTime', 'ActualElapsedTime','FlightDate','OriginCityName','DestCityName','Distance']]
        print("Tool SearchFlight loaded.")

    def call(self, parameters: dict) -> str:
        try:
            # 0 - Parameters validation
            if "departure" not in parameters or "destination" not in parameters or "date" not in parameters:
                return "Invalid parameters. Please provide departure, destination and date." 
            
            departure = parameters["departure"]
            destination = parameters["destination"]
            date = parameters["date"]

            # 1 - Data filtering 
            filtered_data = self.data[self.data["OriginCityName"] == departure]
            filtered_data = filtered_data[filtered_data["DestCityName"] == destination]
            filtered_data = filtered_data[filtered_data["FlightDate"] == date]

            # 2 - Format results
            if len(filtered_data) == 0:
                return f"There is no available flight from {departure} to {destination} on {date}. Please rethink your flight search and try again."
            
            results = []
            for i, row in enumerate(filtered_data.itertuples(index=False)): 
                # Flight Number, Price, DepTime, ArrTime, ActualElapsedTime, FlightDate, OriginCityName, DestCityName, Distance
                cur_result = f"{i+1}. [{row[0]}] ${row[1]}. Departure: {row[2]}, Arrival: {row[3]}, Actual Elapsed Time: {row[4]}, Distance: {row[8]} miles\n" 
                results.append(cur_result) 
            return f"A SearchFlight for {departure} to {destination} on {date} found the following {len(filtered_data)} flights:\n" + "\n".join(results)
        except Exception as e: 
            return f"Tool calling error: {e}" 


if __name__ == "__main__":
    flights = SearchFlight(path="../../database/clean_Flights_2022.csv")

    test_params = [
        {"departure": "New York", "destination": "London", "date": "2022-10-01"},
        {"departure": "Durango", "destination": "Denver", "date": "2022-04-04"},
        {"departure": "Washington", "destination": "Richmond", "date": "2022-05-05"},
        {"departure": "Buffalo", "destination": "Atlanta", "date": "2022-03-02"},
    ]

    for param in test_params:
        print(flights.call(param))
        print("-"*40)
