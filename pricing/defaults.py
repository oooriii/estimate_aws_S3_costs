"""Default AWS pricing hints for interactive prompts (eu-south-2)."""

EU_SOUTH_2_DEFAULTS = {
    "region": "eu-south-2",
    "storage_per_gb_month": {
        "STANDARD": 0.0255,
        "STANDARD_IA": 0.014,
        "INTELLIGENT_TIERING": 0.0255,
        "GLACIER_INSTANT": 0.0045,
    },
    "intelligent_tiering_monitoring_per_1000_objects": 0.0025,
    "requests_per_1000": {
        "GET": 0.00043,
        "PUT": 0.0054,
        "LIST": 0.0054,
    },
    "s3_transfer_tiers": [
        (10240, 0.09),
        (None, 0.085),
    ],
    "cloudfront_transfer_tiers": [
        (10240, 0.085),
        (None, 0.08),
    ],
    "cloudfront_requests_per_10000": {
        "GET": 0.0075,
    },
    "recommended_cache_hit_ratio": 0.85,
}
