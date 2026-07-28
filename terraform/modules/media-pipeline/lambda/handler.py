"""Submit a MediaConvert job when a video lands in the ingest bucket.

Triggered by S3 ObjectCreated. Builds an adaptive HLS ladder (720p + 480p) plus a
poster thumbnail, writing outputs under <base-key>/ in the output bucket. The
MediaConvert account endpoint is account-specific, so it's discovered once and
cached across warm invocations.
"""

import os
import urllib.parse

import boto3

REGION = os.environ["AWS_REGION"]
ROLE_ARN = os.environ["MEDIACONVERT_ROLE_ARN"]
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]

_client = None


def _mediaconvert():
    global _client
    if _client is None:
        bootstrap = boto3.client("mediaconvert", region_name=REGION)
        endpoint = bootstrap.describe_endpoints()["Endpoints"][0]["Url"]
        _client = boto3.client("mediaconvert", region_name=REGION, endpoint_url=endpoint)
    return _client


def _hls_output(name_modifier, height, bitrate):
    return {
        "NameModifier": name_modifier,
        "ContainerSettings": {"Container": "M3U8", "M3u8Settings": {}},
        "VideoDescription": {
            "Height": height,
            "CodecSettings": {
                "Codec": "H_264",
                "H264Settings": {
                    "RateControlMode": "QVBR",
                    "MaxBitrate": bitrate,
                    "SceneChangeDetect": "TRANSITION_DETECTION",
                },
            },
        },
        "AudioDescriptions": [
            {
                "CodecSettings": {
                    "Codec": "AAC",
                    "AacSettings": {"Bitrate": 96000, "CodingMode": "CODING_MODE_2_0", "SampleRate": 48000},
                }
            }
        ],
    }


def _job_settings(input_uri, base):
    dest = f"s3://{OUTPUT_BUCKET}/{base}"
    return {
        "Inputs": [
            {
                "FileInput": input_uri,
                "AudioSelectors": {"Audio Selector 1": {"DefaultSelection": "DEFAULT"}},
                "VideoSelector": {},
                "TimecodeSource": "ZEROBASED",
            }
        ],
        "OutputGroups": [
            {
                "Name": "HLS",
                "OutputGroupSettings": {
                    "Type": "HLS_GROUP_SETTINGS",
                    "HlsGroupSettings": {
                        "Destination": f"{dest}/hls/",
                        "SegmentLength": 6,
                        "MinSegmentLength": 0,
                    },
                },
                "Outputs": [
                    _hls_output("_720", 720, 3_000_000),
                    _hls_output("_480", 480, 1_200_000),
                ],
            },
            {
                "Name": "Thumbnail",
                "OutputGroupSettings": {
                    "Type": "FILE_GROUP_SETTINGS",
                    "FileGroupSettings": {"Destination": f"{dest}/thumb/"},
                },
                "Outputs": [
                    {
                        "NameModifier": "_poster",
                        "ContainerSettings": {"Container": "RAW"},
                        "VideoDescription": {
                            "CodecSettings": {
                                "Codec": "FRAME_CAPTURE",
                                "FrameCaptureSettings": {
                                    "FramerateNumerator": 1,
                                    "FramerateDenominator": 5,
                                    "MaxCaptures": 1,
                                    "Quality": 80,
                                },
                            }
                        },
                    }
                ],
            },
        ],
    }


def handler(event, context):
    client = _mediaconvert()
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        base = key.rsplit(".", 1)[0]  # strip the extension; outputs live under this prefix
        client.create_job(
            Role=ROLE_ARN,
            Settings=_job_settings(f"s3://{bucket}/{key}", base),
            StatusUpdateInterval="SECONDS_60",
        )
        print(f"submitted MediaConvert job for s3://{bucket}/{key} -> {base}/")
