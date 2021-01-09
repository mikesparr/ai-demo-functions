import os
import time
import datetime
import base64
import json
import redis

batch_key = 'batches' # TODO: consider env var

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

    subjects = data['subjects']
    inputs = data['input']
    outputs = data['output']
    batch_id = data['batch_id']

    print(f"Inserting {len(subjects)} predictions into cache")
    cache_start = time.process_time()

    row = {
        'batch_id': batch_id,
        'subjects': subjects,
        'predictions': outputs,
        'created': datetime.datetime.utcnow().isoformat()
    }

    redis_client.lpush(batch_key, json.dumps(row))

    cache_stop = time.process_time()

    print(f"{'Cache time':25}: {cache_stop-cache_start}")
