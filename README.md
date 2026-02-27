# AWS IoT MQTT Pipeline

An AWS IoT data pipeline using the [MQTT Simulator](https://github.com/DamascenoRafael/mqtt-simulator) to publish simulated IoT device data to AWS IoT Core, with routing to S3, Timestream, Lambda, DynamoDB, IoT Analytics, and SageMaker.

## Architecture

```
MQTT Simulator → AWS IoT Core
                   ├→ S3 (raw data lake)
                   ├→ Amazon Timestream (time-series queries)
                   ├→ Lambda → DynamoDB (alerts)
                   ├→ IoT Analytics → SageMaker (ML)
                   └→ CloudWatch (monitoring)
```

## Getting Started

### 1. Install dependencies

```shell
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
```

### 2. Run with public broker (HiveMQ)

```shell
python3 mqtt-simulator/main.py -v
```

### 3. Run with AWS IoT Core

Place your AWS IoT certificates in `certs/` and run:

```shell
python3 mqtt-simulator/main.py -f config/settings-aws.json -v
```

See [AWS IoT Pipeline Guide](docs/aws-iot-pipeline.md) for step-by-step instructions on setting up the full pipeline.

## Configuration

- `config/settings.json` — default config (public HiveMQ broker)
- `config/settings-aws.json` — AWS IoT Core config (TLS mutual auth, QoS 1)

See the [configuration documentation](docs/configuration.md) for all available settings.

## AWS IoT Pipeline Documentation

The [AWS IoT Pipeline Guide](docs/aws-iot-pipeline.md) covers setting up:

1. **S3** — raw data lake for ML training
2. **Amazon Timestream** — time-series database for sensor queries
3. **Lambda + DynamoDB** — real-time alert processing
4. **IoT Analytics** — managed data pipeline with SageMaker integration
5. **SageMaker** — anomaly detection and forecasting
6. **CloudWatch** — monitoring and alarms

## Credits

MQTT Simulator by [DamascenoRafael/mqtt-simulator](https://github.com/DamascenoRafael/mqtt-simulator)
