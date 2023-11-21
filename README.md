# Confidence OpenFeature Python Provider

This repo contains the OpenFeature Python flag provider for [Confidence](https://confidence.spotify.com/).

## OpenFeature

Before starting to use the provider, it can be helpful to read through the general [OpenFeature docs](https://docs.openfeature.dev/)
and get familiar with the concepts. 

## Adding the dependency

#### pip install
<!---x-release-please-start-version-->
```python
pip install confidence-openfeature-provider==0.1.4
```

#### requirements.txt
```python
confidence-openfeature-provider==0.1.4

pip install requirements.txt
```
<!---x-release-please-end-->

### Creating and using the flag provider

Below is an example for how to create a OpenFeature client using the Confidence flag provider, and then resolve
a flag with a boolean attribute. The provider is configured with an api key and a region, which will determine
where it will send the resolving requests. 

The flag will be applied immediately, meaning that Confidence will count the targeted user as having received the treatment. 

You can retrieve attributes on the flag variant using property dot notation, meaning `test-flag.boolean-key` will retrieve
the attribute `boolean-key` on the flag `test-flag`. 

You can also use only the flag name `test-flag` and retrieve all values as a map with `resolve_object_details()`. 

The flag's schema is validated against the requested data type, and if it doesn't match it will fall back to the default value.

```python

from confidence.provider import Region
from confidence.provider import ConfidenceOpenFeatureProvider
from openfeature.api import EvaluationContext
from openfeature import api

provider = ConfidenceOpenFeatureProvider("client_secret", Region.EU)

api.set_provider(provider)
open_feature_client = api.get_client()

ctx = EvaluationContext(targeting_key="random", attributes={
    "user": {
        "country": "SE"
    }
})

flag_value = open_feature_client.get_boolean_value(flag_key="test-flag.boolean-key", default_value=False,
                                                   evaluation_context=ctx)

print(flag_value)

```
