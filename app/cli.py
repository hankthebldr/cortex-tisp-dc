from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.analytics.runs import analyze
from app.config import settings
from app.masking.tokenizer import Masker
from app.parsers.threat_log import read_threat_log
from app.parsers.traffic_log import read_traffic_log


def _parse_ip_list(value: str) -> set[str]:
    return {part.strip() for part in value.split(",") if part.strip()} if value else set()


def _run_ingest(args: argparse.Namespace) -> int:
    threat_df, _ = read_threat_log(Path(args.threat))
    traffic_df = None
    if args.traffic:
        traffic_df, _ = read_traffic_log(Path(args.traffic), args.sinkhole_ip)

    result = analyze(
        threat_df=threat_df,
        traffic_df=traffic_df,
        sinkhole_ip=args.sinkhole_ip,
        declared_infra=_parse_ip_list(args.infra_ips),
    )

    payload: dict = {
        "context": {
            "customer": args.customer,
            "industry": args.industry,
            "se": args.se,
            "sinkhole_ip": args.sinkhole_ip,
        },
        **result.to_dict(),
    }

    if args.mask:
        masker = Masker()
        masker.register(t.source_ip for t in result.top_talkers)
        masker.register(s.source_ip for s in result.sinkhole_endpoints)
        payload["mask_map"] = masker.mapping

    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tisp", description="TISP Evolution CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Parse CSVs and emit analysis JSON")
    ingest.add_argument("--threat", required=True, help="Path to threat log CSV")
    ingest.add_argument("--traffic", default=None, help="Path to sinkhole traffic log CSV (optional)")
    ingest.add_argument("--industry", default="Healthcare", help="Industry vertical")
    ingest.add_argument("--customer", default="Customer", help="Customer name")
    ingest.add_argument("--se", default="SE", help="Preparing SE name")
    ingest.add_argument("--sinkhole-ip", default=settings.sinkhole_ip, help="Sinkhole destination IP")
    ingest.add_argument("--infra-ips", default="", help="Comma-separated declared DC/DNS IPs")
    ingest.add_argument("--mask", action="store_true", help="Tokenize internal source IPs")
    ingest.set_defaults(func=_run_ingest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
