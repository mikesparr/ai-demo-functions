import os
import time
import json
import base64
import psycopg2

from google.cloud import secretmanager

project_id = os.environ.get('PROJECT_ID', 'mike-test-ml-classification1')
db_pass_key = 'db-pass'

# initiate secret store client
client = secretmanager.SecretManagerServiceClient()
request = {"name": f"projects/{project_id}/secrets/{db_pass_key}/versions/latest"}
response = client.access_secret_version(request)
db_pass = response.payload.data.decode("UTF-8")

# connect to database
print(f"Connecting to the database")
conn = None
conn = psycopg2.connect(
     database=os.environ.get('DBNAME', 'bank_data'),
     user=os.environ.get('DBUSER', 'ml_readwrite'),
     host=os.environ.get('DBHOST', 'localhost'),
     password=db_pass,
     port=os.environ.get('DBPORT', '5432')
)
print(conn.dsn)

# process
def process(event, context):
    """Triggered from a message on a Cloud Pub/Sub topic.
    Args:
         event (dict): Event payload.
         context (google.cloud.functions.Context): Metadata for the event.
    """
    print(context)
    print(event)
    pubsub_message = base64.b64decode(event['data']).decode('utf-8')
    data = json.loads(pubsub_message)
    print(data)
    subjects = data['subjects']
    inputs = data['input']
    outputs = data['output']
    batch_id = data['batch_id']

    print(f"Inserting {len(subjects)} predictions into database")
    db_start = time.process_time()
    # loop through subjects and insert record each

    for i, subject in enumerate(subjects):
        print(f"Inserting subject {subject} for row {i}")
        features = inputs[i]
        prediction = outputs[i]

        query = "INSERT INTO predictions (batch_id, subject_id, variance, skewness, curtosis, entropy, prediction) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        data = (batch_id, subject, features[0], features[1], features[2], features[3], prediction)
        print(f"Inserting {data} record")

        # insert record
        try:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    data,
                )
                print(f"insert(): status message: {cur.statusmessage}")
        except (Exception, psycopg2.Error) as error:
            message = f"Error while inserting record in database {error}"
            print(message)

    conn.commit()
    db_stop = time.process_time()

    print(f"{'DB time':25}: {db_stop-db_start}")
