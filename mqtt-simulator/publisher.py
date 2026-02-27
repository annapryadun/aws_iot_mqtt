import json
import ssl
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion, MQTTProtocolVersion
from settings_classes import BrokerSettings, ClientSettings, DataSettings


class Publisher(threading.Thread):
    def __init__(
        self,
        broker_settings: BrokerSettings,
        topic_url: str,
        topic_data: list[DataSettings],
        topic_payload_root: dict[str, Any],
        client_settings: ClientSettings,
        is_verbose: bool,
    ):
        threading.Thread.__init__(self)

        self.broker_settings = broker_settings
        self.topic_url = topic_url
        self.topic_data = topic_data
        self.topic_payload_root = topic_payload_root
        self.client_settings = client_settings
        self.is_verbose = is_verbose

        self.loop = False
        self.payload: dict[str, Any] | None = None
        self.client = self.create_client()

    def create_client(self) -> mqtt.Client:
        clean_session = None if self.broker_settings.protocol == mqtt.MQTTv5 else self.client_settings.clean_session
        client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            protocol=MQTTProtocolVersion(self.broker_settings.protocol),
            client_id=self.topic_url.replace("/", "-"),
            clean_session=clean_session,
        )
        client.on_publish = self.on_publish
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect
        if self.broker_settings.is_tls_enabled():
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_cert_chain(self.broker_settings.tls_cert_path, self.broker_settings.tls_key_path)
            context.load_verify_locations(self.broker_settings.tls_ca_path)
            client.tls_set_context(context)
        if self.broker_settings.is_auth_enabled():
            client.username_pw_set(
                username=self.broker_settings.auth_username,
                password=self.broker_settings.auth_password,
            )
        return client

    def connect(self):
        self.client.connect(self.broker_settings.url, self.broker_settings.port)
        self.client.loop_start()

    def run(self):
        self.loop = True
        self.start_publish_loop()

    def stop(self):
        self.loop = False
        self.client.loop_stop()
        self.client.disconnect()

    def start_publish_loop(self):
        while self.loop:
            self.payload = self.generate_payload()
            self.client.publish(
                topic=self.topic_url,
                payload=json.dumps(self.payload),
                qos=self.client_settings.qos,
                retain=self.client_settings.retain,
            )
            time.sleep(self.client_settings.time_interval)

    def generate_payload(self) -> dict[str, Any] | None:
        payload: dict[str, Any] = {}
        payload.update(self.topic_payload_root)
        has_data_active = False
        for data in self.topic_data:
            if data.get_is_active():
                has_data_active = True
                payload[data.name] = data.generate_value()
        if not has_data_active:
            self.stop()
            return None
        return payload

    def on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"[{time.strftime('%H:%M:%S')}] {self.topic_url} connected: {reason_code}")

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        print(f"[{time.strftime('%H:%M:%S')}] {self.topic_url} disconnected: {reason_code}")

    def on_publish(self, client, userdata, mid, reason_code, properties):
        on_publish_log = f"[{time.strftime('%H:%M:%S')}] Data published on: {self.topic_url}"
        if self.is_verbose:
            on_publish_log += f"\n\t[payload] {json.dumps(self.payload)}"
        print(on_publish_log)
