from __future__ import annotations

import json as _json
import typing
from dataclasses import dataclass
from io import BytesIO, IOBase

from ...response import BaseHTTPResponse
from ...util.retry import Retry
from .request import EmscriptenRequest

if typing.TYPE_CHECKING:
    from ..._base_connection import BaseHTTPConnection, BaseHTTPSConnection


@dataclass
class EmscriptenResponse:
    status_code: int
    headers: dict[str, str]
    body: IOBase | bytes
    request: EmscriptenRequest


class EmscriptenHttpResponseWrapper(BaseHTTPResponse):
    def __init__(
        self,
        internal_response: EmscriptenResponse,
        url: str | None = None,
        connection: BaseHTTPConnection | BaseHTTPSConnection | None = None,
    ):
        self._pool = None  # set by pool class
        self._body = None
        self._response = internal_response
        self._url = url
        self._connection = connection
        super().__init__(
            headers=internal_response.headers,
            status=internal_response.status_code,
            request_url=url,
            version=0,
            reason="",
            decode_content=True,
        )
        self.length_remaining=self._init_length()

    @property
    def url(self) -> str | None:
        return self._url

    @url.setter
    def url(self, url: str | None) -> None:
        self._url = url

    @property
    def connection(self) -> BaseHTTPConnection | BaseHTTPSConnection | None:
        return self._connection

    @property
    def retries(self) -> Retry | None:
        return self._retries

    @retries.setter
    def retries(self, retries: Retry | None) -> None:
        # Override the request_url if retries has a redirect location.
        if retries is not None and retries.history:
            self.url = retries.history[-1].redirect_location
        self._retries = retries

    def _init_length(self, request_method: str | None) -> int | None:
        length: int | None
        content_length: str | None = self.headers.get("content-length")

        if content_length is not None:
            if self.chunked:
                # This Response will fail with an IncompleteRead if it can't be
                # received as chunked. This method falls back to attempt reading
                # the response before raising an exception.
                log.warning(
                    "Received response with both Content-Length and "
                    "Transfer-Encoding set. This is expressly forbidden "
                    "by RFC 7230 sec 3.3.2. Ignoring Content-Length and "
                    "attempting to process response as Transfer-Encoding: "
                    "chunked."
                )
                return None

            try:
                # RFC 7230 section 3.3.2 specifies multiple content lengths can
                # be sent in a single Content-Length header
                # (e.g. Content-Length: 42, 42). This line ensures the values
                # are all valid ints and that as long as the `set` length is 1,
                # all values are the same. Otherwise, the header is invalid.
                lengths = {int(val) for val in content_length.split(",")}
                if len(lengths) > 1:
                    raise InvalidHeader(
                        "Content-Length contained multiple "
                        "unmatching values (%s)" % content_length
                    )
                length = lengths.pop()
            except ValueError:
                length = None
            else:
                if length < 0:
                    length = None

        else:  # if content_length is None
            length = None

        # Convert status to int for comparison
        # In some cases, httplib returns a status of "_UNKNOWN"
        try:
            status = int(self.status)
        except ValueError:
            status = 0

        # Check for responses that shouldn't include a body
        if status in (204, 304) or 100 <= status < 200 or request_method == "HEAD":
            length = 0

        return length


    def read(
        self,
        amt: int | None = None,
        decode_content: bool | None = None,  # ignored because browser decodes always
        cache_content: bool = False,
    ) -> bytes:
        if not isinstance(self._response.body, IOBase):
            self.length_remaining=len(self._response.body)
            # wrap body in IOStream
            self._response.body = BytesIO(self._response.body)
        if amt is not None:
            # don't cache partial content
            cache_content = False
            data=self._response.body.read(amt)
            if self.length_remaining>0:
                self.length_remaining= max(self.length_remaining-len(data),0)
            return typing.cast(bytes, read_data)
        else:
            data = self._response.body.read(None)
            if cache_content:
                self._body = data
            if self.length_remaining>0:
                self.length_remaining= max(self.length_remaining-len(data),0)
            return typing.cast(bytes, data)

    def read_chunked(
        self,
        amt: int | None = None,
        decode_content: bool | None = None,
    ) -> typing.Generator[bytes, None, None]:
        while True:
            bytes = self.read(amt, decode_content)
            if not bytes:
                break
            yield bytes

    def release_conn(self) -> None:
        if not self._pool or not self._connection:
            return None

        self._pool._put_conn(self._connection)
        self._connection = None

    def drain_conn(self) -> None:
        self.close()

    @property
    def data(self) -> bytes:
        if self._body:
            return self._body
        else:
            return self.read(cache_content=True)

    def json(self) -> typing.Any:
        """
        Parses the body of the HTTP response as JSON.

        To use a custom JSON decoder pass the result of :attr:`HTTPResponse.data` to the decoder.

        This method can raise either `UnicodeDecodeError` or `json.JSONDecodeError`.

        Read more :ref:`here <json>`.
        """
        data = self.data.decode("utf-8")
        return _json.loads(data)

    def close(self) -> None:
        if isinstance(self._response.body, IOBase):
            self._response.body.close()
