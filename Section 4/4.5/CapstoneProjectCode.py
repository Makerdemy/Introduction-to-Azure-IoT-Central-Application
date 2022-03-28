import os
import asyncio
import random
import logging
import json
import pdb

import adafruit_dht
from board import *
from gpiozero import Buzzer
from gpiozero import OutputDevice
from time import sleep

from azure.iot.device.aio import IoTHubDeviceClient
from azure.iot.device.aio import ProvisioningDeviceClient
from azure.iot.device import MethodResponse
from datetime import timedelta, datetime
import pnp_helper

logging.basicConfig(level=logging.ERROR)

model_id = "dtmi:com:example:TemperatureController;2"

SENSOR_PIN = D4

buzzer = Buzzer(17)

relay = OutputDevice(22)

relay.on()

dht22 = adafruit_dht.DHT11(SENSOR_PIN, use_pulseio=False)

async def buzzer_handler():
    buzzer.on()
    sleep(1)
    buzzer.off()
    sleep(1)
    print("BUZZER BLOWN")


async def send_telemetry_from_temp_controller(device_client, telemetry_msg, component_name=None):
    msg = pnp_helper.create_telemetry(telemetry_msg, component_name)
    await device_client.send_message(msg)
    print("Sent message")
    print(msg)


async def execute_command_listener(
    device_client,
    component_name=None,
    method_name="blowbuzzer",
    user_command_handler=buzzer_handler,
    create_user_response_handler=None,
):
    while True:
        if component_name and method_name:
            command_name = component_name + "*" + method_name
        elif method_name:
            command_name = method_name
        else:
            command_name = None

        command_request = await device_client.receive_method_request(command_name)
    
        if user_command_handler:
            await user_command_handler()
        else:
            print("No handler provided to execute")

        (response_status, response_payload) = pnp_helper.create_response_payload_with_status(
            command_request, method_name, create_user_response=create_user_response_handler
        )

        command_response = MethodResponse.create_from_method_request(
            command_request, response_status, response_payload
        )

        try:
            await device_client.send_method_response(command_response)
        except Exception:
            print("responding to the {command} command failed".format(command=method_name))


async def execute_property_listener(device_client):
    while True:
        patch = await device_client.receive_twin_desired_properties_patch()  # blocking call
        print("\n Value of PATCH :", patch)

        if patch["bulbSWITCH"] == 1:
            print("ON")
            relay.off()
        elif patch["bulbSWITCH"] == 0:
            print("OFF")
            relay.on()


def stdin_listener():
    while True:
        selection = input("Press Q to quit\n")
        if selection == "Q" or selection == "q":
            print("Quitting...")
            break


async def main():
    conn_str = "Paste Your connection string here"
    print("Connecting using Connection String " + conn_str)
    device_client = IoTHubDeviceClient.create_from_connection_string(
            conn_str, product_info=model_id
        )
   
    # Connect the client.
    await device_client.connect()

    print("Listening for command requests and property updates")


    listeners = asyncio.gather(
        execute_command_listener(
            device_client, method_name="blowbuzzer", user_command_handler=buzzer_handler
        ),
        execute_property_listener(device_client),
    )

    async def send_telemetry():
        print("Sending telemetry from various components")

        while True:
           temperature = dht22.temperature
           temperature_msg1 = {"temperature": temperature}
           await send_telemetry_from_temp_controller(device_client, temperature_msg1)
           humidity = dht22.humidity
           humidity_msg2 = {"humidity": humidity}
           await send_telemetry_from_temp_controller(device_client, humidity_msg2)

    send_telemetry_task = asyncio.ensure_future(send_telemetry())

    # Run the stdin listener in the event loop
    loop = asyncio.get_running_loop()
    user_finished = loop.run_in_executor(None, stdin_listener)
    # # Wait for user to indicate they are done listening for method calls
    await user_finished

    if not listeners.done():
        listeners.set_result("DONE")

    listeners.cancel()

    send_telemetry_task.cancel()

    # Finally, shut down the client
    await device_client.shutdown()


if __name__ == "__main__":
    asyncio.run(main())