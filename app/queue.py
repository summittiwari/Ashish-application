import os
from celery import Celery
from .config import JOB_TIMEOUT
celery=Celery('sentinel',broker=os.getenv('REDIS_URL','redis://redis:6379/0'))
celery.conf.update(task_acks_late=True,task_reject_on_worker_lost=True,worker_prefetch_multiplier=1,broker_transport_options={'visibility_timeout':JOB_TIMEOUT+600},task_soft_time_limit=JOB_TIMEOUT+30,task_time_limit=JOB_TIMEOUT+60)
celery.conf.beat_schedule={'retention-hourly':{'task':'sentinel.retention','schedule':3600.0}}
@celery.task(name='sentinel.compare')
def compare(job):
    from .worker import execute
    execute(job)

@celery.task(name='sentinel.retention')
def retention():
    from .maintenance import cleanup
    try:return cleanup(apply=True)
    except BlockingIOError:return {'skipped':'Another retention sweep is active'}
