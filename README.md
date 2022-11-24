# aws-cost-reporter (pacioli)

[![CircleCI](https://circleci.com/gh/kiconiaworks/aws-cost-reporter.svg?style=svg)](https://circleci.com/gh/kiconiaworks/aws-cost-reporter)

The 'pacioli' package is a simple SLACK bot that generates status of your AWS account(s) monthly cost and posts the resulting reports to the defined slack channel (`SLACK_CHANNEL_NAME`).

The following reports are sent via Slack:

- AWS Account Cost Change Report
- AWS Tag (ProjectID) Cost Change Report
- Top N Tag (ProjectID) Service Breakdown report

## Prerequisites

- python 3.9
- awscli
- pipenv
- AWS Account 
    - Must have access to billing
    
    > User billing access must be turned on via the root account
     
## (optional) Enable "Resource Tag" in Cost Explorer

In order to allow the COST EXPLORER to see tags on resources, the desired "Resource Tag" *MUST* be enabled.

> The system assumes that the desired tag is, "ProjectId"

To enable resource tags refer to:

- https://console.aws.amazon.com/billing/home?#/preferences/tags

## Prepare pipenv environment

```
# Installs the 'frozen' libraires known to work
pipenv sync
```     
### (optional) Enable "Resource Tag" Mapping Feature

The value of the enabled "Resource Tag" may optional be mapped by providing a mapping file in a defined bucket.

Set the following *environment variable* with the s3 uri (ex: `s3://bucket/key/filename.json` to where the mapping file is written.

> NOTE: the function needs read access to the given bucket
 
Add to deployed Lambda function "Environment Variables" Configuration: 
``` 
GROUPBY_TAG_DISPLAY_MAPPING_S3_URI=s3://bucket/key/filename.json
```

### (optional) Create AccountId Mapping

Optionally the `accountid_mapping.json` file can be prepared to provide a more easily understandable display of accounts.

The file should be created in the repository root and consist of the following:

> NOTE: multiple {AWS ACCOUNT ID} entries are supported

```
{
  "{AWS ACCOUNT ID}": "Identity Account (root)",
  "previous_month_total": "Previous Month (Total)",
  "current_month_total": "Current Month (Total)"
}
```

## Slack Bot Setup

For your workspace login and 'install' the app to create a bot following the instructions at the link below:

https://api.slack.com/bot-users#creating-bot-user


## zappa (lambda) Setup

[Zappa](https://github.com/Miserlou/Zappa) provides a framework enabling you to easily setup and run python applications using AWS Lambda (function as a service).
Below is a template `zappa_settings.json` file that can be used to prepare this function.

> This is a scheduled function, no need for `apigateway_enabled`, or `keep_warm`.

```json
{
    "dev": {
        "aws_region": "us-west-2",
        "profile_name": "default",
        "project_name": "aws-cost-report",
        "runtime": "python3.7",
        "s3_bucket": "{YOUR BUCKET}",
        "apigateway_enabled": false,
        "keep_warm": false,
        "environment_variables": {
            "SLACK_API_TOKEN": "{INSERT YOUR SLACK BOT TOKEN}",
            "SLACK_CHANNEL_NAME": "{NAME_OF_SLACK_CHANNEL_TO_POST_TO}"
        },
        "events": [{
           "function": "pacioli.event_handlers.post_daily_chart",
           "expression": "cron(0 50,53 ? * MON,WED,FRI *)"
        }]
    }
}
```

> NOTE: Slack bot tokens are prefixed with "xoxb-"

### Available Environment Variables

- SLACK_API_TOKEN: {INSERT YOUR SLACK BOT TOKEN}",
- SLACK_CHANNEL_NAME": "{NAME_OF_SLACK_CHANNEL_TO_POST_TO}"
- SLACK_BOT_NAME: Display name of Slack Bot
- SLACK_BOT_ICONURL: Icon image for BOT
- LOG_LEVEL: Cloudwatch log level (DEFAULT=INFO)
- UTC_OFFSET: (float) Time offset from UTC for date time display in reports
- PROJECTSERVICES_TOPN: Number of Top Projects to include in the "Top N Tag (ProjectID) Service Breakdown" report (DEFAULT=10)

## AWS Configuration

In order to allow the lambda function to access the billing information the following configuration needs to be performed.

Requires:
- awscli
- envsubst
    - macos install:
    
        ```bash
        brew install gettext
        brew link --force gettext   
        ```
    - ubuntu install:
    
        ```bash
        sudo apt install gettext-base
        ```
    
    

1. Deploy as zappa application:
    
    > This process creates the related roles for the lambda operation
    
    ```
    zappa deploy
    ```

2. Create policy from the template:

    > `envsubst` will use your set Environment Variables to replace those defined values in the template file
    > In this case ACCOUNTID is overwritten.

    ```
    export ACCOUNTID={YOUR_ACCOUNT_ID}
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

## Testing

To test locally, set the following ENVIRONMENT VARIABLES:

- SLACK_API_TOKEN
- SLACK_CHANNEL_NAME
- S3_SERVICE_ENDPOINT=https://127.0.0.1:4566

Once setup and environment variables set, `pacioli` can be tested locally using the following command:

> NOTE: the command below assumes that pipenv is used and sync'd and you are already in the shell

```
python -m pacioli.cli
```

To test submission to SLACK, use the `--post-to-slack` option:
```
python -m pacioli.cli --post-to-slack
```


### awscli ce example

> NOTE: your account must have billing access

```
aws ce get-cost-and-usage \
    --time-period Start="2020-12-01",End="2020-12-31" \
    --granularity DAILY \
    --metrics "BlendedCost" "UnblendedCost" "UsageQuantity" \
    --group-by Type=DIMENSION,Key=LINKED_ACCOUNT Type=DIMENSION,Key=SERVICE
```

### Execute lambda function

From the AWS lambda Test Console add the command, and click, "Test":

```json
{
  "command": "pacioli.handlers.events.post_status"
}
```