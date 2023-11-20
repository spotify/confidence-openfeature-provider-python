import dataclasses
from typing import Any, Dict, List, Optional, Type, Union, get_args, get_origin
from typing_extensions import TypeGuard
from enum import Enum
from confidence import __version__

import requests
from openfeature.api import EvaluationContext
from openfeature.exception import (
    FlagNotFoundError,
    ParseError,
    TypeMismatchError,
)
from openfeature.flag_evaluation import FlagResolutionDetails
from openfeature.flag_evaluation import Reason
from openfeature.api import Hook
from openfeature.provider.metadata import Metadata
from openfeature.provider.provider import AbstractProvider

from .names import FlagName, VariantName

EU_RESOLVE_API_ENDPOINT = "https://resolver.eu.confidence.dev/v1"
US_RESOLVE_API_ENDPOINT = "https://resolver.us.confidence.dev/v1"


Primitive = Union[str, int, float, bool, None]
FieldType = Union[Primitive, List[Primitive], List["Object"], "Object"]
Object = Dict[str, FieldType]


def is_primitive(field_type: Type[Any]) -> TypeGuard[Type[Primitive]]:
    return field_type in get_args(Primitive)


def primitive_matches(value: FieldType, value_type: Type[Primitive]) -> bool:
    return (
        value_type is None
        or (value_type is int and isinstance(value, int))
        or (value_type is float and isinstance(value, float))
        or (value_type is str and isinstance(value, str))
        or (value_type is bool and isinstance(value, bool))
    )


class Region(Enum):
    def endpoint(self) -> str:
        return self.value

    EU = EU_RESOLVE_API_ENDPOINT
    US = US_RESOLVE_API_ENDPOINT


@dataclasses.dataclass
class ResolveResult(object):
    value: Optional[Object]
    variant: Optional[str]
    token: str


class ConfidenceOpenFeatureProvider(AbstractProvider):
    def __init__(
        self,
        client_secret: str,
        region: Region = Region.EU,
        apply_on_resolve: bool = True,
    ):
        self._client_secret = client_secret
        self._api_endpoint = region.endpoint()
        self._apply_on_resolve = apply_on_resolve

    #
    # --- Provider API ---
    #

    def get_metadata(self) -> Metadata:
        return Metadata("Confidence")

    def get_provider_hooks(self) -> List[Hook]:
        return []

    def resolve_boolean_details(
        self,
        flag_key: str,
        default_value: bool,
        evaluation_context: Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[bool]:
        return self._evaluate(flag_key, bool, default_value, evaluation_context)

    def resolve_float_details(
        self,
        flag_key: str,
        default_value: float,
        evaluation_context: Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[float]:
        return self._evaluate(flag_key, float, default_value, evaluation_context)

    def resolve_integer_details(
        self,
        flag_key: str,
        default_value: int,
        evaluation_context: Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[int]:
        return self._evaluate(flag_key, int, default_value, evaluation_context)

    def resolve_string_details(
        self,
        flag_key: str,
        default_value: str,
        evaluation_context: Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[str]:
        return self._evaluate(flag_key, str, default_value, evaluation_context)

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: Union[Object, List[Primitive]],
        evaluation_context: Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[Union[Object, List[Primitive]]]:
        return self._evaluate(flag_key, Object, default_value, evaluation_context)

    #
    # --- internals
    #

    def _evaluate(
        self,
        flag_key: str,
        value_type: Type[FieldType],
        default_value: FieldType,
        evaluation_context: Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[Any]:
        if evaluation_context is None:
            evaluation_context = EvaluationContext()

        if "." in flag_key:
            flag_id, value_path = flag_key.split(".", 1)
        else:
            flag_id = flag_key
            value_path = None

        context = {
            **(evaluation_context.attributes or {}),
        }
        if evaluation_context.targeting_key:
            context["targeting_key"] = evaluation_context.targeting_key

        result = self._resolve(FlagName(flag_id), context)
        if result.variant is None or len(str(result.value)) == 0:
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.DEFAULT,
                flag_metadata={"flag_key": flag_key},
            )

        variant_name = VariantName.parse(result.variant)

        value = self._select(result, value_path, value_type)
        if value is None:
            value = default_value

        return FlagResolutionDetails(
            value=value,
            variant=variant_name.variant,
            reason=Reason.TARGETING_MATCH,
            flag_metadata={"flag_key": flag_key},
        )

    def _resolve(self, flag_name: FlagName, context: Dict[str, str]) -> ResolveResult:
        request_body = {
            "clientSecret": self._client_secret,
            "evaluationContext": context,
            "apply": self._apply_on_resolve,
            "flags": [str(flag_name)],
            "sdk": {"id": "SDK_ID_PYTHON_PROVIDER", "version": __version__},
        }

        resolve_url = f"{self._api_endpoint}/flags:resolve"
        response = requests.post(resolve_url, json=request_body)

        if response.status_code == 404:
            raise FlagNotFoundError()

        response.raise_for_status()

        response_body = response.json()

        resolved_flags = response_body["resolvedFlags"]
        token = response_body["resolveToken"]

        if len(resolved_flags) == 0:
            return ResolveResult(None, None, token)

        resolved_flag = resolved_flags[0]
        variant = resolved_flag.get("variant")
        return ResolveResult(
            resolved_flag.get("value"), None if variant == "" else variant, token
        )

    @staticmethod
    def _select(
        result: ResolveResult,
        value_path: Optional[str],
        value_type: Type[FieldType],
    ) -> FieldType:
        value: FieldType = result.value

        if value_path is not None:
            keys = value_path.split(".")
            for key in keys:
                if not isinstance(value, dict):
                    raise ParseError()

                if key not in value:
                    raise ParseError()

                value = value.get(key)

        # skip type checking if the value was not specified
        if value is None:
            return None

        if not ConfidenceOpenFeatureProvider.type_matches(value, value_type):
            raise TypeMismatchError("type of value did not match excepted type")

        return value

    @staticmethod
    def type_matches(value: FieldType, value_type: Type[FieldType]) -> bool:
        origin = get_origin(value_type)

        if is_primitive(value_type):
            return primitive_matches(value, value_type)
        elif origin is list:
            return isinstance(value, list)
        elif origin is dict:
            return isinstance(value, dict)

        return False
