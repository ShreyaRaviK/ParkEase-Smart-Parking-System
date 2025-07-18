import requests

class TrichyWeatherClassifier:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.openweathermap.org/data/2.5/weather"
        # Trichy's approximate coordinates (lat/lon)
        self.trichy_lat = 10.7905
        self.trichy_lon = 78.7047

    def classify_weather(self):
        try:
            params = {
                "lat": self.trichy_lat,
                "lon": self.trichy_lon,
                "appid": self.api_key,
                "units": "metric"  # Get temp in °C
            }

            response = requests.get(self.base_url, params=params)
            response.raise_for_status()  # Raise error for bad status codes

            weather_data = response.json()
            return self._evaluate_weather(weather_data)

        except requests.exceptions.RequestException as e:
            return f"Error fetching data: {str(e)}"

    def _evaluate_weather(self, data):
        temp = data["main"]["temp"]
        humidity = data["main"]["humidity"]
        rain = data.get("rain", {}).get("1h", 0)  # Rain in last hour (mm)
        wind_speed = data["wind"]["speed"]  # Wind speed (m/s)

        # Classification Logic
        if (temp > 36 or temp < 18) or (humidity > 85) or (rain > 15) or (wind_speed > 10):
            return "bad"  # Extreme heat/cold, heavy rain, or strong winds
        elif (20 <= temp <= 30) and (humidity < 70) and (rain < 2.5):
            return "good"  # Pleasant conditions
        else:
            return "average"  # Moderate weather

# Example Usage
if __name__ == "__main__":
    API_KEY = "2cc77eedcd3b191bf76a5b2e2edce3c4"  # Replace with your key
    classifier = TrichyWeatherClassifier(API_KEY)

    result = classifier.classify_weather()
    print(f"Current weather in Trichy is: {result.upper()}")