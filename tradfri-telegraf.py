#!/usr/env/python3
import os
import uuid
import json
import asyncio
import logging
from functools import partial
from pytradfri import Gateway
from pytradfri.api.aiocoap_api import APIFactory
from pytradfri.error import PytradfriError
from telegraf.client import TelegrafClient

CONFIG_FILE = 'config.json'

def load_env():
    return {
        'gateway': os.environ.get('GATEWAY'),
        'key': os.environ.get('KEY'),
        'telegraf_host': os.environ.get('TELEGRAF_HOST'),
        'telegraf_port': int(os.environ.get('TELEGRAF_PORT')),
        'telegraf_metric': os.environ.get('TELEGRAF_METRIC', 'tradfri_level'),
    }

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_config(conf):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(conf, f)

async def initialize_api_connection(host, key):
    identity = uuid.uuid4().hex
    api_factory = APIFactory(host=host, psk_id=identity)
    psk =  await api_factory.generate_psk(key)
    logging.info('Generated PSK')

    conf = load_config()
    conf[host] =  {
        'identity': identity,
        'key': psk
    }
    save_config(conf)
    return api_factory

async def load_api(host, key):
    conf = load_config()
    if host in conf:
        logging.info('PSK from config file')
        identity = conf[host].get('identity')
        psk = conf[host].get('key')
        return APIFactory(host=host, psk_id=identity, psk=psk)
    else:
        return await initialize_api_connection(host, key)

def err_callback(err):
    logging.error(err)

def change_listener(client, metric, device):
    dimmer = device.light_control.lights[0].dimmer
    state = device.light_control.lights[0].state
    level = dimmer if state else 0
    logging.debug('%s is now %i' % (device.name, level))
    client.metric(metric, level, tags={'light': device.name})

def initialize_telegraf(cfg):
    return TelegrafClient(
            host=cfg['telegraf_host'],
            port=cfg['telegraf_port'])

async def main():
    envs = load_env()
    gateway = envs.get('gateway')
    key = envs.get('key')
    api_factory = await load_api(gateway, key)
    api = api_factory.request
    client = initialize_telegraf(envs)

    gateway = Gateway()
    devices_command = gateway.get_devices()
    devices_commands = await api(devices_command)
    devices = await api(devices_commands)

    lights = [dev for dev in devices if dev.has_light_control]

    change_f = partial(change_listener, client, envs['telegraf_metric'])
    for light in lights:
        observe_command = light.observe(change_f, err_callback, duration=0)
        # Write init value
        change_f(light)
        asyncio.ensure_future(api(observe_command))
        await asyncio.sleep(0)

    return api_factory

async def close_api(api_factory):
    await api_factory.shutdown()

if __name__ == '__main__':
    LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()
    logging.basicConfig(level=LOGLEVEL)
    loop = asyncio.get_event_loop()
    try:
        api_factory = asyncio.ensure_future(main())
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        logging.info('Close API')
        loop.run_until_complete(close_api(api_factory.result()))
        logging.info('Close loop')
        loop.close()
