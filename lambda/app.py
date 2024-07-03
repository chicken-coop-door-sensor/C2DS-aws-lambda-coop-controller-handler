import json
import os
from datetime import datetime
from datetime import timedelta

import boto3
import pytz
import requests
from timezonefinder import TimezoneFinder


def convert_utc_to_local(utc_time_str, timezone_name):
    try:
        # Get the current date
        current_date = datetime.now().date()

        # Combine the current date with the provided UTC time
        combined_utc_str = f"{current_date} {utc_time_str}"

        # Define the UTC timezone
        utc_timezone = pytz.utc

        # Convert the combined string to a datetime object and localize to UTC
        utc_datetime = utc_timezone.localize(datetime.strptime(combined_utc_str, "%Y-%m-%d %H:%M"))

        # Get the local timezone object
        local_timezone = pytz.timezone(timezone_name)

        # Convert the UTC time to local time in the specified timezone
        local_time = utc_datetime.astimezone(local_timezone)

        # Format the local time to 'HH:MM'
        local_time_str = local_time.strftime('%H:%M')

        return local_time_str
    except pytz.UnknownTimeZoneError:
        return f"Unknown timezone: {timezone_name}"
    except ValueError:
        return "Incorrect time format. Please use 'HH:MM'."


def get_local_time(timezone_name):
    try:
        # Get the timezone object
        timezone = pytz.timezone(timezone_name)

        # Get the current time in the specified timezone
        local_time = datetime.now(timezone).strftime('%H:%M')

        return local_time
    except pytz.UnknownTimeZoneError:
        return f"Unknown timezone: {timezone_name}"


def get_utc_offset(timezone_name):
    try:
        # Create a timezone object
        tz = pytz.timezone(timezone_name)

        # Get the current time in the given timezone
        current_time = datetime.now(tz)

        # Get the offset for standard time
        standard_offset = tz.utcoffset(current_time.replace(tzinfo=None)).total_seconds() / 3600

        # Get the offset during daylight saving time
        dst_offset = tz.dst(current_time.replace(tzinfo=None)).total_seconds() / 3600 if tz.dst(
            current_time.replace(tzinfo=None)) else 0

        # Calculate the total offset during DST
        total_offset_during_dst = standard_offset + dst_offset

        return standard_offset, total_offset_during_dst

    except Exception as e:
        return str(e)


def is_dst(date, timezone):
    tz = pytz.timezone(timezone)
    aware_date = tz.localize(date, is_dst=None)
    return aware_date.dst() != timedelta(0)


def get_local_timezone_offset(date, timezone):
    standard_offset, dst_offset = get_utc_offset(timezone)

    if is_dst(date, timezone):
        return dst_offset  # CDT (Central Daylight Time)
    else:
        return standard_offset  # CST (Central Standard Time)


def get_timezone(latitude, longitude):
    # Create an instance of TimezoneFinder
    tf = TimezoneFinder()
    # Get the timezone name
    return tf.timezone_at(lat=float(latitude), lng=float(longitude))


def get_local_twilight_times(latitude, longitude):
    sunrise_utc = None
    sunset_utc = None
    date = datetime.now()  # Today's date
    timezone = get_timezone(latitude, longitude)
    url = (f"https://aa.usno.navy.mil/api/rstt/oneday?date={date.strftime('%Y-%m-%d')}&coords={latitude},{longitude}")
    print(url)
    response = requests.get(url)
    response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)
    data = response.json()
    print(data)
    sundata = data['properties']['data']['sundata']
    for entry in sundata:
        if entry['phen'] == 'Rise':
            sunrise_utc = entry['time']
        elif entry['phen'] == 'Set':
            sunset_utc = entry['time']

    if not sunrise_utc or not sunset_utc:
        raise ValueError("Sunrise or sunset time not found in the response")

    print(f"Sunrise UTC: {sunrise_utc}, Sunset UTC: {sunset_utc}")

    sunrise_local = convert_utc_to_local(sunrise_utc, timezone)
    sunset_local = convert_utc_to_local(sunset_utc, timezone)

    print(f"Sunrise local: {sunrise_local}, Sunset local: {sunset_local}")

    return sunrise_local, sunset_local


def is_daytime(longitude, latitude) -> bool:
    print(f"Latitude: {latitude}, Longitude: {longitude}")

    sunrise_local, sunset_local = get_local_twilight_times(latitude, longitude)
    print(f"Sunrise: {sunrise_local}, Sunset: {sunset_local}")

    timezone = get_timezone(latitude, longitude)
    print(f"Timezone: {timezone}")

    current_time = datetime.strptime(get_local_time(timezone), '%H:%M')
    sunrise = datetime.strptime(sunrise_local, '%H:%M')
    sunset = datetime.strptime(sunset_local, '%H:%M')

    current_time_only = current_time.time()
    sunrise_time = sunrise.time()
    sunset_time = sunset.time()

    if sunrise_time < sunset_time:
        if sunrise_time <= current_time_only < sunset_time:
            return True
        else:
            return False
    else:
        if current_time_only >= sunrise_time or current_time_only < sunset_time:
            return True
        else:
            return False


def reported_state(door_status, is_daytime):
    print(f"door_status: {door_status}")
    print(f"is_daytime: {is_daytime}")

    state = None
    if door_status == 'OPEN' and is_daytime:
        state = "CHICKEN_COOP_DOOR_OPEN_IN_DAYTIME_OK"
    elif door_status == 'CLOSED' and not is_daytime:
        state = "CHICKEN_COOP_DOOR_CLOSED_AT_NIGHT_OK"
    elif door_status == 'CLOSED' and is_daytime:
        state = "CHICKEN_COOP_DOOR_CLOSED_IN_DAYTIME_ERROR"
    elif door_status == 'OPEN' and not is_daytime:
        state = "CHICKEN_COOP_DOOR_OPEN_AT_NIGHT_ERROR"
    else:
        state = "CHICKEN_COOP_DOOR_SENSOR_FAILURE_ERROR"
    print(f"Returning state: {state}")
    return state


def get_ddb_state(table):
    STATE_KEY = 'coop_state'
    CURRENT_STATE_VALUE = 'current_status'
    try:
        response = table.get_item(Key={STATE_KEY: CURRENT_STATE_VALUE})
        print(f"full response: {response}")
        coop_state = response['Item']['Status']
        print(f"get current state returning: {coop_state}")
        return coop_state
    except KeyError:
        print("The key 'Status' does not exist in the item.")
        return None


def set_ddb_state(table, new_state):
    response = table.put_item(
        Item={
            'coop_state': 'current_status',
            'Status': new_state
        }
    )
    print(f'ddb response: {response}')
    print(f'Updated ddb state to: {new_state}')


def publish_sns_message(new_state, sns_topic_arn):
    sns = boto3.client('sns')
    sns_message = {
        "message": new_state
    }
    response = sns.publish(TopicArn=sns_topic_arn, Message=json.dumps(sns_message))
    print(f'Publish SNS response: {response}')


def publish_mqtt_message(new_state, mqtt_topic, iot_endpoint):
    mqtt = boto3.client('iot-data', endpoint_url=iot_endpoint)
    mqtt_message = {
        "state": new_state
    }
    response = mqtt.publish(topic=mqtt_topic, qos=1, payload=json.dumps(mqtt_message))
    print(f'Publish MQTT response: {response}')


def lambda_handler(event, context):
    latitude = os.getenv('LATITUDE')
    longitude = os.getenv('LONGITUDE')
    ddb_table_name = os.getenv('DDB_TABLE_NAME')
    sns_topic_arn = os.getenv('SNS_TOPIC_ARN')
    mqtt_topic = os.getenv('MQTT_TOPIC')
    iot_endpoint = os.getenv('IOT_ENDPOINT')

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(ddb_table_name)

    print("Received event: " + json.dumps(event, indent=2))
    door_status = event.get('door')

    now_daytime = is_daytime(longitude, latitude)
    print(f"Is it daytime? {now_daytime}")

    new_state = reported_state(door_status, now_daytime)
    print(f"New state: {new_state}")

    current_state = get_ddb_state(table)
    print(f"Current state: {current_state}")

    if new_state != current_state:
        print("State has changed. Updating DDB, publishing SNS and MQTT messages.")
        set_ddb_state(table, new_state)
        publish_sns_message(new_state, sns_topic_arn)
    else:
        print("State has not changed. No action required.")

    # Publish MQTT message always because the devices need to know the current state
    publish_mqtt_message(new_state, mqtt_topic, iot_endpoint)
