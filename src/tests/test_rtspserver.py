import pytest
from unittest.mock import MagicMock, patch
import gi

# Attempt to load GStreamer and GstRtspServer
try:
    gi.require_version('Gst', '1.0')
    gi.require_version('GstRtspServer', '1.0')
    from gi.repository import Gst, GstRtspServer, GLib
except (ValueError, ImportError) as e:
    # This allows tests to be collected even if GStreamer is not fully installed,
    # but tests requiring Gst objects will be skipped.
    Gst = None
    GstRtspServer = None
    GLib = None
    print(f"GStreamer libraries not found or could not be loaded: {e}. Some rtspserver tests may be skipped.")

# Assuming rtspserver.py is in the src directory and accessible in PYTHONPATH
# from rtspserver import PushedStreamFactory # This direct import might fail if Gst is not loaded

# To avoid conditional import at top level based on Gst presence, we can define PushedStreamFactory
# or import it within tests or fixtures that are skipped if Gst is None.

# If Gst is available, import the class to be tested
if Gst and GstRtspServer:
    from rtspserver import PushedStreamFactory
else:
    # Define a dummy class if GStreamer is not available so tests can be defined
    # and skipped, rather than causing import errors at collection time.
    class PushedStreamFactory:
        def __init__(self, *args, **kwargs):
            pass
        def do_create_element(self, url):
            return None

@pytest.fixture
def factory():
    if not Gst or not GstRtspServer:
        pytest.skip("GStreamer libraries not available, skipping PushedStreamFactory tests")
    return PushedStreamFactory()

@pytest.fixture
def mock_url():
    # Create a mock GstRtspServer.RTSPUrl object
    # This might need more specific mocking depending on how it's used
    url = MagicMock(spec=GstRtspServer.RTSPUrl if GstRtspServer else object)
    url.get_request_uri.return_value = "rtsp://localhost:8554/push"
    return url


@patch('rtspserver.Gst.parse_launch') # Patch Gst.parse_launch within rtspserver module
def test_do_create_element_success(mock_parse_launch, factory: PushedStreamFactory, mock_url):
    if not Gst: # Skip if Gst wasn't loaded properly
        pytest.skip("GStreamer not available, skipping test")

    mock_pipeline = MagicMock(spec=Gst.Pipeline if Gst else object)
    mock_parse_launch.return_value = mock_pipeline

    # Expected pipeline string from PushedStreamFactory
    expected_pipeline_str = "( rtph264depay name=depay ! h264parse ! fakesink name=sink async=false enable-last-sample=false )"

    pipeline = factory.do_create_element(mock_url)

    mock_parse_launch.assert_called_once_with(expected_pipeline_str)
    assert pipeline == mock_pipeline
    mock_url.get_request_uri.assert_called_once()

@patch('rtspserver.Gst.parse_launch')
def test_do_create_element_parse_failure(mock_parse_launch, factory: PushedStreamFactory, mock_url, caplog):
    if not Gst or not GLib: # GLib.Error is used in the except block
        pytest.skip("GStreamer/GLib not available, skipping test")

    # Simulate Gst.parse_launch raising a GLib.Error
    mock_parse_launch.side_effect = GLib.Error("Mocked Gst.parse_launch error")

    pipeline = factory.do_create_element(mock_url)

    assert pipeline is None
    assert "Failed to parse launch pipeline" in caplog.text
    assert "Mocked Gst.parse_launch error" in caplog.text

# It's hard to test the main() function directly without a running GLib main loop
# and actual GStreamer server setup. Such tests would be more integration-level.
# The PushedStreamFactory logic is the most unit-testable part of rtspserver.py.

# Example of how to skip all tests in this file if Gst is not available:
# pytestmark = pytest.mark.skipif(Gst is None, reason="GStreamer libraries not found")
# However, the individual skips in fixtures/tests provide more fine-grained control. 