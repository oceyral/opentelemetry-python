# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import threading
import typing
import uuid
from functools import wraps
from os import environ

from pkg_resources import iter_entry_points

from opentelemetry.context.context import Context, _RuntimeContext
from opentelemetry.environment_variables import OTEL_PYTHON_CONTEXT

logger = logging.getLogger(__name__)
_RUNTIME_CONTEXT = None  # type: typing.Optional[_RuntimeContext]
_RUNTIME_CONTEXT_LOCK = threading.Lock()

_F = typing.TypeVar("_F", bound=typing.Callable[..., typing.Any])


def _load_runtime_context(func: _F) -> _F:
    """A decorator used to initialize the global RuntimeContext

    Returns:
        A wrapper of the decorated method.
    """

    @wraps(func)  # type: ignore[misc]
    def wrapper(  # type: ignore[misc]
        *args: typing.Tuple[typing.Any, typing.Any],
        **kwargs: typing.Dict[typing.Any, typing.Any]
    ) -> typing.Optional[typing.Any]:
        global _RUNTIME_CONTEXT  # pylint: disable=global-statement

        with _RUNTIME_CONTEXT_LOCK:
            if _RUNTIME_CONTEXT is None:
                # FIXME use a better implementation of a configuration manager to avoid having
                # to get configuration values straight from environment variables
                default_context = "contextvars_context"

                configured_context = environ.get(
                    OTEL_PYTHON_CONTEXT, default_context
                )  # type: str
                try:
                    _RUNTIME_CONTEXT = next(
                        iter_entry_points(
                            "opentelemetry_context", configured_context
                        )
                    ).load()()
                except Exception:  # pylint: disable=broad-except
                    logger.error(
                        "Failed to load context: %s", configured_context
                    )
        return func(*args, **kwargs)  # type: ignore[misc]

    return typing.cast(_F, wrapper)  # type: ignore[misc]


def create_key(keyname: str) -> str:
    """To allow cross-cutting concern to control access to their local state,
    the RuntimeContext API provides a function which takes a keyname as input,
    and returns a unique key.
    Args:
        keyname: The key name is for debugging purposes and is not required to be unique.
    Returns:
        A unique string representing the newly created key.
    """
    return keyname + "-" + str(uuid.uuid4())


def get_value(key: str, context: typing.Optional[Context] = None) -> "object":
    """To access the local state of a concern, the RuntimeContext API
    provides a function which takes a context and a key as input,
    and returns a value.

    Args:
        key: The key of the value to retrieve.
        context: The context from which to retrieve the value, if None, the current context is used.

    Returns:
        The value associated with the key.
    """
    return context.get(key) if context is not None else get_current().get(key)


def set_value(
    key: str, value: "object", context: typing.Optional[Context] = None
) -> Context:
    """To record the local state of a cross-cutting concern, the
    RuntimeContext API provides a function which takes a context, a
    key, and a value as input, and returns an updated context
    which contains the new value.

    Args:
        key: The key of the entry to set.
        value: The value of the entry to set.
        context: The context to copy, if None, the current context is used.

    Returns:
        A new `Context` containing the value set.
    """
    if context is None:
        context = get_current()
    new_values = context.copy()
    new_values[key] = value
    return Context(new_values)


@_load_runtime_context  # type: ignore
def get_current() -> Context:
    """To access the context associated with program execution,
    the Context API provides a function which takes no arguments
    and returns a Context.

    Returns:
        The current `Context` object.
    """
    return _RUNTIME_CONTEXT.get_current()  # type:ignore


@_load_runtime_context  # type: ignore
def attach(context: Context) -> object:
    """Associates a Context with the caller's current execution unit. Returns
    a token that can be used to restore the previous Context.

    Args:
        context: The Context to set as current.

    Returns:
        A token that can be used with `detach` to reset the context.
    """
    return _RUNTIME_CONTEXT.attach(context)  # type:ignore


@_load_runtime_context  # type: ignore
def detach(token: object) -> None:
    """Resets the Context associated with the caller's current execution unit
    to the value it had before attaching a specified Context.

    Args:
        token: The Token that was returned by a previous call to attach a Context.
    """
    try:
        _RUNTIME_CONTEXT.detach(token)  # type: ignore
    except Exception:  # pylint: disable=broad-except
        logger.error("Failed to detach context")


# FIXME This is a temporary location for the suppress instrumentation key.
# Once the decision around how to suppress instrumentation is made in the
# spec, this key should be moved accordingly.
_SUPPRESS_INSTRUMENTATION_KEY = create_key("suppress_instrumentation")
_SUPPRESS_HTTP_INSTRUMENTATION_KEY = create_key(
    "suppress_http_instrumentation"
)
