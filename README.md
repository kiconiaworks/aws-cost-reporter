# aws-cost-reporter

Generates cost daily charts and sends to slack.


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

## bokeh update

Note, this requires that `bokeh` needs to be udpated in order to properly find the `phantomjs` binary dependency:

The following file is updated to include `` as the *phantomjs_path*:
```python
def detect_phantomjs(version='2.1'):
    ''' Detect if PhantomJS is avaiable in PATH, at a minimum version.

    Args:
        version (str, optional) :
            Required minimum version for PhantomJS (mostly for testing)

    Returns:
        str, path to PhantomJS

    '''
    if settings.phantomjs_path() is not None:
        phantomjs_path = settings.phantomjs_path()
    else:
        if os.path.exists('/var/task/bin/phantomjs'):
            phantomjs_path = '/var/task/bin/phantomjs'
        elif hasattr(shutil, "which"):
            phantomjs_path = shutil.which("phantomjs") or "phantomjs"
        else:
            # Python 2 relies on Environment variable in PATH - attempt to use as follows
            phantomjs_path = "phantomjs"

    try:
        proc = Popen([phantomjs_path, "--version"], stdout=PIPE, stderr=PIPE)
        proc.wait()
        out = proc.communicate()

        if len(out[1]) > 0:
            raise RuntimeError('Error encountered in PhantomJS detection: %r' % out[1].decode('utf8'))

        required = V(version)
        installed = V(out[0].decode('utf8'))
        if installed < required:
            raise RuntimeError('PhantomJS version to old. Version>=%s required, installed: %s' % (required, installed))

    except OSError:
        raise RuntimeError('PhantomJS is not present in PATH. Try "conda install phantomjs" or \
            "npm install -g phantomjs-prebuilt"')

    return phantomjs_path
```

The following `bokeh/io/export.py` was updated:

```python
def export_png(obj, filename=None, height=None, width=None, webdriver=None, as_fileobj=False):
    ''' Export the LayoutDOM object or document as a PNG.

    If the filename is not given, it is derived from the script name
    (e.g. ``/foo/myplot.py`` will create ``/foo/myplot.png``)

    Args:
        obj (LayoutDOM or Document) : a Layout (Row/Column), Plot or Widget
            object or Document to export.

        filename (str, optional) : filename to save document under (default: None)
            If None, infer from the filename.

        height (int) : the desired height of the exported layout obj only if
            it's a Plot instance. Otherwise the height kwarg is ignored.

        width (int) : the desired width of the exported layout obj only if
            it's a Plot instance. Otherwise the width kwarg is ignored.

        webdriver (selenium.webdriver) : a selenium webdriver instance to use
            to export the image.

    Returns:
        filename (str) : the filename where the static file is saved.

    .. warning::
        Responsive sizing_modes may generate layouts with unexpected size and
        aspect ratios. It is recommended to use the default ``fixed`` sizing mode.

    '''

    image = get_screenshot_as_png(obj, height=height, width=width, driver=webdriver)

    if filename is None:
        filename = default_filename("png")
    if as_fileobj:
        return image
    else:
        image.save(filename)
        return abspath(filename)

```