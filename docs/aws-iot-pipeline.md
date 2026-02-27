# AWS IoT Pipeline: From MQTT Simulator to Machine Learning

This guide walks you through setting up a full AWS IoT data pipeline using the MQTT simulator as the data source. All steps are performed in the AWS Console (eu-central-1 / Frankfurt).

## Architecture Overview

```
MQTT Simulator
  → AWS IoT Core (MQTT broker)
    → IoT Rule #1 → S3 (raw data lake)
    → IoT Rule #2 → Amazon Timestream (time-series DB)
    → IoT Rule #3 → Lambda → DynamoDB (alerts)
    → IoT Analytics (clean, enrich, query)
    → SageMaker (ML: anomaly detection, forecasting)
```

## Prerequisites

- MQTT Simulator connected to AWS IoT Core (see [settings-aws.json](../config/settings-aws.json))
- AWS account with IoT Core Thing + certificate configured
- Region: **eu-central-1** (Frankfurt)

---

## Step 1: Create an S3 Bucket (Raw Data Lake)

This stores every MQTT message as a JSON file for long-term storage and ML training.

1. Go to **S3** → **Create bucket**
2. Bucket name: `iot-simulator-data-<your-account-id>`
3. Region: **eu-central-1**
4. Leave defaults → **Create bucket**
5. Inside the bucket, create a folder: `raw/`

---

## Step 2: Create an IAM Role for IoT Rules

IoT Rules need permission to write to S3, Timestream, Lambda, etc.

1. Go to **IAM** → **Roles** → **Create role**
2. Trusted entity: **AWS service**
3. Use case: **IoT**
4. Click **Next**
5. Attach these policies:
   - `AmazonS3FullAccess`
   - `AmazonTimestreamFullAccess`
   - `AWSLambda_FullAccess`
   - `AmazonDynamoDBFullAccess`
6. Role name: `IoT_Rule_Role`
7. **Create role**
8. Copy the **Role ARN** — you'll need it for each IoT Rule

---

## Step 3: IoT Rule #1 — Store All Messages in S3

1. Go to **AWS IoT** → **Message routing** → **Rules** → **Create rule**
2. Rule name: `store_all_to_s3`
3. SQL statement:
   ```sql
   SELECT *, topic() AS topic, timestamp() AS ts FROM '#'
   ```
   This captures all messages from all topics and adds the topic name and timestamp.
4. **Rule actions** → **Add action** → **S3**
   - Bucket: `iot-simulator-data-<your-account-id>`
   - Key: `raw/${topic()}/${timestamp()}.json`
   - IAM Role: select `IoT_Rule_Role`
5. **Create rule**

**Verify:** Run the simulator, then check S3. You should see JSON files appearing under `raw/lamp/1/`, `raw/air_quality/`, etc.

---

## Step 4: Create Amazon Timestream Database

Timestream is a serverless time-series database — ideal for IoT sensor data, dashboards, and queries.

1. Go to **Amazon Timestream** → **Databases** → **Create database**
2. Database name: `iot_simulator_db`
3. Choose **Standard database**
4. **Create database**
5. Inside the database → **Tables** → **Create table**
6. Table name: `sensor_data`
7. Memory store retention: **1 day** (hot data)
8. Magnetic store retention: **30 days** (warm data)
9. **Create table**

---

## Step 5: IoT Rule #2 — Route Temperature Data to Timestream

1. Go to **AWS IoT** → **Message routing** → **Rules** → **Create rule**
2. Rule name: `temperature_to_timestream`
3. SQL statement:
   ```sql
   SELECT temperature, topic() AS topic FROM '#' WHERE temperature IS NOT NULL
   ```
4. **Rule actions** → **Add action** → **Timestream table**
   - Database: `iot_simulator_db`
   - Table: `sensor_data`
   - Dimensions:
     - Name: `device` / Value: `${topic()}`
   - Timestamp: `${timestamp()}` (milliseconds)
   - IAM Role: select `IoT_Rule_Role`
5. **Create rule**

**Query example** (Timestream → Query editor):
```sql
SELECT device, time, measure_value::double AS temperature
FROM "iot_simulator_db"."sensor_data"
WHERE time > ago(1h)
ORDER BY time DESC
LIMIT 100
```

---

## Step 6: Create DynamoDB Table for Alerts

1. Go to **DynamoDB** → **Create table**
2. Table name: `iot_alerts`
3. Partition key: `alert_id` (String)
4. Sort key: `timestamp` (Number)
5. Leave defaults → **Create table**

---

## Step 7: Create Lambda Function for Alert Processing

This function checks conditions (e.g., air quality alert = true) and writes to DynamoDB.

1. Go to **Lambda** → **Create function**
2. Function name: `iot_alert_processor`
3. Runtime: **Python 3.12**
4. Execution role: **Create a new role with basic Lambda permissions**
5. **Create function**
6. Replace the code with:

```python
import json
import boto3
import uuid
import time

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('iot_alerts')

def lambda_handler(event, context):
    print(f"Received event: {json.dumps(event)}")

    alert_item = {
        'alert_id': str(uuid.uuid4()),
        'timestamp': int(time.time() * 1000),
        'topic': event.get('topic', 'unknown'),
        'payload': json.dumps(event),
        'alert_type': 'air_quality_alert'
    }

    table.put_item(Item=alert_item)

    return {
        'statusCode': 200,
        'body': json.dumps('Alert stored')
    }
```

7. Click **Deploy**
8. Go to **Configuration** → **Permissions** → click the role name
9. Attach policy: `AmazonDynamoDBFullAccess`

---

## Step 8: IoT Rule #3 — Trigger Lambda on Air Quality Alerts

1. Go to **AWS IoT** → **Message routing** → **Rules** → **Create rule**
2. Rule name: `air_quality_alerts`
3. SQL statement:
   ```sql
   SELECT *, topic() AS topic, timestamp() AS ts FROM 'air_quality' WHERE alert = true
   ```
4. **Rule actions** → **Add action** → **Lambda**
   - Function: `iot_alert_processor`
5. **Create rule**

**Verify:** Run the simulator. When `air_quality` publishes `"alert": true`, check the `iot_alerts` DynamoDB table for new entries.

---

## Step 9: Set Up IoT Analytics

IoT Analytics provides a managed pipeline to clean, transform, store, and query IoT data — plus built-in integration with SageMaker notebooks.

### 9a. Create a Channel (data ingestion)

1. Go to **IoT Analytics** → **Channels** → **Create channel**
2. Channel name: `iot_simulator_channel`
3. Storage: **Service-managed**
4. Retention: **30 days**
5. **Create channel**

### 9b. Create a Datastore (processed data)

1. Go to **Datastores** → **Create datastore**
2. Datastore name: `iot_simulator_datastore`
3. Storage: **Service-managed**
4. Retention: **30 days**
5. **Create datastore**

### 9c. Create a Pipeline (transforms)

1. Go to **Pipelines** → **Create pipeline**
2. Pipeline name: `iot_simulator_pipeline`
3. Source: `iot_simulator_channel`
4. Add activity: **Add attributes from message** (adds `topic` from `topic()`)
5. Output: `iot_simulator_datastore`
6. **Create pipeline**

### 9d. Create an IoT Rule to Feed the Channel

1. Go to **AWS IoT** → **Message routing** → **Rules** → **Create rule**
2. Rule name: `send_to_analytics`
3. SQL statement:
   ```sql
   SELECT *, topic() AS topic, timestamp() AS ts FROM '#'
   ```
4. **Rule actions** → **Add action** → **IoT Analytics**
   - Channel: `iot_simulator_channel`
5. **Create rule**

### 9e. Create a Dataset (query results)

1. Go to **IoT Analytics** → **Datasets** → **Create dataset**
2. Choose **SQL dataset**
3. Dataset name: `iot_simulator_dataset`
4. SQL query:
   ```sql
   SELECT * FROM "iot_simulator_datastore"
   ```
5. Schedule: **Not scheduled** (run manually for now)
6. **Create dataset** → **Run now**

---

## Step 10: SageMaker — Anomaly Detection on IoT Data

### Option A: Quick Start with IoT Analytics Notebook

1. In **IoT Analytics** → **Notebooks** → **Create notebook**
2. Choose a SageMaker notebook instance (or create one)
3. Select the **anomaly detection** template
4. This gives you a pre-configured Jupyter notebook with your IoT Analytics dataset

### Option B: SageMaker Studio with S3 Data

1. Go to **SageMaker** → **Studio** → **Open Studio**
2. Create a new Jupyter notebook
3. Load data from S3:

```python
import boto3
import pandas as pd
import json

s3 = boto3.client('s3')
bucket = 'iot-simulator-data-<your-account-id>'

# List and load raw JSON files
objects = s3.list_objects_v2(Bucket=bucket, Prefix='raw/')
data = []
for obj in objects.get('Contents', []):
    response = s3.get_object(Bucket=bucket, Key=obj['Key'])
    payload = json.loads(response['Body'].read())
    data.append(payload)

df = pd.DataFrame(data)
print(df.head())
```

4. Example: anomaly detection on temperature data:

```python
from sklearn.ensemble import IsolationForest

# Filter temperature readings
temp_df = df[df['temperature'].notna()][['temperature', 'ts']].copy()
temp_df['ts'] = pd.to_datetime(temp_df['ts'], unit='ms')

# Train anomaly detection model
model = IsolationForest(contamination=0.05, random_state=42)
temp_df['anomaly'] = model.fit_predict(temp_df[['temperature']])

# anomaly = -1 means outlier
anomalies = temp_df[temp_df['anomaly'] == -1]
print(f"Found {len(anomalies)} anomalies out of {len(temp_df)} readings")
```

---

## Step 11: CloudWatch Monitoring

IoT Core automatically publishes metrics. Set up alarms for operational monitoring:

1. Go to **CloudWatch** → **Alarms** → **Create alarm**
2. Select metric: **IoT** → **Protocol Metrics**
   - `PublishIn.Success` — messages received by IoT Core
   - `Connect.Success` — successful device connections
3. Set threshold (e.g., alarm if `PublishIn.Success` < 1 for 5 minutes — means devices stopped sending)
4. Notification: create an SNS topic to receive email alerts

---

## Summary of AWS Services Used

| Service | Purpose | IoT Rule |
|---------|---------|----------|
| **IoT Core** | MQTT broker, message routing | - |
| **S3** | Raw data lake for ML training | `store_all_to_s3` |
| **Timestream** | Time-series queries and dashboards | `temperature_to_timestream` |
| **Lambda** | Custom alert processing | `air_quality_alerts` |
| **DynamoDB** | Alert storage | via Lambda |
| **IoT Analytics** | Data pipeline + SageMaker integration | `send_to_analytics` |
| **SageMaker** | ML: anomaly detection, forecasting | reads from S3 / IoT Analytics |
| **CloudWatch** | Monitoring and alarms | automatic |
| **IAM** | Permissions for IoT rules | `IoT_Rule_Role` |

---

## Cost Considerations

Most services have a **free tier**:
- **IoT Core**: 250,000 messages/month free (first 12 months)
- **S3**: 5 GB free
- **Lambda**: 1M requests/month free
- **DynamoDB**: 25 GB free
- **Timestream**: 50 GB writes, 10 GB queries free (first 12 months)
- **IoT Analytics**: 100 MB processed free

For a simulator running 7 topics at 4-8 second intervals, you'll stay well within free tier limits.

---

## Running the Simulator

```bash
# Default (HiveMQ public broker)
python3 mqtt-simulator/main.py -v

# AWS IoT Core
python3 mqtt-simulator/main.py -f config/settings-aws.json -v
```
