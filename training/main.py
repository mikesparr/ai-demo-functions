import os
import time
import json
import base64
import psycopg2
import uuid

import pandas as pd
import numpy as np
from joblib import dump
from sklearn.model_selection import train_test_split
from sklearn.svm import SVC
from sklearn.metrics import classification_report, confusion_matrix

from google.cloud import storage
from google.cloud import pubsub_v1
from google.cloud import secretmanager

# Example record published to PubSub
example = """
{
    "data": {
        "batch_id": "7c9b80e0-3762-11eb-adc1-0242ac120002",
        "orig_batch_id": "1cfa5d88-3752-11eb-adc1-0242ac120002",
        "subjects": ["twenty", "dollar"],
        "ratings": [1,0]
    }
}
"""

project_id = os.environ.get('PROJECT_ID', 'mike-test-ml-classification1')
topic_id = os.environ.get('TOPIC_ID', 'model') # where to publish to ->
bucket_name = os.environ.get('BUCKET', 'mike-test-classification-models1')
db_pass_key = 'db-pass'

# initiate secret store client
client = secretmanager.SecretManagerServiceClient()
request = {"name": f"projects/{project_id}/secrets/{db_pass_key}/versions/latest"}
response = client.access_secret_version(request)
db_pass = response.payload.data.decode("UTF-8")

# initialize cloud storage
storage_client = storage.Client()
bucket = storage_client.bucket(bucket_name)

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
def upload_blob(source_file_name, destination_blob_name):
    """Uploads a file to the bucket."""
    # source_file_name = "local/path/to/file"
    # destination_blob_name = "storage-object-name"

    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(source_file_name)

    print(
        "File {} uploaded to {}.".format(
            source_file_name, destination_blob_name
        )
    )

def publish_to_topic(message):
     """Publishes messages to a pubsub topic.
     Args:
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
    pubsub_message = base64.b64decode(event['data']).decode('utf-8')
    print(pubsub_message)

    # fetch training set from db
    print(f"Fetching training set from database")
    db_start = time.process_time()

    # fetch balanced amount of rows for both classes and de-duplicate based on feature columns
    query = """
    WITH l AS
        (
            SELECT one_count, two_count, LEAST(one_count, two_count) as max_per_class 
            FROM
                (
                    SELECT COUNT(1) as one_count FROM training WHERE class = 1
                ) as derivedTable1,
                (
                    SELECT COUNT(1) as two_count FROM training WHERE class = 0
                ) as derivedTable2
        )
    (
        SELECT variance, skewness, curtosis, entropy, class 
        FROM training WHERE class = 0 
        GROUP BY variance, skewness, curtosis, entropy, class 
        LIMIT (SELECT max_per_class FROM l)
    )
    UNION ALL
    (
        SELECT variance, skewness, curtosis, entropy, class 
        FROM training WHERE class = 1 
        GROUP BY variance, skewness, curtosis, entropy, class 
        LIMIT (SELECT max_per_class FROM l)
    )
    """

    # fetch records
    try:
        with conn.cursor() as cur:
            cur.execute(
                query,
            )
            print(f"select(): status message: {cur.statusmessage}")
            rows = cur.fetchall()
            print(f"Found {len(rows)} records in training set")

    except (Exception, psycopg2.Error) as error:
        message = f"Error while fetching training set {error}"
        print(message)

    conn.commit()
    db_stop = time.process_time()

    # prepare data
    prep_start = time.process_time()
    bankdata = pd.DataFrame(rows, columns = ['Variance', 'Skewness', 'Curtosis', 'Entropy', 'Class'])
    X = bankdata.drop('Class', axis=1)  # X = features
    y = bankdata['Class']               # y = target (label)

    # divide into training and testing
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20)
    prep_stop = time.process_time()

    # fit data
    train_start = time.process_time()
    job_id = uuid.uuid1().hex
    print("Training model")
    svclassifier = SVC(kernel='linear')
    svclassifier.fit(X_train, y_train)
    train_stop = time.process_time()

    # analyze results
    test_start = time.process_time()
    print("Testing prediction")
    prediction = svclassifier.predict(X_test)
    print(prediction)
    report = classification_report(y_test, prediction, output_dict=True)
    print(f"Accuracy was {report['accuracy']}")
    test_stop = time.process_time()

    # download model to /tmp
    model_file_name = f"model-{int(time.time())}.joblib"
    model_path = f"/tmp/{model_file_name}"
    dump(svclassifier, model_path)

    # save versioned model to bucket
    upload_blob(model_path, model_file_name)

    # publish new model to message for caching
    response = {
        'job_id': job_id,
        'model_file_name': model_file_name,
        'records': len(rows),
        'accuracy': report['accuracy'],
        'report': report,
        'data_prep_time': prep_stop-prep_start,
        'training_time': train_stop-train_start,
        'testing_time': test_stop-test_start
    }
    publish_to_topic(response)
