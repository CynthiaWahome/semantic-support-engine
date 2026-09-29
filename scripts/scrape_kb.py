"""Run the Slack extraction pipeline without loading dotenv files."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

from slack_sdk import WebClient

from app.integrations.slack_history import SlackHistoryReader
from app.repositories.dataset import LocalDatasetRepository
from app.services.dataset import DatasetService
from app.services.scraper import SlackQAScraper


def build_parser() -> argparse.ArgumentParser:
    """Build the safe dry-run and full extraction interface."""
    parser = argparse.ArgumentParser(
        description="Extract Q&A records from Slack history."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List target channels without reading messages.",
    )
    parser.add_argument(
        "--channels", nargs="+", help="Explicit channel names to process."
    )
    parser.add_argument(
        "--exclude-channels", nargs="*", default=[], help="Channel names to skip."
    )
    parser.add_argument(
        "--patterns",
        default=os.environ.get("CHANNEL_PATTERNS", "support-,help-"),
        help="Comma-separated channel prefixes.",
    )
    parser.add_argument(
        "--mentors-channel",
        default=os.environ.get("MENTORS_CHANNEL", "experts"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.environ.get("SCRAPER_OUTPUT_DIR", "data/scraper")),
    )
    return parser


def run(args: argparse.Namespace, reader: SlackHistoryReader) -> int:
    """Execute discovery, optional extraction, and local publication."""
    scraper = SlackQAScraper(
        reader,
        channel_patterns=tuple(pattern.strip() for pattern in args.patterns.split(",")),
        mentors_channel=args.mentors_channel,
        bot_user_id=reader.fetch_bot_user_id(),
    )
    channels = scraper.discover_target_channels(args.channels, args.exclude_channels)
    print(f"Target channels ({len(channels)}):")
    for name in channels:
        print(f"- {name}")
    if args.dry_run:
        return 0

    scraper.load_mentor_ids(channels)
    records = []
    checkpoint_path = args.output_dir / "kb_checkpoint.json"
    for name, channel_id in channels.items():
        records.extend(scraper.process_channel(name, channel_id))
        LocalDatasetRepository(checkpoint_path).save(records)

    dataset_service = DatasetService(
        LocalDatasetRepository(args.output_dir / "kb_dataset.json")
    )
    dataset_service.publish(
        records,
        args.output_dir / "kb_dataset.json",
        args.output_dir / "kb_dataset.xlsx",
    )
    print(f"Published {len(records)} Q&A records to {args.output_dir}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and construct the authenticated Slack reader."""
    args = build_parser().parse_args(argv)
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise ValueError("SLACK_BOT_TOKEN must be provided by the runtime environment")
    return run(args, SlackHistoryReader(WebClient(token=token)))


if __name__ == "__main__":
    raise SystemExit(main())
