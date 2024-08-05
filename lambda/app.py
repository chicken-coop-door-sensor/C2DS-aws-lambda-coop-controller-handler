import json
import os
from datetime import datetime

import boto3
import pytz

# Lookup table for LED colors based on states
LED_COLOR_LOOKUP = {
    "CHICKEN_COOP_DOOR_OPEN_IN_DAYTIME_OK": "LED_GREEN",
    "CHICKEN_COOP_DOOR_CLOSED_AT_NIGHT_OK": "LED_GREEN",
    "CHICKEN_COOP_DOOR_CLOSED_IN_DAYTIME_ERROR": "LED_FLASHING_YELLOW",
    "CHICKEN_COOP_DOOR_OPEN_AT_NIGHT_ERROR": "LED_FLASHING_RED",
    "CHICKEN_COOP_DOOR_SENSOR_FAILURE_ERROR": "LED_FLASHING_MAGENTA"
}

def get_local_time(timezone_name):
    try:
        # Get the timezone object
        timezone = pytz.timezone(timezone_name)

        # Get the current time in the specified timezone
        local_time = datetime.now(timezone).strftime('%H:%M')

        return local_time
    except pytz.UnknownTimeZoneError:
        return f"Unknown timezone: {timezone_name}"

def is_daytime(table_name) -> bool:
    print("Checking if it is daytime")
    ddb = boto3.resource('dynamodb')
    table = ddb.Table(table_name)

    response = table.get_item(Key={'primary_key': 'twilight'})

    item = response.get('Item')
    if item:
        sunrise = item.get('sunrise')
        sunset = item.get('sunset')
        timezone = item.get('timezone')
    else:
        raise Exception("No items found in DDB")

    print(f"Timezone: {timezone} Sunrise: {sunrise}, Sunset: {sunset}")

    current_time = datetime.strptime(get_local_time(timezone), "%H:%M").time()
    sunrise_time = datetime.strptime(sunrise, "%H:%M").time()
    sunset_time = datetime.strptime(sunset, "%H:%M").time()

    print(f"Current time: {current_time}, Sunrise time: {sunrise_time}, Sunset time: {sunset_time}")

    if sunrise_time < sunset_time:
        if sunrise_time <= current_time < sunset_time:
            return True
        else:
            return False
    else:
        if current_time >= sunrise_time or current_time < sunset_time:
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
    print(f'Publishing SNS message: {new_state}')
    sns = boto3.client('sns')
    sns_message = {
        "message": new_state
    }
    response = sns.publish(TopicArn=sns_topic_arn, Message=json.dumps(sns_message))
    print(f'Publish SNS response: {response}')

def publish_mqtt_message(new_state, mqtt_topic, iot_endpoint):
    print(f'Publishing MQTT message: {new_state} to topic: {mqtt_topic}')
    mqtt = boto3.client('iot-data', endpoint_url=iot_endpoint)
    mqtt_message = {
        "LED": new_state
    }
    response = mqtt.publish(
        topic=mqtt_topic,
        qos=1,
        payload=json.dumps(mqtt_message)
    )
    print(f'Publish MQTT response: {response}')

def get_led_color(state_str):
    return LED_COLOR_LOOKUP.get(state_str, "LED_FLASHING_RED")

def lambda_handler(event, context):
    print(f"event:\n{event}")

    ddb_state_table_name = os.getenv('DDB_STATE_TABLE_NAME')
    ddb_twilight_table_name = os.getenv('DDB_TWILIGHT_TABLE_NAME')
    sns_topic_arn = os.getenv('SNS_PUBLISH_TOPIC_ARN')
    mqtt_topic = os.getenv('MQTT_PUBLISH_TOPIC')
    iot_endpoint = os.getenv('IOT_ENDPOINT')

    dynamodb = boto3.resource('dynamodb')
    ddb_state_table = dynamodb.Table(ddb_state_table_name)

    print("Received event: " + json.dumps(event, indent=2))
    door_status = event.get('door')
    if not door_status:
        print("No door status received. Exiting.")
        return

    now_daytime = is_daytime(ddb_twilight_table_name)
    print(f"Is it daytime? {now_daytime}")

    new_state = reported_state(door_status, now_daytime)
    print(f"New state: {new_state}")

    current_state = get_ddb_state(ddb_state_table)
    print(f"Current state: {current_state}")

    if new_state != current_state:
        print("State has changed. Updating DDB, publishing SNS and MQTT messages.")
        set_ddb_state(ddb_state_table, new_state)
        publish_sns_message(new_state, sns_topic_arn)
    else:
        print("State has not changed. No action required.")

    led_color = get_led_color(new_state)
    # Publish MQTT message always because the devices need to know the current state
    publish_mqtt_message(led_color, mqtt_topic, iot_endpoint)
