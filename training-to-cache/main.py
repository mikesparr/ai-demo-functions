import os
import time
import base64
import json
import redis

example = """
{
    'job_id': "UUID",
    'model_file_name': "model.joblib",
    'records': 1400,
    'accuracy': 0.98,
    'report': {},
    'data_prep_time': 0.001,
    'training_time': 0.020,
    'testing_time': 0.004
}
"""

jobs_key = 'jobs'
model_key = 'model:latest'
model_accuracy_key = 'model:latest:accuracy'

# initiate redis cache
redis_host = os.environ.get('REDISHOST', 'localhost')
redis_port = int(os.environ.get('REDISPORT', 6379))
redis_client = redis.StrictRedis(host=redis_host, port=redis_port)

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

    print(f"Inserting new model into cache")
    cache_start = time.process_time()

    # update model in case
    # TODO: compare accuracy against current model and only update if better
    redis_client.set(model_key, data['model_file_name'])
    redis_client.set(model_accuracy_key, data['accuracy'])

    # TODO: potentially add report
    job = {
        'job_id': data['job_id'],
        'model_file_name': data['model_file_name'],
        'records': data['records'],
        'accuracy': data['accuracy'],
        'data_prep_time': data['data_prep_time'],
        'training_time': data['training_time'],
        'testing_time': data['testing_time']
    }

    redis_client.lpush(jobs_key, json.dumps(job))

    cache_stop = time.process_time()

    print(f"{'Cache time':25}: {cache_stop-cache_start}")
