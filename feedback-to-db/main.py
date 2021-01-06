import os
import time
import json
import base64
import psycopg2

from google.cloud import pubsub_v1
from google.cloud import secretmanager

# Example record published to PubSub
example = """
{
    "data": {
        "batch_id": "1cfa5d88-3752-11eb-adc1-0242ac120002",
        "subjects": ["twenty", "dollar"],
        "ratings": [1,0]
    }
}
"""

project_id = os.environ.get('PROJECT_ID', 'mike-test-ml-classification1')
topic_id = os.environ.get('TOPIC_ID', 'training') # where to publish to ->
db_pass_key = 'db-pass'

# initiate secret store client
client = secretmanager.SecretManagerServiceClient()
request = {"name": f"projects/{project_id}/secrets/{db_pass_key}/versions/latest"}
response = client.access_secret_version(request)
db_pass = response.payload.data.decode("UTF-8")

# initiate pubsub client
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(project_id, topic_id)

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

# helper functions
def publish_to_topic(message):
     """Publishes messages to a pubsub topic.
     Args:
          topic (string): Topic name.
          message (dict): Message payload.
     """

     print(message)

     publish_start = time.process_time()
     # Data must be a bytestring
     encoded_message = json.dumps(message).encode("utf-8")

     # Add attributes to the message
     future = publisher.publish(
          topic_path, encoded_message, foo="bar", fizz="buzz"
     )
     publish_stop = time.process_time()
     print(future.result())

     print(f"Published message to {topic_path}.")
     print(f"{'Message publishing took':25}: {publish_stop-publish_start}")

# process
def process(event, context):
    """Triggered from a message on a Cloud Pub/Sub topic.
    Args:
         event (dict): Event payload.
         context (google.cloud.functions.Context): Metadata for the event.
    """

    # extract data from message
    print(context)
    print(event)
    pubsub_message = base64.b64decode(event['data']).decode('utf-8')
    data = json.loads(pubsub_message)
    print(data)

    batch_id = data['batch_id']
    subjects = data['subjects']
    ratings = data['ratings']

    print(f"Updating {len(subjects)} predictions in database")
    db_start = time.process_time()
    # loop through subjects and insert record each

    for i, subject in enumerate(subjects):
        print(f"Inserting subject {subject} for row {i}")
        rating = ratings[i]

        query = "UPDATE predictions SET is_correct = %s WHERE batch_id = %s AND subject_id = %s"
        values = (True if rating == 1 else False, batch_id, subject)
        print(f"Inserting {values} record")

        # insert record
        try:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    values,
                )
                print(f"update(): status message: {cur.statusmessage}")
        except (Exception, psycopg2.Error) as error:
            message = f"Error while inserting record in database {error}"
            print(message)

    conn.commit()
    db_stop = time.process_time()

    print(f"{'DB time':25}: {db_stop-db_start}")

    # if any results corrected, publish to message topic to kick of retraining
    print("Triggering retraining job")
    publish_to_topic(data)
