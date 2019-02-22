# aws-cost-reporter (pacioli)

[![CircleCI](https://circleci.com/gh/kiconiaworks/aws-cost-reporter.svg?style=svg)](https://circleci.com/gh/kiconiaworks/aws-cost-reporter)

The 'pacioli' package is a simple SLACK bot that generates a chart of your AWS account(s) monthly cost and posts the resulting chart image to the defined slack channel (`SLACK_CHANNEL_NAME`).


## Prerequisites

- python 3.6
- awscli
- pipenv
- AWS Account 
    - Must have access to billing
    
    > User billing access must be turned on via the root account
     
## Prepare pipenv environment

```
# Installs the 'frozen' libraires known to work
pipenv sync
```     

### Create AccountId Mapping

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
        "runtime": "python3.6",
        "s3_bucket": "{YOUR BUCKET}",
        "apigateway_enabled": false,
        "keep_warm": false,
        "environment_variables": {
            "SLACK_API_TOKEN": "{INSERT YOUR SLACK BOT TOKEN}",
            "BOKEH_PHANTOMJS_PATH": "/var/task/bin/phantomjs",
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
- BOKEH_PHANTOMJS_PATH: "/var/task/bin/phantomjs",
- SLACK_CHANNEL_NAME": "{NAME_OF_SLACK_CHANNEL_TO_POST_TO}"
- SLACK_BOT_NAME: Display name of Slack Bot
- SLACK_BOT_ICONURL: Icon image for BOT

## bokeh setting

In order to export PNG bokeh requires that [phantomjs](http://phantomjs.org/download.html) be available.
The location of `phantomjs` can be specified via the `BOKEH_PHANTOMJS_PATH` environment variable.

The `get_phantomjs.py` script will attempt to download the latest `phantomjs` linux binary and place it in the `{REPOSITORY_ROOT}/bin` directory:

```
pipenv run get_phantomjs.py
```

If the script doesn't work follow the steps in the section below. 

### Prepare phantomjs

1. Download the linux phantomjs binary from (http://phantomjs.org/download.html):

    ```bash
    export PHANTOMJS_VERSION=phantomjs-2.1.1-linux-x86_64
    wget https://bitbucket.org/ariya/phantomjs/downloads/${PHANTOMJS_VERSION}.tar.bz2
    tar xvjf ${PHANTOMJS_VERSION}.tar.bz2
    sudo mv ${PHANTOMJS_VERSION}/bin/phantomjs bin/  
    ```

2. Place binary in `REPOSITORY_ROOT/bin`

> NOTE: If you used the sample `zappa_settings.json` template above you should be set to run the function.


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
- BOKEH_PHANTOMJS_PATH

Once setup and environment variables set, `pacioli` can be tested locally using the following command:

> NOTE: the command below assumes that pipenv is used and sync'd and you are already in the shell
> This will create and post the image to the configured slack channel


```
python -m pacioli.cli
```

If the `--test` option is given, results will NOT be posted to slack, and CostManager.collect_account_basic_account_metrics() output will be displayed:
```
python -m pacioli.cli --test
```