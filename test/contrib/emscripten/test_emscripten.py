from __future__ import annotations

import sys
import typing

import pytest

from urllib3.fields import _TYPE_FIELD_VALUE_TUPLE

from ...port_helpers import find_unused_port

if sys.version_info < (3, 11):
    # pyodide only works on 3.11+
    pytest.skip(allow_module_level=True)

# only run these tests if pytest_pyodide is installed
# so we don't break non-emscripten pytest running
pytest_pyodide = pytest.importorskip("pytest_pyodide")

from pytest_pyodide import run_in_pyodide  # type: ignore[import] # noqa: E402
from pytest_pyodide.decorator import (  # type: ignore[import] # noqa: E402
    copy_files_to_pyodide,
)

from .conftest import PyodideServerInfo, ServerRunnerInfo  # noqa: E402

# make our ssl certificates work in chrome
pytest_pyodide.runner.CHROME_FLAGS.append("ignore-certificate-errors")


# copy our wheel file to pyodide and install it
def install_urllib3_wheel() -> (
    typing.Callable[
        [typing.Callable[..., typing.Any]], typing.Callable[..., typing.Any]
    ]
):
    return copy_files_to_pyodide(  # type: ignore[no-any-return]
        file_list=[("dist/*.whl", "/tmp")], install_wheels=True
    )


@install_urllib3_wheel()
def test_index(selenium: typing.Any, testserver_http: PyodideServerInfo) -> None:
    @run_in_pyodide  # type: ignore[misc]
    def pyodide_test(selenium, host: str, port: int) -> None:  # type: ignore[no-untyped-def]
        from urllib3.connection import HTTPConnection
        from urllib3.response import HTTPResponse

        conn = HTTPConnection(host, port)
        conn.request("GET", f"http://{host}:{port}/")
        response = conn.getresponse()
        assert isinstance(response, HTTPResponse)
        data = response.data
        assert data.decode("utf-8") == "Dummy server!"

    pyodide_test(selenium, testserver_http.http_host, testserver_http.http_port)


# wrong protocol / protocol error etc. should raise an exception of urllib3.exceptions.ResponseError
@install_urllib3_wheel()
def test_wrong_protocol(
    selenium: typing.Any, testserver_http: PyodideServerInfo
) -> None:
    @run_in_pyodide(packages=("pytest",))  # type: ignore[misc]
    def pyodide_test(selenium, host: str, port: int) -> None:  # type: ignore[no-untyped-def]
        import pytest

        import urllib3.exceptions
        from urllib3.connection import HTTPConnection

        conn = HTTPConnection(host, port)
        try:
            conn.request("GET", f"http://{host}:{port}/")
            conn.getresponse()
            pytest.fail("Should have thrown ResponseError here")
        except BaseException as ex:
            assert isinstance(ex, urllib3.exceptions.ResponseError)

    pyodide_test(selenium, testserver_http.http_host, testserver_http.https_port)


# no connection - should raise
@install_urllib3_wheel()
def test_no_response(selenium: typing.Any, testserver_http: PyodideServerInfo) -> None:
    @run_in_pyodide(packages=("pytest",))  # type: ignore[misc]
    def pyodide_test(selenium, host: str, port: int) -> None:  # type: ignore[no-untyped-def]
        import pytest

        import urllib3.exceptions
        from urllib3.connection import HTTPConnection

        conn = HTTPConnection(host, port)
        try:
            conn.request("GET", f"http://{host}:{port}/")
            _ = conn.getresponse()
            pytest.fail("No response, should throw exception.")
        except BaseException as ex:
            assert isinstance(ex, urllib3.exceptions.ResponseError)

    pyodide_test(selenium, testserver_http.http_host, find_unused_port())


@install_urllib3_wheel()
def test_404(selenium: typing.Any, testserver_http: PyodideServerInfo) -> None:
    @run_in_pyodide  # type: ignore[misc]
    def pyodide_test(selenium, host: str, port: int) -> None:  # type: ignore[no-untyped-def]
        from urllib3.connection import HTTPConnection
        from urllib3.response import HTTPResponse

        conn = HTTPConnection(host, port)
        conn.request("GET", f"http://{host}:{port}/status?status=404 NOT FOUND")
        response = conn.getresponse()
        assert isinstance(response, HTTPResponse)
        assert response.status == 404

    pyodide_test(selenium, testserver_http.http_host, testserver_http.http_port)


# setting timeout should show a warning to js console
# if we're on the ui thread, because XMLHttpRequest doesn't
# support timeout in async mode if globalThis == Window
@install_urllib3_wheel()
def test_timeout_warning(
    selenium: typing.Any, testserver_http: PyodideServerInfo
) -> None:
    @run_in_pyodide()  # type: ignore[misc]
    def pyodide_test(selenium, host: str, port: int) -> None:  # type: ignore[no-untyped-def]
        import urllib3.contrib.emscripten.fetch
        from urllib3.connection import HTTPConnection

        conn = HTTPConnection(host, port, timeout=1.0)
        conn.request("GET", f"http://{host}:{port}/")
        conn.getresponse()
        assert urllib3.contrib.emscripten.fetch._SHOWN_TIMEOUT_WARNING

    pyodide_test(selenium, testserver_http.http_host, testserver_http.http_port)


@install_urllib3_wheel()
def test_timeout_in_worker(
    selenium: typing.Any,
    testserver_http: PyodideServerInfo,
    run_from_server: ServerRunnerInfo,
) -> None:
    worker_code = f"""
        import pyodide_js as pjs
        await pjs.loadPackage('http://{testserver_http.http_host}:{testserver_http.http_port}/wheel/dist.whl',deps=False)
        import urllib3.contrib.emscripten.fetch
        await urllib3.contrib.emscripten.fetch.wait_for_streaming_ready()
        from urllib3.exceptions import TimeoutError
        from urllib3.connection import HTTPConnection
        conn = HTTPConnection("{testserver_http.http_host}", {testserver_http.http_port},timeout=1.0)
        result=-1
        try:
            conn.request("GET","/slow")
            _response = conn.getresponse()
            result=-3
        except TimeoutError as e:
            result=1 # we've got the correct exception
        except BaseException as e:
            result=-2
        result
"""
    result = run_from_server.run_webworker(worker_code)
    # result == 1 = success, -2 = wrong exception, -3 = no exception thrown
    assert result == 1


@install_urllib3_wheel()
def test_index_https(selenium: typing.Any, testserver_http: PyodideServerInfo) -> None:
    @run_in_pyodide  # type: ignore[misc]
    def pyodide_test(selenium, host: str, port: int) -> None:  # type: ignore[no-untyped-def]
        from urllib3.connection import HTTPSConnection
        from urllib3.response import HTTPResponse

        conn = HTTPSConnection(host, port)
        conn.request("GET", f"https://{host}:{port}/")
        response = conn.getresponse()
        assert isinstance(response, HTTPResponse)
        data = response.data
        assert data.decode("utf-8") == "Dummy server!"

    pyodide_test(selenium, testserver_http.http_host, testserver_http.https_port)


@install_urllib3_wheel()
def test_non_streaming_no_fallback_warning(
    selenium: typing.Any, testserver_http: PyodideServerInfo
) -> None:
    @run_in_pyodide  # type: ignore[misc]
    def pyodide_test(selenium, host: str, port: int) -> None:  # type: ignore[no-untyped-def]
        import urllib3.contrib.emscripten.fetch
        from urllib3.connection import HTTPSConnection
        from urllib3.response import HTTPResponse

        conn = HTTPSConnection(host, port)
        conn.request("GET", f"https://{host}:{port}/", preload_content=True)
        response = conn.getresponse()
        assert isinstance(response, HTTPResponse)
        data = response.data
        assert data.decode("utf-8") == "Dummy server!"
        # no console warnings because we didn't ask it to stream the response
        assert not urllib3.contrib.emscripten.fetch._SHOWN_STREAMING_WARNING

    pyodide_test(selenium, testserver_http.http_host, testserver_http.https_port)


@install_urllib3_wheel()
def test_streaming_fallback_warning(
    selenium: typing.Any, testserver_http: PyodideServerInfo
) -> None:
    @run_in_pyodide  # type: ignore[misc]
    def pyodide_test(selenium, host: str, port: int) -> None:  # type: ignore[no-untyped-def]
        import urllib3.contrib.emscripten.fetch
        from urllib3.connection import HTTPSConnection
        from urllib3.response import HTTPResponse

        conn = HTTPSConnection(host, port)
        conn.request("GET", f"https://{host}:{port}/", preload_content=False)
        response = conn.getresponse()
        assert isinstance(response, HTTPResponse)
        data = response.data
        assert data.decode("utf-8") == "Dummy server!"
        # check that it has warned about falling back to non-streaming fetch
        assert urllib3.contrib.emscripten.fetch._SHOWN_STREAMING_WARNING

    pyodide_test(selenium, testserver_http.http_host, testserver_http.https_port)


def test_specific_method(
    selenium: typing.Any,
    testserver_http: PyodideServerInfo,
) -> None:
    @run_in_pyodide  # type: ignore[misc]
    def pyodide_test(selenium, host: str, port: int) -> None:  # type: ignore[no-untyped-def]
        from urllib3 import HTTPSConnectionPool

        with HTTPSConnectionPool(host, port) as pool:
            path = "/specific_method?method=POST"
            response = pool.request("POST", path)
            assert response.status == 200

            response = pool.request("PUT", path)
            assert response.status == 400

    pyodide_test(selenium, testserver_http.http_host, testserver_http.https_port)


@install_urllib3_wheel()
def test_streaming_download(
    selenium: typing.Any,
    testserver_http: PyodideServerInfo,
    run_from_server: ServerRunnerInfo,
) -> None:
    # test streaming download, which must be in a webworker
    # as you can't do it on main thread

    # this should return the 17mb big file, and
    # should not log any warning about falling back
    bigfile_url = (
        f"http://{testserver_http.http_host}:{testserver_http.http_port}/bigfile"
    )
    worker_code = f"""
            import pyodide_js as pjs
            await pjs.loadPackage('http://{testserver_http.http_host}:{testserver_http.http_port}/wheel/dist.whl',deps=False)

            import urllib3.contrib.emscripten.fetch
            await urllib3.contrib.emscripten.fetch.wait_for_streaming_ready()
            from urllib3.response import HTTPResponse
            from urllib3.connection import HTTPConnection
            import js

            conn = HTTPConnection("{testserver_http.http_host}", {testserver_http.http_port})
            conn.request("GET", "{bigfile_url}",preload_content=False)
            response = conn.getresponse()
            assert isinstance(response, HTTPResponse)
            assert urllib3.contrib.emscripten.fetch._SHOWN_STREAMING_WARNING==False
            data=response.data.decode('utf-8')
            data
"""
    result = run_from_server.run_webworker(worker_code)
    assert len(result) == 17825792


@install_urllib3_wheel()
def test_streaming_notready_warning(
    selenium: typing.Any,
    testserver_http: PyodideServerInfo,
    run_from_server: ServerRunnerInfo,
) -> None:
    # test streaming download but don't wait for
    # worker to be ready - should fallback to non-streaming
    # and log a warning
    bigfile_url = (
        f"http://{testserver_http.http_host}:{testserver_http.http_port}/bigfile"
    )
    worker_code = f"""
        import pyodide_js as pjs
        await pjs.loadPackage('http://{testserver_http.http_host}:{testserver_http.http_port}/wheel/dist.whl',deps=False)
        import urllib3
        from urllib3.response import HTTPResponse
        from urllib3.connection import HTTPConnection

        conn = HTTPConnection("{testserver_http.http_host}", {testserver_http.http_port})
        conn.request("GET", "{bigfile_url}",preload_content=False)
        response = conn.getresponse()
        assert isinstance(response, HTTPResponse)
        data=response.data.decode('utf-8')
        assert urllib3.contrib.emscripten.fetch._SHOWN_STREAMING_WARNING==True
        data
        """
    result = run_from_server.run_webworker(worker_code)
    assert len(result) == 17825792


@install_urllib3_wheel()
def test_post_receive_json(
    selenium: typing.Any, testserver_http: PyodideServerInfo
) -> None:
    @run_in_pyodide  # type: ignore[misc]
    def pyodide_test(selenium, host: str, port: int) -> None:  # type: ignore[no-untyped-def]
        import json

        from urllib3.connection import HTTPConnection
        from urllib3.response import HTTPResponse

        json_data = {
            "Bears": "like",
            "to": {"eat": "buns", "with": ["marmalade", "and custard"]},
        }
        conn = HTTPConnection(host, port)
        conn.request(
            "POST",
            f"http://{host}:{port}/echo_json",
            body=json.dumps(json_data).encode("utf-8"),
        )
        response = conn.getresponse()
        assert isinstance(response, HTTPResponse)
        data = response.json()
        assert data == json_data

    pyodide_test(selenium, testserver_http.http_host, testserver_http.http_port)


@install_urllib3_wheel()
def test_upload(selenium: typing.Any, testserver_http: PyodideServerInfo) -> None:
    @run_in_pyodide  # type: ignore[misc]
    def pyodide_test(selenium, host: str, port: int) -> None:  # type: ignore[no-untyped-def]
        from urllib3 import HTTPConnectionPool

        data = "I'm in ur multipart form-data, hazing a cheezburgr"
        fields: dict[str, _TYPE_FIELD_VALUE_TUPLE] = {
            "upload_param": "filefield",
            "upload_filename": "lolcat.txt",
            "filefield": ("lolcat.txt", data),
        }
        fields["upload_size"] = len(data)  # type: ignore
        with HTTPConnectionPool(host, port) as pool:
            r = pool.request("POST", "/upload", fields=fields)
            assert r.status == 200

    pyodide_test(selenium, testserver_http.http_host, testserver_http.http_port)
