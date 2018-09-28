# aws-cost-reporter

This project provides a simple SLACK bot to generate AWS cost daily charts and sends to slack.


## Prerequisites

- python 3.6
- AWS Account 
    - Must have access to billing
    
    > User billing access must be turned on via the root account
     

## AWS Configuration

In order to allow the lambda function to access the billing information the following configuration needs to be performed.

1. Deploy as zappa application:
    
    > This process creates the related roles for the lambda operation
    
    ```
    zappa deploy
    ```

2. Create policy from template:

    ```
    export ACCOUNTID=391604260554
    envsubst < ./aws/policies/billing-cost-explorer-policy.json.template > ./billing-cost-explorer-policy.json 
    ```

3. Create policy to allow programmatic access to the 'cost-explorer':

    ```
    aws iam create-policy --policy-name cost-reporter-ce-policy --policy-document file://./billing-cost-explorer-policy.json 
    ``` 

4. Apply created policy to the execution role created on `zappa deploy`:

```
aws iam attach-role-policy --role-name aws-cost-report-dev-ZappaLambdaExecutionRole --policy-arn $(aws iam list-policies --scope Local --query "Policies[?PolicyName=='cost-reporter-ce-policy'].Arn" --output text)
```

## Slack Bot Setup

For your workspace login and 'install' the app to create a bot following the instructions at the link below:

https://api.slack.com/bot-users#creating-bot-user


## zappa (lambda) Setup

Zappa provides a simple framework enabling you to easily setup and run python applications using AWS Lambda (function as a service).

```json
{
    "dev": {
        "aws_region": "us-west-2",
        "profile_name": "default",
        "project_name": "aws-cost-report",
        "runtime": "python3.6",
        "s3_bucket": "pacioli-zappa-jklalkjdf92923923",
        "apigateway_enabled": false,
        "keep_warm": false,
        "environment_variables": {
            "SLACK_API_TOKEN": "{INSERT YOUR SLACK BOT TOKEN}",
            "BOKEH_PHANTOMJS_PATH": "/var/task/bin/phantomjs"
        },
        "events": [{
           "function": "pacioli.event_handlers.post_daily_chart",
           "expression": "cron(0 0 ? * MON,WED,FRI *)"
        }]
    }
}
```

> NOTE: Slack bot tokens are prefixed with "xoxb-"

## bokeh setting

In order to export PNG bokeh requires that [phantomjs](http://phantomjs.org/download.html) be available.
The location of `phantomjs` can be specified via the `BOKEH_PHANTOMJS_PATH` environment variable._


### Prepare phantomjs

1. Download the linux phantomjs binary from (http://phantomjs.org/download.html)

2. Place binary in `REPOSITORY_ROOT/bin`

> NOTE: If you used the sample `zappa_settings.json` template above you should be set to run the function.


