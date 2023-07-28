from flask import Flask, Response
from prometheus_client import Gauge, generate_latest
import boto3
from datetime import datetime, timedelta
import time, os
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

QUERY_PERIOD = os.getenv('QUERY_PERIOD', "1800")
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')  # Change 'us-west-2' to your desired region

app = Flask(__name__)
CONTENT_TYPE_LATEST = str('text/plain; version=0.0.4; charset=utf-8')
session = boto3.Session(
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

if os.environ.get('METRIC_COST_LAST_MONTH') is not None:
    g_cost_last_month = Gauge('aws_cost_last_month', 'Cost from AWS for last month')

if os.environ.get('METRIC_COST_THIS_MONTH') is not None:
    g_cost_this_month = Gauge('aws_cost_this_month', 'Cost from AWS for this month')

if os.environ.get('METRIC_COST_BEFORE_LAST_MONTH') is not None:
    g_cost_before_last_month = Gauge('aws_cost_before_last_month', 'Cost from AWS for the month before last month')

scheduler = BackgroundScheduler()

def aws_query():
    print("Calculating costs...")
    now = datetime.now()
    last_month_start = datetime(now.year, now.month - 1, 1)
    this_month_start = datetime(now.year, now.month, 1)
    before_last_month_start = datetime(now.year, now.month - 2, 1)

    ce_client = session.client('ce')

    if os.environ.get('METRIC_COST_LAST_MONTH') is not None:
        r = ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': last_month_start.strftime("%Y-%m-%d"),
                'End':  this_month_start.strftime("%Y-%m-%d")
            },
            Granularity="MONTHLY",
            Metrics=["BlendedCost"]
        )
        cost_last_month = r["ResultsByTime"][0]["Total"]["BlendedCost"]["Amount"]
        print("Cost from last month: %s" % cost_last_month)
        g_cost_last_month.set(float(cost_last_month))

    if os.environ.get('METRIC_COST_THIS_MONTH') is not None:
        r = ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': this_month_start.strftime("%Y-%m-%d"),
                'End':  now.strftime("%Y-%m-%d")
            },
            Granularity="MONTHLY",
            Metrics=["BlendedCost"]
        )
        cost_this_month = r["ResultsByTime"][0]["Total"]["BlendedCost"]["Amount"]
        print("Cost for this month: %s" % cost_this_month)
        g_cost_this_month.set(float(cost_this_month))

    if os.environ.get('METRIC_COST_BEFORE_LAST_MONTH') is not None:
        r = ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': before_last_month_start.strftime("%Y-%m-%d"),
                'End':  last_month_start.strftime("%Y-%m-%d")
            },
            Granularity="MONTHLY",
            Metrics=["BlendedCost"]
        )
        cost_before_last_month = r["ResultsByTime"][0]["Total"]["BlendedCost"]["Amount"]
        print("Cost for the month before last month: %s" % cost_before_last_month)
        g_cost_before_last_month.set(float(cost_before_last_month))

    print("Finished calculating costs")
    return 0

@app.route('/metrics/')
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

@app.route('/health')
def health():
    return "OK"

scheduler.start()
scheduler.add_job(
    func=aws_query,
    trigger=IntervalTrigger(seconds=int(QUERY_PERIOD),start_date=(datetime.now() + timedelta(seconds=5))),
    id='aws_query',
    name='Run AWS Query',
    replace_existing=True
    )
# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())
