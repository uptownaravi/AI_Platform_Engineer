#!/usr/bin/env python3
"""
warrantyAI — Week 11
scripts/promote_canary.py

Promotes the Lambda staging alias to production.

Three modes:

  1. Canary (--canary N)
     Routes N% of production traffic to the staging version.
     Use this to test the new version on real traffic before full rollout.
     Monitor the CloudWatch dashboard for 15 minutes before promoting.

  2. Promote (--promote)
     Shifts 100% of production traffic to the staging version.
     Run this after the canary is healthy.

  3. Rollback (--rollback VERSION)
     Points production back to a specific previous version number.
     Use this if the new version is misbehaving.

Usage:
    # Step 1: Stage canary at 10% (optional)
    python scripts/promote_canary.py --canary 10

    # Step 2: Monitor CloudWatch dashboard for 15 minutes
    # open: https://ap-south-1.console.aws.amazon.com/cloudwatch/home#dashboards:name=warrantyai-observability

    # Step 3: Full promotion
    python scripts/promote_canary.py --promote

    # Rollback if needed
    python scripts/promote_canary.py --rollback 3

Requirements:
    pip install boto3
    AWS credentials with lambda:GetAlias, lambda:UpdateAlias permissions
"""

import argparse
import sys
import os
import boto3
from botocore.exceptions import ClientError

FUNCTION_NAME = os.environ.get("LAMBDA_FUNCTION_NAME", "warrantyai-langgraph-pipeline")
AWS_REGION    = os.environ.get("AWS_REGION", "ap-south-1")


def get_lambda_client():
    return boto3.client("lambda", region_name=AWS_REGION)


def get_alias_version(client, alias: str) -> str:
    """Return the function version a Lambda alias currently points to."""
    resp = client.get_alias(FunctionName=FUNCTION_NAME, Name=alias)
    return resp["FunctionVersion"]


def get_current_versions(client) -> dict:
    """Return current staging and production alias versions."""
    return {
        "staging":    get_alias_version(client, "staging"),
        "production": get_alias_version(client, "production"),
    }


def update_alias(client, alias: str, version: str, routing: dict | None = None) -> None:
    """Update a Lambda alias to point to a new version."""
    kwargs = dict(
        FunctionName    = FUNCTION_NAME,
        Name            = alias,
        FunctionVersion = version,
    )
    if routing:
        kwargs["RoutingConfig"] = {"AdditionalVersionWeights": routing}
    else:
        kwargs["RoutingConfig"] = {"AdditionalVersionWeights": {}}

    client.update_alias(**kwargs)


def cmd_canary(client, canary_pct: int) -> None:
    """Route canary_pct% of production traffic to the staging version."""
    versions     = get_current_versions(client)
    staging_ver  = versions["staging"]
    prod_ver     = versions["production"]

    if staging_ver == "$LATEST":
        print("ERROR: staging alias points to $LATEST, not a published version.")
        print("Publish a version first:")
        print(f"  aws lambda publish-version --function-name {FUNCTION_NAME}")
        sys.exit(1)

    if staging_ver == prod_ver:
        print(f"Staging ({staging_ver}) and production ({prod_ver}) are the same version — nothing to canary.")
        sys.exit(0)

    canary_weight = canary_pct / 100.0
    prod_weight   = 1 - canary_weight

    print(f"Setting canary: {prod_weight:.0%} → v{prod_ver}  |  {canary_weight:.0%} → v{staging_ver}")
    update_alias(
        client,
        alias   = "production",
        version = prod_ver,
        routing = {staging_ver: canary_weight},
    )
    print(f"Canary live. Monitor: https://{AWS_REGION}.console.aws.amazon.com/cloudwatch/home?region={AWS_REGION}#dashboards:name=warrantyai-observability")
    print(f"Promote when healthy: python scripts/promote_canary.py --promote")


def cmd_promote(client) -> None:
    """Shift 100% of production traffic to the staging version."""
    versions    = get_current_versions(client)
    staging_ver = versions["staging"]
    prod_ver    = versions["production"]

    if staging_ver == "$LATEST":
        print("ERROR: staging alias points to $LATEST.")
        print(f"  aws lambda publish-version --function-name {FUNCTION_NAME}")
        sys.exit(1)

    print(f"Promoting v{staging_ver} to production  (was: v{prod_ver})")
    update_alias(client, alias="production", version=staging_ver, routing=None)
    print(f"Production alias → v{staging_ver}. Done.")


def cmd_rollback(client, version: str) -> None:
    """Point production back to a specific version."""
    current = get_alias_version(client, "production")
    print(f"Rolling back production: v{current} → v{version}")
    update_alias(client, alias="production", version=version, routing=None)
    print(f"Production alias → v{version}. Rollback complete.")


def main():
    parser = argparse.ArgumentParser(
        description="Promote or rollback the warrantyAI Lambda production alias."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--canary", type=int, metavar="PCT",
        help="Route PCT%% of production traffic to the staging version (e.g. 10)",
    )
    group.add_argument(
        "--promote", action="store_true",
        help="Shift 100%% of production traffic to the staging version",
    )
    group.add_argument(
        "--rollback", type=str, metavar="VERSION",
        help="Point production back to a specific published version (e.g. 3)",
    )
    group.add_argument(
        "--status", action="store_true",
        help="Show current staging and production alias versions",
    )
    parser.add_argument(
        "--function", default=FUNCTION_NAME,
        help=f"Lambda function name (default: {FUNCTION_NAME})",
    )
    args = parser.parse_args()

    client = get_lambda_client()

    try:
        if args.status:
            versions = get_current_versions(client)
            print(f"staging    → v{versions['staging']}")
            print(f"production → v{versions['production']}")

        elif args.canary is not None:
            if not 1 <= args.canary <= 99:
                print("ERROR: canary percentage must be 1–99")
                sys.exit(1)
            cmd_canary(client, args.canary)

        elif args.promote:
            cmd_promote(client)

        elif args.rollback:
            cmd_rollback(client, args.rollback)

    except ClientError as e:
        print(f"AWS error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
