from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime, timedelta
import re 
import string 

app = Flask(__name__)

# --- Configuration ---
# IMPORTANT: Replace 'YOUR_OPENWEATHERMAP_API_KEY' with your actual key
# You can also set this as an environment variable for better security in production
OPENWEATHERMAP_API_KEY = os.environ.get('OPENWEATHERMAP_API_KEY', 'd076515451a75692ef26de8d300ed97c') # REPLACE THIS!
OPENWEATHERMAP_CURRENT_WEATHER_URL = "http://api.openweathermap.org/data/2.5/weather"
OPENWEATHERMAP_FORECAST_URL = "http://api.openweathermap.org/data/2.5/forecast"

# --- CORS Headers for Frontend Communication ---
# This is crucial for allowing your frontend (running on a different "origin" like file:// or localhost:port)
# to communicate with your backend.
@app.after_request
def add_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*') # Allow requests from any origin
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# --- Function to Get Current Weather Data ---
def get_current_weather_data(city_name):
    params = {
        'q': city_name,
        'appid': OPENWEATHERMAP_API_KEY,
        'units': 'metric' # Request temperature in Celsius
    }
    try:
        response = requests.get(OPENWEATHERMAP_CURRENT_WEATHER_URL, params=params)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching current weather for {city_name}: {e}")
        return None

# --- Function to Get Forecast Weather Data ---
def get_forecast_data(city_name, target_date):
    params = {
        'q': city_name,
        'appid': OPENWEATHERMAP_API_KEY,
        'units': 'metric'
    }
    try:
        response = requests.get(OPENWEATHERMAP_FORECAST_URL, params=params)
        response.raise_for_status()
        data = response.json()

        # Find the forecast closest to the target date (e.g., around noon for the day)
        # The forecast API returns 3-hour forecasts for the next 5 days
        
        # We look for a forecast around noon (12 PM) on the target date.
        # OpenWeatherMap's 'dt_txt' is in UTC, so we compare dates directly.
        
        closest_forecast = None
        min_time_diff = float('inf') # Initialize with a very large number

        for forecast_entry in data.get('list', []):
            forecast_time_utc = datetime.fromtimestamp(forecast_entry['dt']) # Convert Unix timestamp to datetime object
            
            # Check if the forecast entry's date matches our target_date
            if forecast_time_utc.date() == target_date: # Corrected: target_date is already a date object
                # For multiple forecasts on the same day, pick the one closest to midday
                target_midday_timestamp = datetime(target_date.year, target_date.month, target_date.day, 12, 0, 0).timestamp()
                
                time_diff = abs(forecast_time_utc.timestamp() - target_midday_timestamp)
                
                if time_diff < min_time_diff:
                    min_time_diff = time_diff
                    closest_forecast = forecast_entry
            # Optimization: if we've passed the target date, and haven't found a forecast for it, we can stop
            # because forecasts are ordered by time.
            elif forecast_time_utc.date() > target_date: # Corrected: target_date is already a date object
                break

        return closest_forecast # Returns the specific forecast entry or None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching forecast weather for {city_name} on {target_date.strftime('%Y-%m-%d')}: {e}")
        return None


# --- Chatbot Endpoint ---
@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message')
    if not user_message:
        return jsonify({"response": "No message provided.", "weather_category": "default"}), 400
    user_message = user_message.rstrip(string.punctuation).strip()
    city = None
    target_date = datetime.now().date() # Default to today's date
    is_forecast_request = False
    date_str = "today"
    
    user_message_lower = user_message.lower()

    # --- NLP Logic for Date/Time and City Extraction ---
    # Initialize a message that will have date/time keywords removed for cleaner city extraction
    cleaned_message_for_city_extraction = user_message_lower

    # Priority 1: Specific date keywords (tomorrow, day after tomorrow, next day)
    if "tomorrow" in user_message_lower:
        target_date = datetime.now().date() + timedelta(days=1)
        is_forecast_request = True
        cleaned_message_for_city_extraction = user_message_lower.replace("tomorrow", "").strip()
    elif "day after tomorrow" in user_message_lower:
        target_date = datetime.now().date() + timedelta(days=2)
        is_forecast_request = True
        cleaned_message_for_city_extraction = user_message_lower.replace("day after tomorrow", "").strip()
    elif "next day" in user_message_lower:
        target_date = datetime.now().date() + timedelta(days=1)
        is_forecast_request = True
        cleaned_message_for_city_extraction = user_message_lower.replace("next day", "").strip()
    # Priority 2: "in X days" pattern using regex for robustness
    else: # Only try this if no other date keyword was matched
        match = re.search(r"in (\d+)\s*days", user_message_lower) # Matches "in 3 days", "in 10 days" etc.
        if match:
            try:
                num_days = int(match.group(1)) # Extract the number of days (e.g., '3')
                if 1 <= num_days <= 5: # OpenWeatherMap free tier offers 5-day forecast
                    target_date = datetime.now().date() + timedelta(days=num_days)
                    is_forecast_request = True
                    # Remove the exact matched phrase (e.g., "in 2 days") from the message
                    cleaned_message_for_city_extraction = user_message_lower.replace(match.group(0), "").strip()
                else:
                    bot_response = "I can only provide a forecast up to 5 days from now."
                    # Send this response immediately if forecast is too far in the future
                    return jsonify({"response": bot_response, "weather_category": "default"})
            except ValueError:
                pass # If num_days isn't a valid integer, just ignore this date pattern

    # Remove any extra spaces that might have been left after cleaning date phrases
    cleaned_message_for_city_extraction = ' '.join(cleaned_message_for_city_extraction.split())

    # --- Now, perform City Extraction on the CLEANED message ---
    # This logic ensures date keywords are not accidentally picked up as part of the city.
    
    keywords_to_look_for_city = ["weather in ", "in ", "of ", "for "]
    for keyword in keywords_to_look_for_city: # Correct variable name used here
        if keyword in cleaned_message_for_city_extraction:
            parts = cleaned_message_for_city_extraction.split(keyword, 1) # Split only once
            if len(parts) > 1:
                city_candidate = parts[1].strip()
                # Remove common trailing punctuation/question marks
                city_candidate = city_candidate.replace('?', '').replace('.', '').replace('!', '')
                city = city_candidate.title() # Capitalize first letter of each word
                break # Stop after finding the first suitable city part
    
    # Fallback: if no specific keyword phrase found, try to guess it's the last word
    if not city and len(cleaned_message_for_city_extraction.split()) > 0:
        city_candidate = cleaned_message_for_city_extraction.split()[-1].strip()
        city_candidate = city_candidate.replace('?', '').replace('.', '').replace('!', '')
        city = city_candidate.title()
        
        # Additional check: if user just says "weather", don't treat "weather" as a city
        if city.lower() == "weather":
            city = None


    bot_response = "I'm sorry, I couldn't understand that. Please ask about the weather in a specific city, e.g., 'What's the weather in London?' or 'Weather in Paris tomorrow?'"
    weather_category = "default" # Default category

    if city:
        weather_data = None
        if is_forecast_request:
            # Call the forecast API
            weather_data = get_forecast_data(city, target_date)
        else:
            # Call the current weather API
            weather_data = get_current_weather_data(city)

        if weather_data:
            temp_celsius = round(weather_data['main']['temp'], 1)
            description = weather_data['weather'][0]['description']
            humidity = weather_data['main']['humidity']
            wind_speed = weather_data['wind']['speed']
            pressure = weather_data['main']['pressure']
            feels_like = round(weather_data['main']['feels_like'], 1)

            main_weather = weather_data['weather'][0]['main'].lower()
            # Determine weather_category as before
            if main_weather == 'clear': weather_category = 'clear'
            elif main_weather == 'clouds': weather_category = 'clouds'
            elif main_weather == 'rain' or main_weather == 'drizzle': weather_category = 'rain'
            elif main_weather == 'snow': weather_category = 'snow'
            elif main_weather == 'thunderstorm': weather_category = 'thunderstorm'
            elif main_weather in ['mist', 'smoke', 'haze', 'dust', 'fog', 'sand', 'ash', 'squall', 'tornado']: weather_category = 'atmosphere'
            
            specific_question_response = None # Initialize to None

            # Check for specific questions/intents
            if "humidity" in user_message_lower:
                specific_question_response = f"The humidity in {city} {date_str} is {humidity}%."
            elif "wind" in user_message_lower or "wind speed" in user_message_lower:
                specific_question_response = f"The wind speed in {city} {date_str} is {wind_speed} m/s."
            elif "pressure" in user_message_lower:
                specific_question_response = f"The atmospheric pressure in {city} {date_str} is {pressure} hPa."
            elif "feels like" in user_message_lower or "feel like" in user_message_lower:
                specific_question_response = f"It feels like {feels_like}°C in {city} {date_str}."
            elif "raining" in user_message_lower or "rain" in user_message_lower or "is it wet" in user_message_lower:
                # Check the main weather condition for rain
                if main_weather in ['rain', 'drizzle', 'thunderstorm']:
                    specific_question_response = f"Yes, it is currently {description} in {city} {date_str}."
                else:
                    specific_question_response = f"No, it is not raining in {city} {date_str}. It is {description}."
            elif "sunny" in user_message_lower or "sun" in user_message_lower:
                if main_weather == 'clear':
                    specific_question_response = f"Yes, it is sunny and clear skies in {city} {date_str}."
                else:
                    specific_question_response = f"No, it's not sunny in {city} {date_str}. It is {description}."
            elif "cloudy" in user_message_lower or "clouds" in user_message_lower:
                if main_weather == 'clouds':
                    specific_question_response = f"Yes, it is cloudy in {city} {date_str}."
                else:
                    specific_question_response = f"No, it's not cloudy in {city} {date_str}. It is {description}."
            elif "snowing" in user_message_lower or "snow" in user_message_lower:
                if main_weather == 'snow':
                    specific_question_response = f"Yes, it is snowing in {city} {date_str}."
                else:
                    specific_question_response = f"No, it is not snowing in {city} {date_str}. It is {description}."
            # Add more specific conditions as you like!
            
            # Construct response based on whether it's current or forecast
           # date_str = "today" # Default for current weather
            if is_forecast_request: # Only format date if it was a forecast request
                date_str = target_date.strftime("on %A, %d %B")

            if specific_question_response:
                bot_response = specific_question_response
            else:
                # Original comprehensive response (default)
                bot_response = (
                    f"The weather in {city} {date_str} is {description} with a temperature of {temp_celsius}°C "
                    f"(feels like {feels_like}°C). "
                    f"Humidity is {humidity}%, wind speed is {wind_speed} m/s, and pressure is {pressure} hPa."
                )
        else:
            if is_forecast_request:
                # Use target_date for error message if it was a forecast request
                formatted_target_date = target_date.strftime("%A, %d %B")
                bot_response = f"Sorry, I couldn't fetch forecast data for {city} on {formatted_target_date}. Please check the city name or try another date."
            else:
                bot_response = f"Sorry, I couldn't fetch current weather data for {city}. Please check the city name."
    
    return jsonify({"response": bot_response, "weather_category": weather_category})

# --- Run the Flask App ---
if __name__ == '__main__':
    app.run(debug=True, port=5000) # Runs on http://127.0.0.1:5000