import os
import base64
import datetime
import json
import redis
import time

import numpy as np
from joblib import load
from sklearn.svm import SVC

from google.cloud import storage
from google.cloud import pubsub_v1

# Example record published to PubSub
example = """
{
    "data": {         
        "batch_id": "f38b1e92-378d-11eb-adc1-0242ac120002",
        "subjects": ["dollar", "twenty", "yen", "benjamin", "bitcoin"],
        "features": [[-2.16680,1.59330,0.045122,-1.67800],[1,2,3,4],[-2.8833,1.7713,0.68946,-0.4638],[2.8297,6.3485,-0.73546,-0.58665],[5,6,7,8]]     
    }
}
"""

project_id = os.environ.get('PROJECT_ID', 'mike-test-ml-classification1')
topic_id = os.environ.get('TOPIC_ID', 'prediction') # where to publish to ->
bucket_name = os.environ.get('BUCKET', 'mike-test-classification-models1')

model_key = 'model:latest'
model_file = 'model.joblib' # default
next_model_download = datetime.datetime.now()

# initiate pubsub
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(project_id, topic_id)

# initiate storage
storage_client = storage.Client()

# initiate redis cache
redis_host = os.environ.get('REDISHOST', 'localhost')
redis_port = int(os.environ.get('REDISPORT', 6379))
redis_client = redis.StrictRedis(host=redis_host, port=redis_port)
print(f"Cached model file is {str(redis_client.get(model_key), 'utf-8')}")

# helper functions
def fetch_latest_model_from_cache():
     """Checks redis (cache) for latest model file and if different, 
     triggers new model download.
     """

     global model_file # allow updating name outside function
     global next_model_download
     cached_model_file_name = None

     # only fetch newest model if 1 minute has passed since last download
     now = datetime.datetime.now()
     if now <= next_model_download:
          print("It has not been at least 1 minute since last model download. Skipping.")
     else:
          print(f"Checking if newer model file than {model_file}")

          next_model_download = now + datetime.timedelta(minutes = 1)

          try:
               print("Checking cache...")
               cached_model_file_name = str(redis_client.get(model_key), 'utf-8')
               print(cached_model_file_name)
          except Exception as ce:
               print(f"Error fetching cached model {ce}")

          if cached_model_file_name is None:
               print("No cached model file found")
          elif cached_model_file_name == model_file:
               print("Current model matches cached model. Nothing to do.")
          else:
               print(f"Replacing {model_file} with {cached_model_file_name}")
               model_file = cached_model_file_name
               download_object_file(bucket_name, model_file, model_file)

def download_object_file(bucket_name, source_filename='model.joblib', dest_filename='model.joblib'):
     """Downloads file from bucket and saves in /tmp dir.
     Args:
          bucket_name (string): Bucket name.
          source_filename (string): Name of file stored in bucket. [default: model.joblib]
          dest_filename (string): Name of file stored in /tmp dir. [default: model.joblib]
     """

     print(f"Downloading {bucket_name}/{source_filename} to /tmp/{dest_filename}")

     download_start = time.process_time()
     bucket = storage_client.bucket(bucket_name)
     blob = bucket.blob(source_filename)
     blob.download_to_filename(f"/tmp/{dest_filename}")
     download_stop = time.process_time()

     print(f"{'Model download took':25}: {download_stop-download_start}")

def publish_to_topic(message):
     """Publishes messages to a pubsub topic.
     Args:
          message (dict): Message payload.
     """

     print(message)

     publish_start = time.process_time()
     # Data must be a bytestring
     data = json.dumps(message).encode("utf-8")

     # Add attributes to the message
     future = publisher.publish(
          topic_path, data, foo="bar", fizz="buzz"
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

    print(context)
    print(event)
    pubsub_message = base64.b64decode(event['data']).decode('utf-8')
    data = json.loads(pubsub_message)
    print(data)
    features = data['features'] # [[-2.16680,1.59330,0.045122,-1.67800]]

    # load the model
    fetch_latest_model_from_cache()
    print(f"Using model file {model_file}")
    load_start = time.process_time()
    model = load(f"/tmp/{model_file}")
    load_stop = time.process_time()

    # predict
    predict_start = time.process_time()
    result = model.predict(np.array(features)) # should be 2D array, else .reshape(1, -1)
    predict_stop = time.process_time()

    prediction = ['real' if val == 1 else 'fake' for val in result]

    print()
    print(f"{'Result':25}: {prediction}")
    print(f"{'Model loading took':25}: {load_stop-load_start}")
    print(f"{'Prediction took':25}: {predict_stop-predict_start}")

    # create result object
    response = {
         'batch_id': data['batch_id'],
         'subjects': data['subjects'],
         'input': features,
         'output': prediction
    }

    # publish to message topic
    publish_to_topic(response)
